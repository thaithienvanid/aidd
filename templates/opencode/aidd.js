// aidd's guard for OpenCode V2, written by `aidd init --harness opencode`; `aidd upgrade` rewrites it, so edit nothing here.
// It asks aidd's guard (`aidd hook pre-tool`, through this user's launcher, ~/.aidd/bin/aidd) before every tool call, and
// before every shell OpenCode creates outside the agent's tool flow, which the tool hook never sees. A deny throws, which
// blocks the call and tells the agent why. An allow says nothing: OpenCode's permission rules decide.
// The person's prompt goes to aidd's prompt hook (`aidd hook prompt-submit`) before the model reads it, so typed words
// such as `approve SPEC-1` or `land it` are their decision; aidd's note joins the prompt. Only a root session's prompt
// counts: a subagent's (one with a parent session) is an agent's words, never the person's. A root session's first prompt
// also runs `aidd hook session-start`, so the agent gets the loop's note; a compaction runs `aidd hook pre-compact`, so the
// work's state survives it. When the compaction ends, session-start runs again with source `compact`, which reads that
// state back, as Claude Code does, and its note joins the session (or the next prompt, where it cannot). A root
// session's finished turn (`session.execution.succeeded`, or
// `session.idle`) runs `aidd hook stop`: its reminder joins the session as a synthetic message, and at level strict that
// message continues the agent once, as Claude Code's Stop hook does.
// Every hook acts in the folder the session works in (`session.location.directory`), never the folder the plugin was
// loaded in, so a moved session or a worktree is guarded and recorded where it works. A session aidd cannot read is never
// taken for the person's, and the prompt hook says so on stderr rather than dropping a typed decision in silence.
// A shell command's `${AIDD_SESSION_ID}` becomes this session's id first, as Claude Code's ${CLAUDE_SESSION_ID} does,
// so `aidd autopilot` binds its lease to this session and the guard knows it. OpenCode's bash tool then creates its shell,
// and `create.before` names no session, so the plugin pairs it with the tool call the guard just allowed: the same command
// text, within a few seconds, used once. Any other shell names no session, never one an agent could set (`env`).
import { execFile } from "node:child_process"
import { readFileSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join, resolve } from "node:path"

const LAUNCHER = join(homedir(), ".aidd", "bin", "aidd")
const TIMEOUT_MS = 20000
const SETUP = "aidd init --harness opencode"
const SHELL_TOOLS = new Set(["shell", "bash"])
const SESSION_WORD = "${AIDD_SESSION_ID}"
// A shell call whose command is not text (or an argv of text) does not run: the guard cannot read what it would run.
const OPAQUE_SHELL = "aidd: this shell call names its command in a form the guard cannot read, so it does not run; run it again as one command line"
const SESSION_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/ // autopilot.SESSION_ID: never a word the shell would read
const PAIR_MS = 10000 // how long an allowed shell tool call's session waits for the shell it creates
const PAIR_MAX = 64 // the most tool calls that wait at once
// guard/repo_config.fails_closed: a project whose profile requires the guard or whose `mode` is enforce, or an
// organization's AIDD_HOOK_FAIL_CLOSED=1.
const FAIL_CLOSED_LINE = /^(?:profile:[ \t]*["']?(?:__FAIL_CLOSED_PROFILES__)|mode:[ \t]*["']?(?:__FAIL_CLOSED_MODES__))["']?[ \t]*(?:#[^\n]*)?\r?$/m

// One word of an argv, quoted for a POSIX shell: as it is when it holds only safe characters, else in single quotes.
function shellWord(word) {
  const text = String(word)
  return /^[A-Za-z0-9_@%+=:,./-]+$/.test(text) ? text : `'${text.replaceAll("'", `'"'"'`)}'`
}

// How this plugin starts the user launcher on this machine: `cmd.exe /c <launcher>.cmd` on Windows, where the launcher is
// `aidd.cmd` beside the sh script `aidd init` writes (hook_wiring.windows_launcher_script); the launcher itself elsewhere.
export function launcherInvocation(platform, launcher = LAUNCHER) {
  return platform === "win32" ? { file: "cmd.exe", args: ["/c", `${launcher}.cmd`] } : { file: launcher, args: [] }
}

// The project's config: in the session's folder, or the nearest folder above it that holds one.
function failsClosed(dir) {
  if (process.env.AIDD_HOOK_FAIL_CLOSED === "1") return true
  for (let d = resolve(dir); ; d = dirname(d)) {
    try {
      return FAIL_CLOSED_LINE.test(readFileSync(join(d, ".aidd", "config.yaml"), "utf8"))
    } catch {
      if (dirname(d) === d) return false
    }
  }
}

function ask(event, dir, hook = "pre-tool") {
  const started = launcherInvocation(process.platform)
  return new Promise((done) => {
    const child = execFile(started.file, [...started.args, "hook", hook], { cwd: dir, timeout: TIMEOUT_MS, maxBuffer: 1 << 20 }, (error, stdout) =>
      done({ error, stdout: String(stdout ?? "") }),
    )
    child.stdin?.on("error", () => {})
    child.stdin?.end(JSON.stringify(event))
  })
}

// What aidd answered: the parsed JSON, null when it said nothing, or undefined when it could not answer at all (a launcher
// that is missing, failed, or printed something the plugin cannot read). The caller decides what a silence means.
function answered({ error, stdout }) {
  if (error) return undefined
  try {
    return stdout.trim() ? JSON.parse(stdout) : null
  } catch {
    return undefined
  }
}

export default {
  id: "aidd",
  async setup(ctx) {
    const loadedIn = ctx.location.directory
    // The folder this session works in, falling back to the folder the plugin was loaded in: a session aidd cannot read
    // is still guarded and recorded, just where the plugin was loaded.
    const where = async (sessionID) => {
      if (typeof ctx.session?.get !== "function") return loadedIn
      try {
        const session = await ctx.session.get({ sessionID })
        const dir = session?.location?.directory
        return typeof dir === "string" && dir ? dir : loadedIn
      } catch {
        return loadedIn
      }
    }
    // One call to the guard: a deny throws (the call does not run), an allow says nothing, and a guard that cannot answer
    // is reported, or blocks when the session's project fails closed. True only when the guard answered and allowed.
    const guard = async (event, dir) => {
      const answer = answered(await ask(event, dir))
      if (answer === undefined) {
        const why = "__GUARD_MISSING__"
        if (failsClosed(dir)) throw new Error(why)
        console.error(why)
        return false
      }
      if (answer && answer.decision === "deny") throw new Error(String(answer.reason || "aidd: the guard denied this call"))
      return true
    }
    // The shell tool calls the guard allowed, by command text: the session and agent a `create.before` for the same text
    // takes once, while it is fresh. Two calls waiting with the same text from another session or agent pair neither, so
    // a shell never takes the wrong one's session.
    const allowed = new Map()
    const prune = () => {
      const now = Date.now()
      for (const [text, call] of allowed) if (now - call.at > PAIR_MS) allowed.delete(text)
    }
    const remember = (command, sessionID, agent) => {
      prune()
      const before = allowed.get(command)
      const both = before && (before.ambiguous || before.sessionID !== sessionID || before.agent !== agent)
      allowed.set(command, both ? { ambiguous: true, at: Date.now() } : { sessionID, agent, at: Date.now() })
      if (allowed.size > PAIR_MAX) allowed.delete(allowed.keys().next().value)
    }
    const pairedCall = (command) => {
      prune()
      const call = typeof command === "string" ? allowed.get(command) : undefined
      if (call) allowed.delete(command)
      return call && !call.ambiguous ? call : {}
    }
    const pairs = typeof ctx.shell?.hook === "function"
    await ctx.tool.hook("execute.before", async (event) => {
      let input = event.input && typeof event.input === "object" ? event.input : {}
      if (SHELL_TOOLS.has(event.tool) && typeof input.command !== "string") throw new Error(OPAQUE_SHELL)
      if (SHELL_TOOLS.has(event.tool) && typeof event.sessionID === "string" && SESSION_ID.test(event.sessionID)) {
        input = { ...input, command: input.command.replaceAll(SESSION_WORD, event.sessionID) }
        event.input = input
      }
      const dir = await where(event.sessionID)
      const workdir = typeof input.workdir === "string" && input.workdir ? resolve(dir, input.workdir) : dir
      const allows = await guard({ harness: "opencode", hook_event_name: "PreToolUse", tool: event.tool, input, sessionID: event.sessionID, agent: event.agent, cwd: workdir }, dir)
      if (allows && pairs && SHELL_TOOLS.has(event.tool) && typeof event.sessionID === "string") remember(input.command, event.sessionID, event.agent)
    })
    // A shell OpenCode creates itself (a command's `!` block, a terminal) skips the tool hook: ask the same guard here.
    // The bash tool's own shell comes here too, after its tool call.
    if (typeof ctx.shell?.hook === "function") {
      await ctx.shell.hook("create.before", async (event) => {
        // An argv is quoted word by word, as a POSIX shell would read it back, so the guard reads the command that runs.
        // A command in any other shape never runs unread: the guard would read it as no command at all.
        const argv = Array.isArray(event.command) && event.command.length && event.command.every((word) => typeof word === "string")
        if (typeof event.command !== "string" && !argv) throw new Error(OPAQUE_SHELL)
        const command = argv ? event.command.map(shellWord).join(" ") : event.command
        // OpenCode 2.1.0 sends only { command, cwd, timeout, shell, env }: the session is the paired tool call's, or none.
        // An OpenCode that names the session keeps it, and the paired call's agent only when that call is the session's.
        const paired = pairedCall(event.command)
        const own = typeof event.sessionID === "string" ? event.sessionID : undefined
        const { sessionID, agent } = own === undefined ? paired : { sessionID: own, agent: paired.sessionID === own ? paired.agent : undefined }
        const dir = typeof event.cwd === "string" && event.cwd ? event.cwd : await where(sessionID)
        await guard({ harness: "opencode", hook_event_name: "PreToolUse", tool: "shell", input: { command }, sessionID, agent, cwd: dir }, dir)
      })
    }
    if (typeof ctx.session?.hook !== "function") return // an OpenCode with no session hooks: the guard alone
    // Read the session's flag without letting a storage failure look like a first prompt.
    const started = async (key) => {
      try {
        return Boolean(await ctx.storage?.get(key))
      } catch {
        return false
      }
    }
    const mark = async (key, value) => {
      try {
        await ctx.storage?.set(key, value)
      } catch {
        // a flag that cannot be kept costs one note more or less, never the session
      }
    }
    await ctx.session.hook("prompt", async (event) => {
      const text = event?.prompt?.text
      if (typeof text !== "string" || !text.trim()) return
      let session
      try {
        session = await ctx.session.get({ sessionID: event.sessionID })
      } catch {
        // A person's typed decision must never vanish without a word: say it, and let the prompt go on as typed.
        console.error(`aidd: could not read this session, so a decision typed here is not recorded; run ${SETUP}, and aidd doctor says why`)
        return
      }
      if (!session || session.parentID) return // a subagent's prompt is an agent's words, never the person's
      const dir = await where(event.sessionID)
      const notes = []
      const key = `aidd:session-started:${event.sessionID}`
      const compacted = await started(`aidd:compacted:${event.sessionID}`)
      if (compacted || !(await started(key))) {
        const source = compacted ? "compact" : "startup"
        const first = answered(await ask({ harness: "opencode", hook_event_name: "SessionStart", source, sessionID: event.sessionID, cwd: dir }, dir, "session-start"))
        const note = first?.context
        if (typeof note === "string" && note) notes.push(note)
        // The session-start note may come twice when storage fails; a session that cannot start is the worse failure.
        await mark(key, true)
        if (compacted) await mark(`aidd:compacted:${event.sessionID}`, false)
      }
      await mark(`aidd:stop-continued:${event.sessionID}`, false) // the person spoke, so the next stop may continue the agent
      const got = answered(await ask({ harness: "opencode", hook_event_name: "UserPromptSubmit", prompt: text, sessionID: event.sessionID, cwd: dir }, dir, "prompt-submit"))
      const note = got?.context
      if (typeof note === "string" && note) notes.push(note)
      if (notes.length) event.prompt.text = [text, ...notes].join("\n\n")
    })
    await ctx.session.hook("compaction", async (event) => {
      const dir = await where(event?.sessionID)
      await ask({ harness: "opencode", hook_event_name: "PreCompact", sessionID: event?.sessionID, cwd: dir }, dir, "pre-compact")
      if (typeof event?.sessionID === "string") await mark(`aidd:compacted:${event.sessionID}`, true)
    })
    if (typeof ctx.event?.subscribe !== "function" || typeof ctx.session.synthetic !== "function") return // a prompt carries both
    // A root session's own turn: a subagent's ends in its lead's session, which is checked there.
    const rootSession = async (sessionID) => {
      try {
        const session = await ctx.session.get({ sessionID })
        return Boolean(session) && !session.parentID
      } catch {
        return false
      }
    }
    // Text for the agent, joined to the session as a synthetic message: `resume` starts a turn, else the next one reads it.
    const join = async (sessionID, text, resume) => {
      try {
        await ctx.session.synthetic({ sessionID, text, description: "aidd", resume })
        return true
      } catch {
        console.error(`aidd: this note could not join the session: ${text}`)
        return false
      }
    }
    // OpenCode goes on working after a compaction with no prompt, so the session-start note with source `compact`
    // joins at once, as Claude Code's does; when it cannot, the flag leaves it to the next prompt.
    const compacted = async (sessionID) => {
      const flag = `aidd:compacted:${sessionID}`
      if (!(await started(flag)) || !(await rootSession(sessionID))) return
      const dir = await where(sessionID)
      const answer = answered(await ask({ harness: "opencode", hook_event_name: "SessionStart", source: "compact", sessionID, cwd: dir }, dir, "session-start"))
      const text = answer?.context
      if (typeof text !== "string" || !text || (await join(sessionID, text, false))) await mark(flag, false)
    }
    // A root session's finished turn: the stop hook's reminder joins the session. A block continues the agent once, and
    // the flag tells the next stop so, as Claude Code's `stop_hook_active` does; any other answer waits for the next turn.
    const stop = async (sessionID) => {
      if (!(await rootSession(sessionID))) return
      const dir = await where(sessionID)
      const flag = `aidd:stop-continued:${sessionID}`
      const answer = answered(await ask({ harness: "opencode", hook_event_name: "Stop", sessionID, stop_hook_active: await started(flag), cwd: dir }, dir, "stop"))
      const block = answer?.decision === "block"
      const text = block ? answer.reason : answer?.context
      if (typeof text !== "string" || !text) return
      if (block) await mark(flag, true)
      await join(sessionID, text, block)
    }
    const turns = new Set() // the turns that started and have not ended, so one turn runs one stop check
    const checks = new Map() // each session's stop checks, one after another, so each reads the flag the last one set
    ;(async () => {
      for await (const event of ctx.event.subscribe()) {
        const id = event?.data?.sessionID
        if (typeof id !== "string") continue
        if (event.type === "session.execution.started") turns.add(id)
        else if (event.type === "session.compaction.ended") compacted(id).catch(() => {})
        else if ((event.type === "session.execution.succeeded" || event.type === "session.idle") && turns.delete(id)) {
          checks.set(id, (checks.get(id) ?? Promise.resolve()).then(() => stop(id)).catch(() => {}))
        }
      }
    })().catch(() => {})
  },
}
