// aidd's plugin for OpenCode V2 (the terminal half): `/aidd <verb>` in the terminal, and the status it draws. It asks no
// agent: every answer is the aidd CLI's own line, or the terminal's own dialog. `status.js` beside it holds the pure half
// (the verbs, the argv, and the lines), so this file holds only what OpenCode's terminal needs.
// The person's answer is recorded by the aidd CLI with `--decided-via opencode`: the guard denies the same words from an
// agent's shell, so only this dialog can give them. The status draws what `aidd list --waiting-on-me --json` prints, and
// nothing else, so there is one owner for what waits on the person.
import { Plugin } from "@opencode/plugin/tui"
import { execFile } from "node:child_process"
import { homedir } from "node:os"
import { join } from "node:path"
import { For, Show, createSignal } from "solid-js"

import {
  STATUS_ARGV,
  TITLE,
  approveArgv,
  failedLine,
  firstLine,
  footerLine,
  helpLines,
  initArgs,
  initCheckArgv,
  isReady,
  mergeArgv,
  parseVerb,
  PROPOSAL_USAGE,
  proposalArgv,
  proposalAsked,
  proposalPreviewOf,
  proposalQuestion,
  proposalShowArgv,
  recordedLine,
  NOT_ON_A_PLATFORM,
  landArgv,
  mergesOnPlatform,
  parsed,
  previewOf,
  publishFrom,
  publishShowArgv,
  standingScope,
  standingArgv,
  statusFrom,
  cliChecked,
  nothingDue,
  checkParts,
  stepWaits,
  repoChecked,
  updateChecks,
  updateQuestion,
  updateSaid,
  updateSteps,
  EXPLORE_PREFIX,
  EXPLORE_WORD,
  EXPLORE_USAGE,
  countedLine,
  exploreArgv,
  exploreAsked,
  exploreQuestion,
  exploreLine,
  menuLines,
  outsideOf,
  mergeQuestion,
  outsideText,
  specQuestion,
} from "./status.js"

const CLI = join(homedir(), ".aidd", "bin", "aidd")
const TIMEOUT_MS = 600_000
const MISSING = "aidd did not start: run `aidd init --harness opencode` in a terminal, then `aidd doctor`"
const RECORD = "Record this approval?"
const NOTHING = "aidd recorded nothing"

// The aidd CLI, in the folder the session works in: what it printed, whether it failed, and its stderr. aidd says why it
// failed on stderr, so a failure reads aidd's own reason; JSON it printed stays the answer, since a preview's problems
// are in it.
function run(dir, argv, timeoutMs = 120_000) {
  return new Promise((done) => {
    execFile(CLI, argv, { cwd: dir, timeout: timeoutMs, maxBuffer: 1 << 22 }, (error, stdout, stderr) => {
      const out = String(stdout ?? "").trim()
      if (!error) return done({ failed: false, said: out })
      if (error.code === "ENOENT") return done({ failed: true, said: MISSING })
      if (error.killed) return done({ failed: true, said: `\`aidd ${argv.join(" ")}\` took over ${timeoutMs / 1000} seconds` })
      const err = String(stderr ?? "").trim()
      const ended = error.signal ? `was stopped by ${error.signal}` : `exited ${error.code}`
      done({ failed: true, said: (out.startsWith("{") ? out : err || out) || `\`aidd ${argv.join(" ")}\` ${ended}`, stderr: err })
    })
  })
}

// A verb that throws still answers: the person reads why, and the command that works in a terminal. Nothing was
// recorded past the last step that said so.
function answered(context, work, input) {
  return work.catch((error) => toast(context, failedLine(error?.message ?? error, input), true))
}

function toast(context, message, failed = false) {
  return context.ui.toast.show({ message, variant: failed ? "error" : "success" })
}

function show(context, message) {
  return context.ui.dialog.alert({ title: TITLE, message })
}

// git, in the folder the session works in, for `/aidd explore`: what it printed, and whether it failed.
function git(dir, argv) {
  return new Promise((done) => {
    execFile("git", argv, { cwd: dir, timeout: 60_000 }, (error, stdout, stderr) => {
      done({ failed: Boolean(error), said: String(stdout ?? "").trim() || String(stderr ?? "").trim() })
    })
  })
}

// One decision, asked once and then recorded by the aidd CLI. A cancelled dialog records nothing. When something
// changed outside the agent's session since the last decision, aidd's line that it counts as theirs comes after.
async function ask(context, dir, question, argv, said = firstLine) {
  const agreed = await context.ui.dialog.confirm({ title: RECORD, message: question, label: { confirm: "Record", cancel: "Nothing" } })
  if (!agreed) return toast(context, NOTHING)
  const got = await run(dir, argv)
  const counted = got.failed ? "" : countedLine(got.said)
  return toast(context, [(got.failed ? firstLine(got.said) : said(got.said)) || NOTHING, counted].filter(Boolean).join(" "), got.failed)
}

// `/aidd approve`: a Spec or the merge, this branch, or a standing approval.
async function approve(context, dir, args) {
  const what = (args[0] ?? "").toLowerCase()
  if (what === "stop") return await stop(context, dir)
  if (what === "all") {
    const scope = standingScope(args.slice(1))
    const publish = scope.includes("and-publish") ? " and publish each reviewed change" : ""
    const shown = await run(dir, standingArgv(scope, true))
    const problems = shown.failed ? [firstLine(shown.said)] : parsed(shown.said).problems ?? []
    if (problems.length > 0) return show(context, [...problems, "Fix them, then ask again."].join("\n"))
    const changed = outsideText(outsideOf(parsed(shown.said)))
    return await ask(context, dir, `Let the agent record every approval${publish} for you until you stop it?${changed}`, standingArgv(scope, false, parsed(shown.said).outside_hash))
  }
  if (what === "merge" || what === "") {
    const shown = previewOf("merge", await run(dir, ["approve", "merge", "--show"]))
    if (!isReady(shown)) return show(context, [...shown.problems, "Fix them, then ask again."].join("\n"))
    return await ask(context, dir, mergeQuestion(shown, "Approve merging it?"), mergeArgv(shown))
  }
  const ids = args.filter((word) => word !== "--auto-merge")
  const list = []
  for (const id of ids) {
    const shown = previewOf("spec", await run(dir, ["approve", "spec", id, "--show"]))
    if (!isReady(shown)) return show(context, [...shown.problems, `Fix them, then ask again.`].join("\n"))
    list.push({ id: shown.id || id, shown })
  }
  const agreed = await context.ui.dialog.confirm({ title: RECORD, message: specQuestion(list), label: { confirm: "Record", cancel: "Nothing" } })
  if (!agreed) return toast(context, NOTHING)
  let counted = ""
  // Each approval moves the decision records, so only the first names the digest of what the dialog showed.
  for (const [at, one] of list.entries()) {
    const got = await run(dir, approveArgv(one.id, one.shown.commit, at === 0 ? one.shown.seen : ""))
    if (got.failed) return toast(context, firstLine(got.said), true)
    counted ||= countedLine(got.said)
  }
  return toast(context, [`aidd recorded ${list.length === 1 ? list[0].id : `${list.length} approvals`}`, counted].filter(Boolean).join(" "), false)
}

// `/aidd land`: the tests run again on the head, and it lands on the local trunk only if they pass.
async function land(context, dir) {
  const shown = previewOf("merge", await run(dir, ["land", "--show"]))
  if (!isReady(shown)) return show(context, [...shown.problems, "Fix them, then ask again."].join("\n"))
  const message = mergeQuestion(shown, "The tests run again first; it lands only if they pass. Land it?")
  const agreed = await context.ui.dialog.confirm({ title: RECORD, message, label: { confirm: "Land", cancel: "Nothing" } })
  if (!agreed) return toast(context, NOTHING)
  const got = await run(dir, landArgv(shown), TIMEOUT_MS)
  return toast(context, [firstLine(got.said) || NOTHING, got.failed ? "" : countedLine(got.said)].filter(Boolean).join(" "), got.failed)
}

// `/aidd merge`: the person's Merge approval on this branch's pull or merge request, with its auto-merge. A branch not on
// a platform has none: nothing is recorded, and the answer names `/aidd land` and `publish`. A failed `land --show`
// says nothing about the platform (it refuses a dirty working tree first), so the preview below says what stops this
// approval, as Claude Code's `merge it` does.
async function merge(context, dir) {
  const where = await run(dir, ["land", "--show"])
  if (!where.failed && !mergesOnPlatform(parsed(where.said))) return show(context, NOT_ON_A_PLATFORM)
  const shown = previewOf("merge", await run(dir, ["approve", "merge", "--show"]))
  if (!isReady(shown)) return show(context, [...shown.problems, "Fix them, then ask again."].join("\n"))
  return await ask(context, dir, mergeQuestion(shown, "Approve it on its PR/MR? It merges once aidd/gate passes."), mergeArgv(shown, true))
}

// `/aidd decide PROP-1 go [why]` or `/aidd sign-off PROP-1`: what `--show` says the person decides, then the dialog,
// then the record for exactly that decision, or for a sign-off exactly the text's hash. aidd writes it into the
// proposal for the person to commit.
async function proposal(context, dir, verb, args) {
  const asked = proposalAsked(verb, args)
  if (!asked) return show(context, PROPOSAL_USAGE)
  const shown = proposalPreviewOf(asked, await run(dir, proposalShowArgv(asked)))
  if (!isReady(shown)) return show(context, [...shown.problems, "Fix them, then ask again."].join("\n"))
  return await ask(context, dir, proposalQuestion(asked, shown), proposalArgv(asked, shown), recordedLine)
}

// `/aidd stop` (or `/aidd approve stop`): the end of the standing approval. It only takes approval back, so it never
// asks, as in Claude Code.
async function stop(context, dir) {
  const got = await run(dir, standingArgv("stop"))
  return toast(context, firstLine(got.said) || NOTHING, got.failed)
}

// `/aidd explore <topic>`: this worktree moves to the explore branch of `topic` (a new branch from here, or the one that
// exists), after one question. Only a person starts one: the guard holds an agent's switch, and no agent reaches this
// terminal's verbs. aidd's own prompt hook does the same for the typed `explore branch <topic>`.
async function exploreBranch(context, dir, args) {
  const topic = exploreAsked(args)
  if (!topic) return show(context, EXPLORE_USAGE)
  const branch = `${EXPLORE_PREFIX}${topic}`
  const plan = exploreArgv(branch, false)
  if ((await git(dir, plan.check)).failed) return show(context, `aidd: ${branch} is not a branch name git accepts. ${EXPLORE_USAGE.slice(6)}`)
  const agreed = await context.ui.dialog.confirm({ title: RECORD, message: exploreQuestion(branch), label: { confirm: "Move", cancel: "Nothing" } })
  if (!agreed) return toast(context, NOTHING)
  const exists = !(await git(dir, plan.exists)).failed
  const switched = await git(dir, exploreArgv(branch, exists).switch)
  const head = await git(dir, plan.head)
  if (head.failed || head.said !== branch) return toast(context, `aidd: git could not switch to ${branch}: ${firstLine(switched.said) || "it said nothing"}`, true)
  return toast(context, exploreLine(branch))
}

// `/aidd publish`: what would leave this machine, or why aidd could not say. The person types `publish` to take it off,
// and aidd records it.
async function publish(context, dir) {
  return show(context, publishFrom(await run(dir, publishShowArgv())))
}

// `/aidd update`: the aidd CLI and this repository's aidd files, after one dialog.
async function update(context, dir) {
  // Each check on its own: the CLI's fails before the first release or offline, and the repository's still counts.
  const [checked, planned] = await Promise.all(updateChecks().map((argv) => run(dir, argv)))
  // aidd did not start, so neither check ran: that is the answer, as a failure.
  if (checked.said === MISSING) return toast(context, MISSING, true)
  const cli = cliChecked(checked)
  const repo = repoChecked(planned)
  if (!cli.isDue && !repo.isDue) {
    const due = nothingDue(cli, repo)
    return toast(context, due.message, due.failed)
  }
  const steps = updateSteps(cli, repo)
  // Only this repository's files are due, and they wait for a CLI aidd knows is current: nothing would run.
  if (steps.length === 0) return toast(context, checkParts(cli, repo).join(" "), true)
  const agreed = await context.ui.dialog.confirm({ title: RECORD, message: updateQuestion(cli, repo), label: { confirm: "Update", cancel: "Nothing" } })
  if (!agreed) return toast(context, NOTHING)
  const said = []
  let failed = false
  for (const argv of steps) {
    const waits = stepWaits(argv, failed)
    if (waits) {
      said.push(waits)  // the CLI update failed, so the old CLI would write its older files
      continue
    }
    const got = await run(dir, argv, TIMEOUT_MS)
    said.push(updateSaid(argv, got, repo))
    failed = failed || got.failed
  }
  return toast(context, said.filter(Boolean).join(" ") || "aidd updated", failed)
}

// `/aidd init`: adopt aidd here, after the dry run and one dialog.
async function adopt(context, dir, args) {
  const flags = initArgs(args.join(" "))
  const planned = await run(dir, [...initCheckArgv(), ...flags])
  if (planned.failed) return toast(context, firstLine(planned.said), true)
  const agreed = await context.ui.dialog.confirm({ title: RECORD, message: `${planned.said}\n\nAdopt aidd here now?`, label: { confirm: "Install", cancel: "Nothing" } })
  if (!agreed) return toast(context, NOTHING)
  const got = await run(dir, ["init", ...flags], TIMEOUT_MS)
  return toast(context, firstLine(got.said) || "aidd installed", got.failed)
}

// One verb, from the person's own line. No verb reaches an agent's turn.
async function verb(context, input) {
  const asked = parseVerb(input ?? "")
  const dir = context.location?.directory ?? "."
  if (asked.problem) return toast(context, asked.problem, true)
  if (asked.verb === "menu") return show(context, menuLines().join("\n"))
  if (asked.verb === "help") return show(context, helpLines().join("\n"))
  if (asked.verb === "status") return show(context, statusFrom(await run(dir, STATUS_ARGV)).lines.join("\n"))
  if (asked.verb === "approve") return await approve(context, dir, asked.args)
  if (asked.verb === "stop") return await stop(context, dir)
  if (asked.verb === EXPLORE_WORD) return await exploreBranch(context, dir, asked.args)
  if (asked.verb === "land") return await land(context, dir)
  if (asked.verb === "merge") return await merge(context, dir)
  if (asked.verb === "publish") return await publish(context, dir)
  if (asked.verb === "decide" || asked.verb === "sign-off") return await proposal(context, dir, asked.verb, asked.args)
  if (asked.verb === "update") return await update(context, dir)
  return await adopt(context, dir, asked.args)
}

export default Plugin.define({
  id: "aidd-tui",
  async setup(context) {
    const [status, setStatus] = createSignal({ lines: [], waits: 0, failed: false })
    const here = () => context.location?.directory ?? "."
    const refresh = async () => setStatus(statusFrom(await run(here(), STATUS_ARGV)))
    // The status view: the lines the CLI printed, in the footer and in a session panel the person opens. A failed list
    // says so in the footer too, and never that nothing waits.
    const footer = context.ui.slot({
      append: "home.footer.status",
      render: () => (
        <Show when={footerLine(status())}>
          <text>{footerLine(status())}</text>
        </Show>
      ),
    })
    const panel = context.ui.slot({
      append: "session.panel",
      render: (props) => (
        <Show when={props.name === "aidd.status"}>
          <box>
            <text>{TITLE}</text>
            <For each={status().lines}>{(line) => <text>{line}</text>}</For>
          </box>
        </Show>
      ),
    })
    await refresh()
    context.keymap.layer(() => ({
      mode: "global",
      priority: 10,
      commands: [
        {
          id: "aidd.verb",
          title: "aidd: your decisions, status, approve, stop, land, publish, merge, decide, sign-off, spike, update, init, help",
          group: "aidd",
          slash: { name: "aidd", arguments: true },
          run: (input) => answered(context, verb(context, input), input),
        },
        {
          id: "aidd.status",
          title: "aidd: what waits on you",
          group: "aidd",
          run: () =>
            answered(
              context,
              (async () => {
                await refresh()
                if (context.ui.panel.open("aidd.status") === false) show(context, status().lines.join("\n"))
              })(),
              "status",
            ),
        },
      ],
      bindings: ["aidd.verb"],
    }))
    return () => {
      footer?.()
      panel?.()
    }
  },
})
