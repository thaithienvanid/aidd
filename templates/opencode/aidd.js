// aidd's guard for OpenCode V2, written by `aidd init --harness opencode`; `aidd upgrade` rewrites it, so edit nothing here.
// Before each tool call it asks aidd's guard (`aidd hook pre-tool`, through this user's launcher, ~/.aidd/bin/aidd).
// A deny throws, which blocks the call and tells the agent why. An allow says nothing: OpenCode's permission rules decide.
// A shell command's `${AIDD_SESSION_ID}` becomes this session's id first, as Claude Code's ${CLAUDE_SESSION_ID} does,
// so `aidd autopilot` binds its lease to this session and the guard knows it.
import { execFile } from "node:child_process"
import { readFileSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join, resolve } from "node:path"

const LAUNCHER = join(homedir(), ".aidd", "bin", "aidd")
const TIMEOUT_MS = 20000
const SETUP = "aidd init --harness opencode"
const SHELL_TOOLS = new Set(["shell", "bash"])
const SESSION_WORD = "${AIDD_SESSION_ID}"
const SESSION_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/ // autopilot.SESSION_ID: never a word the shell would read
// guard/repo_config.fails_closed: a project whose profile requires the guard, or an organization's AIDD_HOOK_FAIL_CLOSED=1.
const FAIL_CLOSED_LINE = /^profile:[ \t]*["']?(?:__FAIL_CLOSED_PROFILES__)["']?[ \t]*(?:#[^\n]*)?\r?$/m

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

function ask(event, dir) {
  return new Promise((done) => {
    const child = execFile(LAUNCHER, ["hook", "pre-tool"], { cwd: dir, timeout: TIMEOUT_MS, maxBuffer: 1 << 20 }, (error, stdout) =>
      done({ error, stdout: String(stdout ?? "") }),
    )
    child.stdin?.on("error", () => {})
    child.stdin?.end(JSON.stringify(event))
  })
}

export default {
  id: "aidd",
  async setup(ctx) {
    const dir = ctx.location.directory
    await ctx.tool.hook("execute.before", async (event) => {
      let input = event.input && typeof event.input === "object" ? event.input : {}
      if (SHELL_TOOLS.has(event.tool) && typeof input.command === "string" && typeof event.sessionID === "string" && SESSION_ID.test(event.sessionID)) {
        input = { ...input, command: input.command.replaceAll(SESSION_WORD, event.sessionID) }
        event.input = input
      }
      const workdir = typeof input.workdir === "string" && input.workdir ? resolve(dir, input.workdir) : dir
      const { error, stdout } = await ask(
        { harness: "opencode", hook_event_name: "PreToolUse", tool: event.tool, input, sessionID: event.sessionID, agent: event.agent, cwd: workdir },
        dir,
      )
      let answer = null
      try {
        answer = error ? undefined : stdout.trim() ? JSON.parse(stdout) : null
      } catch {
        answer = undefined
      }
      if (answer === undefined) {
        const why = `aidd: the guard could not run on this machine: run ${SETUP}, and aidd doctor says why`
        if (failsClosed(dir)) throw new Error(`${why}; this project requires it`)
        console.error(why)
        return
      }
      if (answer && answer.decision === "deny") throw new Error(String(answer.reason || "aidd: the guard denied this call"))
    })
  },
}
