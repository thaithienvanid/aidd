// aidd's plugin for OpenCode V2 (the pure half): the `/aidd` verbs, the argv each verb runs, and the lines the terminal
// draws. It holds no OpenCode call, no filesystem, no clock, and no network, so `node` runs it as it is, and the tests
// pin every answer below. `tui.tsx` beside it holds every call into OpenCode's own terminal.
// One owner for each fact: the status is what `aidd list --waiting-on-me --json` prints, the approval is what
// `aidd approve ... --show` prints, and the record is what the aidd CLI writes. This module composes none of them.
export const DECIDED_VIA = "opencode" // where the record says the person decided: this terminal's own dialog
// The word that names an explore branch, in `/aidd explore <topic>` and the typed `explore branch <topic>`, and the
// branch's prefix: one place each to rename (aidd's own are workitems.EXPLORE_WORD and EXPLORE_PREFIX).
export const EXPLORE_WORD = "explore"
export const EXPLORE_PREFIX = `${EXPLORE_WORD}/`
export const VERBS = ["status", "approve", "stop", "land", "publish", "merge", "decide", "sign-off", EXPLORE_WORD, "update", "init", "help"]
// A verb an older aidd had, and what to type now: it records nothing.
export const RETIRED = {
  ship: "aidd: `/aidd ship` named three steps: `/aidd land` lands this branch on the local trunk, type `publish` to take it off this machine, and `/aidd merge` merges its PR/MR",
}
export const STATUS_ARGV = ["list", "--waiting-on-me", "--json"]
export const TITLE = "aidd: what waits on you"
export const EMPTY = "aidd: nothing is open; describe a change and the agent checks the route"
export const NOT_ADOPTED = "aidd: this folder is not an aidd repository; run `aidd init --harness opencode`"
export const NOTHING_WAITS = "Nothing waits on you."

const text = (value) => (typeof value === "string" ? value : "")

const lines = (value) => (Array.isArray(value) ? value : [])

// The first line aidd said: what a toast shows, since the terminal has no room for the rest.
export function firstLine(said) {
  return text(said).trim().split("\n")[0] || ""
}

// The last line a command printed, for a failure whose reason comes after its progress, such as an installer's.
export function lastLine(said) {
  return text(said).split("\n").map((l) => l.trim()).filter(Boolean).at(-1) || ""
}

// The JSON object aidd printed, or null when it printed anything else.
function jsonObject(said) {
  try {
    const data = JSON.parse(text(said))
    return data && typeof data === "object" && !Array.isArray(data) ? data : null
  } catch {
    return null
  }
}

// `/aidd <verb> [rest]`, read as the person typed it. No verb answers with the menu of the person's decisions; a word
// that is no verb answers with a problem and the help, so a typo never reaches a verb that records something.
export function parseVerb(rest) {
  const words = text(rest).trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return { verb: "menu", args: [] }
  const verb = words[0].toLowerCase()
  if (RETIRED[verb]) return { problem: RETIRED[verb], verb: "help", args: [] }
  if (!VERBS.includes(verb)) return { problem: `aidd: "${words[0]}" is no aidd verb; /aidd help lists them`, verb: "help", args: [] }
  return { verb, args: words.slice(1) }
}

// The help: one line per verb, with what each records.
export function helpLines() {
  return [
    "aidd, in this terminal. Each answers at once, and no turn goes to the agent:",
    "  /aidd                   every decision that is yours, and the words that make it",
    "  /aidd status            what waits on you, and what to type",
    "  /aidd approve [SPEC]    approve a Spec; /aidd approve merge approves this branch",
    "  /aidd approve all       the agent records every approval for you (`and publish`: and publishes)",
    "  /aidd stop              end that standing approval",
    "  /aidd land              land this branch on the local trunk",
    "  /aidd publish           what would leave this machine; type `publish` at the prompt to take it off",
    "  /aidd merge             approve this branch's PR/MR, which merges once aidd/gate passes",
    "  /aidd decide PROP-1 go  record go or no-go on a proposal (add why after it)",
    "  /aidd sign-off PROP-1   sign off a proposal as it reads now, so it may be sent",
    `  /aidd ${EXPLORE_WORD} <topic>   move this worktree to a throwaway branch where every edit is free`,
    "  /aidd update            update the aidd CLI and this repository's aidd files",
    "  /aidd init [flags]      adopt aidd here with `aidd init` (solo unless you name a profile)",
    "  /aidd help              this list",
  ]
}

// `/aidd` alone: every decision that is the person's, one line each: the words to type, the verb, and when it is
// theirs. Claude Code's aidd-mods lists the same (`AIDD_MENU`), and tests/test_opencode.py holds both to one list.
export function menuLines() {
  return [
    "Your decisions. Type the words at the prompt, or run the /aidd verb beside them:",
    "  approve SPEC-1          /aidd approve SPEC-1     a Spec waits on you: approve it as it reads, and the agent builds it",
    "  approve merge           /aidd approve merge      a reviewed branch: your Merge approval of its head",
    "  land it                 /aidd land               a reviewed branch: land it on your local trunk once the gate passes",
    "  publish                 /aidd publish            take this branch off your machine: push it and open its PR/MR",
    "  merge it                /aidd merge              a branch with a PR/MR: approve it, and it merges once aidd/gate passes",
    '  approve all             /aidd approve all        let the agent approve for you until you stop it (add "and publish" or "but major")',
    "  stop approving          /aidd stop               end that standing approval: each decision waits on you again",
    "  decide PROP-1 go        /aidd decide PROP-1 go   a proposal waits on your go or no-go (add why after it)",
    "  sign off PROP-1         /aidd sign-off PROP-1    a proposal is ready to send, as it reads now",
    `  ${EXPLORE_WORD} branch <topic>  /aidd ${EXPLORE_WORD} <topic>    try an idea on a throwaway branch: every edit is free, and nothing merges from it`,
    '"approve" alone approves every Spec that waits on you. /aidd status shows what waits on you now, and /aidd help lists every verb.',
  ]
}

// `/aidd explore <topic>`: the topic, as the typed words take it (letters, digits, `.`, `_`, `-`), or null.
export function exploreAsked(args) {
  const m = new RegExp(`^(?:branch\\s+)?(?:${EXPLORE_PREFIX})?([A-Za-z0-9][A-Za-z0-9._-]{0,60})$`, "i").exec(lines(args).map(String).join(" ").trim())
  return m ? m[1] : null
}

export const EXPLORE_USAGE = `aidd: say \`/aidd ${EXPLORE_WORD} <topic>\`, such as \`/aidd ${EXPLORE_WORD} caching\`: letters, digits, \`.\`, \`_\`, or \`-\``

export function exploreQuestion(branch) {
  return `Move this worktree to the ${EXPLORE_WORD} branch ${branch}? Nothing merges from it as it is, and its edits are free once you type \`${EXPLORE_WORD} branch ${branch.slice(EXPLORE_PREFIX.length)}\`, which aidd records as yours.`
}

// The git commands `/aidd explore` runs, in order: the name git accepts, whether the branch exists, the switch (a new
// branch from here, or the one that exists), and the branch HEAD names after it.
export function exploreArgv(branch, exists) {
  return {
    check: ["check-ref-format", "--branch", branch],
    exists: ["rev-parse", "-q", "--verify", `refs/heads/${branch}`],
    switch: ["switch", ...(exists ? [] : ["-c"]), branch],
    head: ["symbolic-ref", "-q", "--short", "HEAD"],
  }
}

export function exploreLine(branch) {
  return `aidd: this worktree is on ${branch} now, and nothing merges from it as it is. To free its edits, type \`${EXPLORE_WORD} branch ${branch.slice(EXPLORE_PREFIX.length)}\` at the prompt, which aidd records as yours. To keep the work, rename the branch with \`git branch -m <name>\``
}

// What changed outside the agent's session since the person's last decision, as a preview (`--show`) lists it: the
// person's answer takes it in as theirs, so a dialog shows it before they answer. The lines Claude Code's dialogs show
// too (aidd-mods `outsideLines`).
export function outsideOf(printed) {
  const data = printed && typeof printed === "object" ? printed : {}
  return lines(data.outside_changes)
    .filter((c) => c && typeof c === "object")
    .map((c) => ({ what: oneLine(c.what, 300), restore: oneLine(c.restore, 300), held: c.held === true, guard: c.guard === true }))
}

export function outsideText(changes) {
  if (!lines(changes).length) return ""
  // One that could stop the guard itself stays held whatever this dialog answers: aidd's own dialog or the terminal.
  const tag = (c) => (c.guard ? " (it could stop the guard, so this answer leaves it held: aidd's own dialog or your terminal takes it in)" : c.held ? " (it weakens the guard)" : "")
  const each = changes.map((c) => `\n- ${c.what}${tag(c)} (to put it back: ${c.restore})`).join("")
  return `\n\nSince your last decision, this also changed outside the agent's session, and counts as yours with this answer:${each}`
}

// The question the Spec approval dialog asks: each Spec's id and commit first, so a long title can never push them out
// of view, then every warning (a test changed since the last approval, implementation already there), and what
// changed outside the session.
export function specQuestion(list) {
  const each = list.map((one) => `${one.id} at ${one.shown.commit.slice(0, 12)}: ${one.shown.title}${lines(one.shown.warnings).map((w) => `\n  ! ${w}`).join("")}`)
  const changed = outsideText([...new Map(list.flatMap((one) => one.shown.outside).map((c) => [c.what, c])).values()])
  return `${each.join("\n")}${changed}\n\nApprove ${list.length === 1 ? list[0].id : `these ${list.length} Specs`}?`
}

// The question a merge or land dialog asks: the branch and its head first, then every gate warning, what changed
// outside the session, and the question itself (`ask`).
export function mergeQuestion(shown, ask) {
  const warn = lines(shown.warnings).map((w) => `\n  ! ${w}`).join("")
  return `${shown.branch} at ${shown.head.slice(0, 12)}${warn}${outsideText(shown.outside)}\n\n${ask}`
}

// The line aidd adds after a decision it recorded when something changed outside the session since the last one, or "".
export function countedLine(said) {
  return text(said).split("\n").map((l) => oneLine(l, 1000)).find((l) => l.startsWith("Since your last decision")) || ""
}

// The person's standing approval in force (`aidd list --json`'s `standing`), as the line that says so and how to end
// it, or "" when none is. Claude Code's pane says the same (aidd-mods `standingNote`).
export function standingLine(listed) {
  const s = listed && typeof listed === "object" ? listed.standing : null
  if (!s || typeof s !== "object") return ""
  const scope = text(s.scope)
  const what = `all${scope.includes("and-publish") ? " and publishing" : ""}${scope.endsWith("but-major") ? " but major" : ""}`
  const since = oneLine(s.since, 40).slice(0, 16).replace("T", " ")
  return `Standing approval is on, so aidd records your approvals. To end it: \`/aidd stop\`, or type \`stop approving\`. It covers ${what}, since ${since}.`
}

// The product-level work this repository keeps (`aidd list --json`'s `living`), as one line, or "" when it keeps none.
// Claude Code's pane says the same (aidd-mods `livingNote`).
export function livingLine(listed) {
  const living = listed && typeof listed === "object" && Array.isArray(listed.living) ? listed.living : []
  const parts = living
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const kind = text(item.kind).replace(/-/g, " ")
      const files = typeof item.files === "number" ? `, ${item.files} files` : ""
      const opened = text(item.opened_by)
      return kind ? `${kind} in ${text(item.home)}${files}${opened ? ` (\`${opened}\` opens it)` : ""}` : ""
    })
    .filter((part) => part !== "")
  return parts.length > 0 ? `Product-level work: ${parts.join("; ")}.` : ""
}

// The aidd command that does a verb's work in a person's own terminal, for when the verb could not finish here.
const IN_A_TERMINAL = {
  status: "aidd list --waiting-on-me",
  approve: "aidd approve",
  stop: "aidd approve stop",
  land: "aidd land",
  publish: "aidd publish --show",
  merge: "aidd approve merge",
  decide: "aidd proposal decide",
  "sign-off": "aidd proposal sign-off",
  [EXPLORE_WORD]: `git switch -c ${EXPLORE_PREFIX}<topic>`,
  update: "aidd self-update",
  init: "aidd init",
  help: "aidd --help",
}

// What a verb that threw says: why, and the command that always works in a terminal. A decision is recorded only by a
// step that said so, and `aidd list --waiting-on-me` shows what still waits.
export function failedLine(reason, input) {
  const why = oneLine(firstLine(String(reason ?? "")), 200) || "the command failed"
  const command = IN_A_TERMINAL[parseVerb(input).verb] || IN_A_TERMINAL.status
  return `aidd: ${why}; run \`${command}\` in a terminal`
}

// One step `aidd list` printed, as the line the person reads: what it is, and what to type. The `what` aidd prints may
// name the id again; the id is said once.
function stepLine(step) {
  const id = text(step?.id)
  const what = text(step?.what)
  const said = id && what.startsWith(`${id} `) ? what.slice(id.length + 1) : what
  const how = oneLine(step?.how, 200)
  // A step with no id, such as aidd's "nothing waits on you", is its words alone.
  return `${id ? `${oneLine(id, 40)}: ` : ""}${oneLine(said, 200)}${how ? ` — ${how}` : ""}`
}

// The steps `aidd list` printed, each with the folder it named when the JSON is keyed by folder.
function stepsOf(listed) {
  const data = listed && typeof listed === "object" ? listed : {}
  const repos = data.repos && typeof data.repos === "object" && !Array.isArray(data.repos) ? Object.entries(data.repos) : null
  if (repos) return repos.flatMap(([folder, steps]) => lines(steps).map((step) => ({ folder: oneLine(folder, 80), step })))
  return lines(data.steps).map((step) => ({ folder: "", step }))
}

// The lines the status view draws, from `aidd list --waiting-on-me --json`: one per step that waits on the person, and
// each repository it named when the JSON is keyed by folder.
export function statusLines(listed) {
  const out = stepsOf(listed).map(({ folder, step }) => `${folder ? `${folder}  ` : ""}${stepLine(step)}`)
  return out.length > 0 ? out : [NOTHING_WAITS]
}

// What the status view shows from one run of `aidd list --waiting-on-me --json`: its lines, how many steps wait on the
// person, and whether aidd could say. A failed run shows aidd's reason, as Claude Code's pane does, and never "Nothing
// waits on you". aidd's own "nothing ..." step counts as no wait.
export function statusFrom(got) {
  const data = got?.failed ? null : jsonObject(got?.said)
  if (!data) {
    const reason = got?.failed ? oneLine(firstLine(got?.said), 200) : "aidd printed something that is not JSON"
    return { lines: [`aidd could not say what waits on you: ${reason || "it printed nothing"}`], waits: 0, failed: true }
  }
  const waits = stepsOf(data).filter(({ step }) => !text(step?.code).startsWith("nothing")).length
  const standing = standingLine(data)
  const living = livingLine(data)
  return {
    lines: [...(standing ? [standing] : []), ...statusLines(data), ...(living ? [living] : [])],
    waits,
    failed: false,
    ...(standing ? { standing } : {}),
  }
}

// The footer's one line: how many wait on the person, that aidd could not say, or nothing at all.
export function footerLine(status) {
  if (status?.failed) return "aidd: could not say what waits on you (/aidd status)"
  const stop = status?.standing ? " · standing approval on: /aidd stop ends it" : ""
  return status?.waits > 0 ? `aidd: ${status.waits} wait on you (/aidd status)${stop}` : stop ? `aidd:${stop.slice(2)}` : ""
}

// What `aidd approve spec|merge --show` printed, kept as the person must see it: the title, and the exact commit. The
// problems stop the dialog: while aidd says the change is not ready, this module never builds the confirmed argv.
export function preview(kind, printed) {
  const data = printed && typeof printed === "object" ? printed : {}
  const problems = lines(data.problems).map((p) => oneLine(p, 300))
  const outside = outsideOf(data)
  const seen = /^[0-9a-f]{64}$/.test(text(data.outside_hash)) ? text(data.outside_hash) : ""
  const warnings = lines(data.warnings).slice(0, 5).map((w) => oneLine(w, 300)).filter(Boolean)
  if (kind === "merge") return { head: hex(data.head), branch: oneLine(data.branch), warnings, outside, seen, problems }
  return { id: oneLine(data.id, 40), title: oneLine(data.title), commit: hex(data.commit), warnings, outside, seen, problems }
}

// The characters that can redraw a terminal or reorder what a person reads: the C0 and C1 controls (line breaks and ESC
// among them), DEL, the bidi marks, embeddings, overrides, and isolates, and the Unicode line and paragraph separators.
// The CLI's `plain()` (src/aidd/cli/commands/decide.py) owns this set; Claude Code's `clean` (aidd-mods) uses it too.
const UNSAFE = / *(?:[\u0000-\u001f\u007f-\u009f\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069] *)+/g

// A field the repository wrote (a Spec's title, a branch's name), as one short plain line: each run of those
// characters, with the spaces beside it, is one space, so nothing can move the id and the commit the dialog binds out
// of view, or draw a question of its own.
export function oneLine(value, max = 80) {
  const flat = text(value).replace(UNSAFE, " ").trim()
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat
}

// A commit as aidd prints it: hex digits only, or nothing.
function hex(value) {
  return /^[0-9a-f]{7,64}$/.test(text(value)) ? text(value) : ""
}

// The JSON aidd printed, or {} when it printed something else: the CLI's line is the answer either way.
export function parsed(said) {
  try {
    const data = JSON.parse(text(said))
    return data && typeof data === "object" ? data : {}
  } catch {
    return {}
  }
}

// The preview from one run of `aidd ... --show`. A run that failed, or printed no commit to bind, is a problem, with
// aidd's own reason when it gave one, so the dialog never asks to approve a commit it could not name. A failed run's
// JSON stands only when it names its own problems, since Claude Code's pane stops on any failed run too.
export function previewOf(kind, got) {
  const data = parsed(got?.said)
  const shown = preview(kind, data)
  if (shown.problems.length > 0) return shown
  if (!got?.failed && (kind === "merge" ? shown.head : shown.commit)) return shown
  const reason = oneLine(firstLine(got?.stderr) || (Object.keys(data).length === 0 ? firstLine(got?.said) : ""), 300)
  return { ...shown, problems: [reason || (got?.failed ? "aidd stopped before it named a commit to approve" : "aidd printed no commit to approve")] }
}

export function isReady(shown) {
  return Boolean(shown) && lines(shown.problems).length === 0
}

const confirmed = (...argv) => [...argv, "--decided-via", DECIDED_VIA]

// What the dialog showed changed outside the session, by its digest, so the answer takes in exactly that.
const seenArgv = (seen) => (/^[0-9a-f]{64}$/.test(text(seen)) ? ["--outside-hash", text(seen)] : [])

// The argv that records a Spec approval for exactly the commit the dialog showed.
export function approveArgv(id, commit, seen = "") {
  return confirmed("approve", "spec", String(id), "--confirmed", String(commit), ...seenArgv(seen))
}

// The argv that records this branch's Merge approval for exactly the head the dialog showed; `autoMerge` also turns on
// the platform's own auto-merge.
export function mergeArgv(shown, autoMerge = false) {
  return confirmed("approve", "merge", "--confirmed", text(shown?.head), ...(autoMerge ? ["--auto-merge"] : []), ...seenArgv(shown?.seen))
}

// The argv that lands this branch on the local trunk, for the head the dialog showed.
export function landArgv(shown) {
  return confirmed("land", "--confirmed", text(shown?.head), ...seenArgv(shown?.seen))
}

// `/aidd decide PROP-1 go [why]` or `/aidd sign-off PROP-1`, read as aidd-mods reads them (`proposalAsked`): the
// proposal, and for decide the decision and its reason. Anything else is null, so nothing runs.
export function proposalAsked(verb, args) {
  const [id = "", second = "", ...more] = lines(args).map(String)
  if (!/^[A-Za-z][A-Za-z0-9]*-\d+$/.test(id)) return null
  if (verb === "sign-off") return second === "" ? { verb, id: id.toUpperCase(), decision: null, reason: "" } : null
  const decision = second.toLowerCase()
  if (verb !== "decide" || (decision !== "go" && decision !== "no-go")) return null
  return { verb, id: id.toUpperCase(), decision, reason: more.join(" ").replace(/^because\s+/i, "").slice(0, 500) }
}

export const PROPOSAL_USAGE = "aidd: say `/aidd decide PROP-1 go` (or no-go, with why after it), or `/aidd sign-off PROP-1`"

// The flags and the words after `--` that name one proposal decision, so a reason can never read as a flag.
const reasonFlag = (asked) => (asked.reason ? [`--reason=${asked.reason}`] : [])
const proposalTail = (asked) => ["--", asked.id, ...(asked.decision === null ? [] : [asked.decision])]

// What `/aidd decide` and `/aidd sign-off` run first: what the person decides, as JSON, recording nothing.
export function proposalShowArgv(asked) {
  return ["proposal", asked.verb, "--show", ...reasonFlag(asked), ...proposalTail(asked)]
}

// What `aidd proposal decide|sign-off --show` printed, kept as the person must see it. A failed run, aidd's problems,
// or a sign-off with no hash to bind stops the dialog, so it never asks to record what aidd could not name.
export function proposalPreviewOf(asked, got) {
  const data = parsed(got?.said)
  const shown = { id: oneLine(data.id, 40), title: oneLine(data.title), hash: hex(data.hash), problems: lines(data.problems).map((p) => oneLine(p, 300)) }
  if (shown.problems.length > 0) return shown
  if (!got?.failed && shown.id && (asked.decision !== null || shown.hash)) return shown
  const reason = oneLine(firstLine(got?.stderr) || (Object.keys(data).length === 0 ? firstLine(got?.said) : ""), 300)
  return { ...shown, problems: [reason || (got?.failed ? "aidd stopped before it named the proposal" : "aidd printed no proposal to decide")] }
}

// The dialog's question: the id first, so a long title can never push it out of view.
export function proposalQuestion(asked, shown) {
  const what = asked.decision === null ? `Sign off ${asked.id}, as it reads now, so it may be sent?` : `Record ${asked.decision} on ${asked.id}?`
  return `${shown.id || asked.id}: ${shown.title}\n\n${what}`
}

// The argv that records the person's answer: for decide exactly the decision they saw, for a sign-off exactly the hash
// the preview named, so a proposal that changed since is refused.
export function proposalArgv(asked, shown) {
  const value = asked.decision ?? text(shown?.hash)
  return ["proposal", asked.verb, ...reasonFlag(asked), "--confirmed", value, "--decided-via", DECIDED_VIA, ...proposalTail(asked)]
}

// What a recorded proposal decision says: aidd's `Recorded ...` line, after the card it prints.
export function recordedLine(said) {
  return text(said).split("\n").find((l) => l.startsWith("Recorded")) || firstLine(said)
}

// Where a branch stands for `/aidd merge`: its pull or merge request merges on the platform, or nothing is there yet.
export const NOT_ON_A_PLATFORM =
  "aidd: this branch is not on a platform yet, so there is no PR/MR to merge: `/aidd land` lands it on the local trunk, or type `publish` to push it and open one"

// Whether `aidd land --show` says the branch's pull or merge request merges on the platform.
export function mergesOnPlatform(printed) {
  return Boolean(printed && typeof printed === "object" && printed.merges_on_platform === true)
}

// What `/aidd publish` shows: the plan alone. Publishing is the person's, and their typed `publish` records it, since
// this terminal never pushes.
export function publishShowArgv() {
  return ["publish", "--show"]
}

// What `/aidd publish` says, in Claude Code's words: what would leave this machine and how to publish it, or why aidd
// could not say. Every field is plain, since a commit subject is an agent's words.
export function publishFrom(got) {
  const data = got?.failed ? null : jsonObject(got?.said)
  if (!data) {
    const reason = got?.failed ? oneLine(firstLine(got?.said), 200) : "aidd printed something that is not JSON"
    return `aidd could not say what would leave this machine: ${reason || "it printed nothing"}`
  }
  const branch = oneLine(data.branch)
  if (!branch) return "aidd said nothing about what would leave this machine."
  const n = typeof data.commits === "number" ? data.commits : 0
  const pr = data.pull_request === true ? `, then a pull request into ${oneLine(data.base)}` : ""
  return [
    `Would leave this machine: ${branch} at ${oneLine(data.head).slice(0, 12)} to ${oneLine(data.remote)}/${oneLine(data.to)}${pr} (${n} commit${n === 1 ? "" : "s"} the remote lacks)`,
    ...lines(data.shown).map((c) => `  ${oneLine(c, 200)}`),
    ...outsideOf(data).map((c) => `Since your last decision, ${c.what}: it counts as yours when you publish (to put it back: ${c.restore})`),
    "To publish it, type `publish` at the prompt: aidd records it from your words, and the agent runs `aidd publish`. Or run `aidd publish` in your own terminal.",
  ].join("\n")
}

// The scope of a standing approval from the words after `/aidd approve all`: `and publish`, and `but major`.
export function standingScope(words) {
  const said = words.map((w) => String(w).toLowerCase()).join(" ")
  return "all" + (/\band publish\b/.test(said) ? "-and-publish" : "") + (/\b(but|except) major\b/.test(said) ? "-but-major" : "")
}

// A standing approval: every approval for the person until they stop it, and its end. `stop` records a decision too, so
// nothing confirms it. `show` is what the dialog shows first: what changed outside the session, which the answer takes in.
export function standingArgv(scope, show = false, seen = "") {
  if (scope === "stop") return ["approve", "stop"]
  const flags = [...(scope.includes("and-publish") ? ["--and-publish"] : []), ...(scope.endsWith("but-major") ? ["--but-major"] : [])]
  return show ? ["approve", "all", ...flags, "--show"] : confirmed("approve", "all", ...flags, "--confirmed", scope, ...seenArgv(seen))
}

// What `/aidd update` runs: the dry run it shows, then the same update once the person agrees.
export function updateChecks() {
  return [["self-update", "--check"], ["upgrade"]]
}

// What `aidd self-update --check` said: its line, whether it would change anything, and whether it said this CLI is the
// latest. Any other line, such as a checkout's, leaves the CLI unknown, never current.
export function cliUpdate(said) {
  const line = oneLine(firstLine(said), 300)
  return { line, isDue: /^would update /.test(line), isCurrent: / is up to date: the latest is /.test(line) }
}

// The check from one run: before the first release, or offline, it fails, and `failed` says why, so a failed check
// never reads as up to date.
export function cliChecked(got) {
  return got?.failed
    ? { line: "", isDue: false, isCurrent: false, failed: oneLine(firstLine(got.said), 300) || "the check failed" }
    : cliUpdate(got?.said)
}

// What `aidd upgrade` (a dry run) said: the changes it lists, or none when the repository already matches this aidd.
export function repoUpdate(said) {
  const lines = text(said).split("\n").map((l) => oneLine(l, 300)).filter((l) => l !== "")
  if (lines.length === 0 || /^nothing to update/.test(lines[0])) return { lines: [], isDue: false }
  return { lines: lines.filter((l) => !/^(The CLI itself|The Claude Code plugins):/.test(l)), isDue: true }
}

// The dry run from one run: a failed one is said, never dropped.
export function repoChecked(got) {
  return got?.failed ? { lines: [], isDue: false, failed: oneLine(firstLine(got.said), 300) || "the dry run failed" } : repoUpdate(got?.said)
}

// Why this repository's aidd files don't update on a CLI that may be behind, in Claude Code's words (aidd-mods
// `REPO_WAITS`): `aidd upgrade` writes the files of the CLI that runs it, so an older CLI would write older files.
export const REPO_WAITS =
  "This repository's aidd files wait, because aidd can't tell that this CLI is current, and an older one would write older files over newer ones. Update the CLI (docs/INSTALL.md), then run `aidd upgrade --yes`."

// What each check found, in Claude Code's words (aidd-mods `checkParts`): what would change, why a check could not run,
// or that aidd is up to date.
export function checkParts(cli, repo) {
  if (!cli.isDue && !repo.isDue && !cli.failed && !repo.failed) return [`aidd is up to date. ${cli.line}`.trim()]
  const parts = []
  if (cli.failed) parts.push(`aidd could not check for a new CLI: ${cli.failed}`)
  else if (cli.isDue) parts.push(`The aidd CLI: ${cli.line.replace(/^would /, "")}`)
  else if (cli.line) parts.push(cli.line)
  if (repo.failed) parts.push(`aidd could not check this repository's files: ${repo.failed}`)
  else if (repo.isDue) {
    const shown = repo.lines.slice(0, 8)
    const more = repo.lines.length - shown.length
    parts.push(["This repository's aidd files (commit them on a branch afterwards):", ...shown.map((l) => `  ${l}`), ...(more > 0 ? [`  and ${more} more`] : [])].join("\n"))
    if (!cli.isDue && !cli.isCurrent) parts.push(REPO_WAITS)
  } else parts.push("This repository's aidd files are up to date.")
  return parts
}

// The update dialog: what changes, and where; the person answers once for all of it.
export function updateQuestion(cli, repo) {
  return [...checkParts(cli, repo), "Update now?"].join("\n\n")
}

// What `/aidd update` says when nothing is due: that aidd is up to date, or why a check could not run, as a failure.
export function nothingDue(cli, repo) {
  return { message: checkParts(cli, repo).join(" "), failed: Boolean(cli.failed || repo.failed) }
}

// What runs once the person agrees: the CLI first, so the new aidd brings this repository's files up to itself, and
// only what is due. The repository's files update only on a CLI known to be current: one the check called the latest,
// or one the update brings up (stepWaits), since an older CLI would write older files (REPO_WAITS).
export function updateSteps(cli, repo) {
  return [...(cli.isDue ? [["self-update"]] : []), ...(repo.isDue && (cli.isDue || cli.isCurrent) ? [["upgrade", "--yes"]] : [])]
}

// Why a step does not run, or null: the files' upgrade waits once the CLI update before it failed.
export function stepWaits(argv, failed) {
  return argv[0] === "upgrade" && failed ? REPO_WAITS : null
}

// What one update step did, in the words Claude Code's `/aidd update` uses. OpenCode loads its plugins when it starts,
// so a change to aidd's own plugin files waits for a restart.
// The installer prints its progress first, so a failed `self-update`'s reason is the last line it printed.
export function updateSaid(argv, got, repo) {
  if (argv[0] === "self-update") {
    if (!got.failed) return oneLine(firstLine(got.said), 300)
    return `The CLI was not updated: ${oneLine(lastLine(got.stderr) || lastLine(got.said), 300).replace(/\.$/, "")}.`
  }
  if (got.failed) return `This repository was not updated: ${oneLine(firstLine(got.said), 300)}`
  const restart = repo.lines.some((l) => l.includes(".opencode/plugins/")) ? " Restart OpenCode to load the new aidd plugin." : ""
  return `This repository's aidd files changed: commit them on a branch, as any change.${restart}`
}

// What `/aidd init` runs: the dry run it shows, then the adopt itself.
export function initCheckArgv() {
  return ["init", "--dry-run"]
}

// The flags `/aidd init` passes to `aidd init`: solo unless a profile is named, since solo needs no approver list.
export function initArgs(...given) {
  const words = given.join(" ").split(/\s+/).filter(Boolean)
  return words.some((w) => w === "--profile" || w.startsWith("--profile=")) ? words : ["--profile", "solo", ...words]
}
