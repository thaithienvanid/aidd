import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Section, Snapshot, Step, Task } from '../types'
import {
  about,
  AIDD_HELP,
  aiddVerb,
  approvable,
  approvalIds,
  approvalQuestion,
  cliUpdate,
  installArgs,
  proposalAsked,
  type ProposalAsk,
  exploreNote,
  repoUpdate,
  standingAsked,
  standingNote,
  UPDATE_TIMEOUT_MS,
  updateQuestion,
  autopilot as pilotOf,
  cells,
  type Cell,
  decisions,
  flowLine,
  shape as shapeOf,
  firstLine,
  frontTitle,
  isInside,
  isShip,
  json,
  map,
  mergePreview,
  mergeQuestion,
  NOT_FOUND,
  preview,
  SHIP_TIMEOUT_MS,
  shipQuestion,
  specsFolder,
  steps,
  TIMEOUT_MS,
  until,
} from './aidd'
import type { Approvable, Preview } from './aidd'

// `/aidd status` opens a pane: drawn by the mod, never written to the transcript,
// so none of it reaches the model. The aidd engine decides; the pane only shows.

const PANE = 'aidd-status'
const TITLE = 'aidd'
// Below NARROW the key hints shorten; a row's own columns follow its room (MIN_TITLE, MAX_NOTE).
const NARROW = 56
const MIN_TITLE = 16
const MAX_NOTE = 24

const shot = atom({ plugin: 'aidd-mods', key: 'snapshot' } as const, null)
const loading = atom({ plugin: 'aidd-mods', key: 'isLoading' } as const, false)
const selected = atom({ plugin: 'aidd-mods', key: 'selected' } as const, null)
// The Initiative or Epic the person chose to see alone; null shows everything.
const focus = atom({ plugin: 'aidd-mods', key: 'focus' } as const, null)
// The Task opened from the chosen Spec's detail card; null shows the Spec itself.
const opened = atom({ plugin: 'aidd-mods', key: 'task' } as const, null)
// The Plan section's lines, at most: the rest are counted.
const PLAN_LINES = 6
// The rows the detail card takes, about: the Spec's description and fields, and a few Tasks.
const DETAIL_ROWS = 16


// Running aidd and reading the Spec files: every engine call sits in this file.

async function run($: EngineInterface, root: string, argv: readonly string[], timeoutMs = TIMEOUT_MS): Promise<Section<string>> {
  try {
    const { exitCode, stdout, stderr } = await $.process.run(argv, { cwd: root, timeoutMs })

    return exitCode === 0
      ? { isOk: true, value: stdout }
      : { isOk: false, error: firstLine(stderr) || firstLine(stdout) || `\`${argv.join(' ')}\` exited ${exitCode}` }
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    if (/timed? ?out|still running/i.test(reason)) {
      return { isOk: false, error: `\`${argv.join(' ')}\` took over ${timeoutMs / 1000} seconds` }
    }

    return { isOk: false, error: NOT_FOUND }
  }
}

// Each item's title and what its Spec says (`about`), from one read of its file.
async function titled($: EngineInterface, root: string, list: Step[]): Promise<Step[]> {
  const read = async (step: Step): Promise<Step> => {
    if (!isInside(step.where)) {
      return step
    }
    try {
      const source = await $.fs.read(`${root}/${step.where}`)
      return { ...step, title: frontTitle(source), about: about(source) }
    } catch {
      return step
    }
  }

  return Promise.all(list.map(read))
}

async function snapshot($: EngineInterface): Promise<Snapshot> {
  // The project root, not the shell's directory: a `cd` in the session moves the latter.
  const root = await $.session.root()
  const [head, branch, waiting, pilot, shaped] = await Promise.all([
    run($, root, ['git', 'rev-parse', '--abbrev-ref', 'HEAD']),
    run($, root, ['aidd', 'list', '--branch', '--json']),
    run($, root, ['aidd', 'list', '--waiting-on-me', '--json']),
    run($, root, ['aidd', 'autopilot', 'status', '--json']),
    run($, root, ['aidd', 'goal', 'list', '--json']),
  ])
  const at = await $.clock.now()

  const withTitles = async (section: Section<Step[]>): Promise<Section<Step[]>> =>
    section.isOk ? { isOk: true, value: await titled($, root, section.value) } : section

  const listed = await withTitles(map(json(branch), steps))
  const parsedBranch = json(branch)
  const mine = await withTitles(map(json(waiting), steps))

  return {
    root,
    head: head.isOk ? head.value.trim() : '',
    at,
    branch: listed,
    waiting: mine,
    autopilot: map(json(pilot), status => pilotOf(status, at)),
    shape: map(json(shaped), shapeOf),
    standing: parsedBranch.isOk ? [exploreNote(parsedBranch.value), standingNote(parsedBranch.value)].filter(Boolean).join(' · ') || null : null,
  }
}

async function refresh($: EngineInterface): Promise<void> {
  await update($, loading, () => true)
  try {
    const next = await snapshot($)
    await update($, shot, () => next)
  } finally {
    await update($, loading, () => false)
  }
}

const APPROVE = 'Approve'
const NOT_NOW = 'Not now'

// Approving from the prompt. The person types "approve SPEC-1": their own words are the approval, so this mod, not
// the model, records it at once for exactly the hash it shows (`aidd approve spec --confirmed`), and says what it
// approved. The model never sees the prompt. When the request did not come from the person's keyboard (`askFirst`:
// the SDK, or the agent through the skill), Claude Code's own dialog asks the person first. aidd's guard denies the
// model's own `aidd approve`.
async function approveFromPrompt($: EngineInterface, root: string, ids: string[], open: Approvable[], askFirst = false): Promise<void> {
  const refOf = (id: string): string[] => {
    const branch = open.find(item => item.id === id)?.branch

    return branch ? ['--ref', branch] : []
  }
  const ready: Preview[] = []
  const skipped: string[] = []
  for (const id of ids) {
    const said = map(json(await run($, root, ['aidd', 'approve', 'spec', id, ...refOf(id), '--show'])), preview)
    if (!said.isOk) {
      skipped.push(`${id}: ${said.error}`)
    } else if (said.value.problems.length > 0) {
      skipped.push(`${id}: ${said.value.problems[0]}`)
    } else {
      ready.push(said.value)
    }
  }
  if (ready.length === 0) {
    $.ui.toast(`Nothing was approved. ${skipped.join(' · ')}`, { timeoutMs: 12_000 })
    return
  }
  // The safe answer first, and only the exact label approves: a dialog dismissed, answered by the idle timeout, or
  // answered in free text ("Other") records nothing.
  if (askFirst && !(await confirmed($, approvalQuestion(ready), 'Approve'))) {
    $.ui.toast('Not approved: nothing was recorded.')
    return
  }
  const approved: string[] = []
  for (const p of ready) {
    // One at a time: each approval moves the same ref.
    const said = await run($, root, ['aidd', 'approve', 'spec', p.id, ...refOf(p.id), '--confirmed', p.hash])
    if (said.isOk) {
      approved.push(askFirst ? p.id : `${p.id} at hash ${p.hash.slice(0, 12)}`)
    } else {
      skipped.push(`${p.id}: ${said.error}`)
    }
  }
  const done = approved.length > 0 ? `Approved ${approved.join(', ')}.` : 'Nothing was approved.'
  $.ui.toast([done, ...skipped].join(' '), { timeoutMs: skipped.length > 0 || !askFirst ? 12_000 : 6_000 })
  if (await isOpen($)) {
    await refresh($)
  }
}

// Claude Code's own dialog: the safe answer first, and only the exact label confirms. A dialog dismissed, answered by
// the idle timeout, or answered in free text ("Other") confirms nothing.
async function confirmed($: EngineInterface, question: string, header: string): Promise<boolean> {
  try {
    return (await $.ui.ask(question, { header, options: [NOT_NOW, APPROVE] })) === APPROVE
  } catch {
    return false
  }
}

// "approve the merge", typed by the person: recorded at once, for this checkout's branch at its head; a dialog first
// when the request did not come from their keyboard (`askFirst`).
// With `autoMerge` (the person's "ship it" where a platform merges), the pull request's auto-merge too.
async function approveMergeFromPrompt($: EngineInterface, root: string, askFirst = false, autoMerge = false): Promise<void> {
  const said = map(json(await run($, root, ['aidd', 'approve', 'merge', '--show'])), mergePreview)
  if (!said.isOk || said.value.problems.length > 0) {
    $.ui.toast(`Nothing was approved. ${said.isOk ? said.value.problems[0] : said.error}`, { timeoutMs: 12_000 })
    return
  }
  const p = said.value
  if (askFirst && !(await confirmed($, mergeQuestion(p), 'Approve'))) {
    $.ui.toast('Not approved: nothing was recorded.')
    return
  }
  const done = await run($, root, ['aidd', 'approve', 'merge', '--confirmed', p.head, ...(autoMerge ? ['--auto-merge'] : [])])
  const still = p.failing.length > 0 ? ` The gate still fails on ${p.failing.join(', ')}: the merge waits for that fix.` : ''
  // With auto-merge, aidd's own last line says whether it is on; otherwise the pane names the head it recorded.
  const recorded = autoMerge ? done.isOk && done.value.trim().split('\n').pop() : ''
  const approved = `Approved merging ${p.branch} at ${p.head.slice(0, 12)}.${recorded ? ` ${recorded}` : ''}${still}`
  $.ui.toast(done.isOk ? approved : `Nothing was approved. ${done.error}`, { timeoutMs: done.isOk ? 8_000 : 12_000 })
  if (await isOpen($)) {
    await refresh($)
  }
}

// "ship it", typed by the person: `aidd ship` runs the tests again and lands this head; a dialog first when the
// request did not come from their keyboard (`askFirst`).
async function shipFromPrompt($: EngineInterface, root: string, askFirst = false): Promise<void> {
  const said = map(json(await run($, root, ['aidd', 'ship', '--show'])), mergePreview)
  if (said.isOk && said.value.mergesOnPlatform) {
    // The pull request merges on the platform: "ship it" is the Merge approval there, with its auto-merge.
    await approveMergeFromPrompt($, root, askFirst, true)
    return
  }
  if (!said.isOk || said.value.problems.length > 0) {
    $.ui.toast(`Nothing was shipped. ${said.isOk ? said.value.problems[0] : said.error}`, { timeoutMs: 12_000 })
    return
  }
  const p = said.value
  if (askFirst && !(await confirmed($, shipQuestion(p), 'Ship'))) {
    $.ui.toast('Not shipped: nothing changed.')
    return
  }
  $.ui.toast(`Shipping ${p.branch}: running the tests on what lands…`)
  const done = await run($, root, ['aidd', 'ship', '--confirmed', p.head], SHIP_TIMEOUT_MS)
  $.ui.toast(done.isOk ? `Shipped ${p.branch} into ${p.baseBranch}.` : `Not shipped. ${done.error}`, { timeoutMs: 12_000 })
  if (await isOpen($)) {
    await refresh($)
  }
}

// What a typed "approve …" or `/aidd approve …` approves: the Specs named, the merge, or what waits on you. Returns
// what to tell the person when nothing can be asked, else undefined once the dialog is on its way.
async function approveAsked($: EngineInterface, root: string, asked: string[] | 'merge', askFirst = false): Promise<string | undefined> {
  if (asked === 'merge') {
    $.clock.after(0, () => {
      approveMergeFromPrompt($, root, askFirst).catch(() => $.ui.toast('aidd could not record the approval: run `aidd approve merge` in a terminal.'))
    })
    return undefined
  }
  const waiting = map(json(await run($, root, ['aidd', 'list', '--waiting-on-me', '--json'])), approvable)
  const open = waiting.isOk ? waiting.value : []
  const ids = asked.length > 0 ? asked : open.map(item => item.id)
  if (ids.length === 0) {
    return 'Nothing waits on your approval.'
  }
  $.clock.after(0, () => {
    approveFromPrompt($, root, ids, open, askFirst).catch(() => $.ui.toast('aidd could not record the approval: run `aidd approve spec <ID>` in a terminal.'))
  })
  return undefined
}

const UPDATE = 'Update'
const INSTALL = 'Install'

// `/aidd update`: the CLI (`aidd self-update`) and this repository's aidd files (`aidd upgrade --yes`), after one
// dialog that names both. The repository's files change in the working tree; the person commits them on a branch.
async function updateFromCommand($: EngineInterface, root: string): Promise<string> {
  const [checked, planned] = await Promise.all([run($, root, ['aidd', 'self-update', '--check']), run($, root, ['aidd', 'upgrade'])])
  if (!checked.isOk && checked.error === NOT_FOUND) {
    return NOT_FOUND
  }
  const cli = checked.isOk ? cliUpdate(checked.value) : { line: checked.error, isDue: false }
  const repo = planned.isOk ? repoUpdate(planned.value) : { lines: [], isDue: false }
  if (!cli.isDue && !repo.isDue) {
    return `aidd is up to date. ${cli.line}`
  }
  let answer = ''
  try {
    answer = await $.ui.ask(updateQuestion(cli, repo), { header: 'Update', options: [NOT_NOW, UPDATE] })
  } catch {
    answer = ''
  }
  if (answer !== UPDATE) {
    return 'Nothing was updated.'
  }
  const said: string[] = []
  if (cli.isDue) {
    $.ui.toast('Updating the aidd CLI…')
    const done = await run($, root, ['aidd', 'self-update'], UPDATE_TIMEOUT_MS)
    if (!done.isOk) {
      return `The CLI was not updated: ${done.error}`
    }
    said.push(firstLine(done.value))
  }
  if (repo.isDue) {
    const done = await run($, root, ['aidd', 'upgrade', '--yes'], UPDATE_TIMEOUT_MS)
    said.push(done.isOk ? 'This repository\'s aidd files changed: commit them on a branch, as any change.' : `This repository was not updated: ${done.error}`)
  }
  return [...said, 'Run /reload-plugins to load the new plugins.'].join(' ')
}

// A standing approval ("approve all", "automate", "but major") or its end ("stop approving"): typed by the person, their
// words record it at once; from elsewhere, the dialog asks first. Ending one never asks: it only takes approval back.
async function standingFromPrompt($: EngineInterface, root: string, asked: 'all' | 'all-but-major' | 'stop', askFirst = false): Promise<string> {
  if (asked === 'stop') {
    const done = await run($, root, ['aidd', 'approve', 'stop'])
    return done.isOk ? firstLine(done.value) : `aidd could not stop it: ${done.error}`
  }
  const what = asked === 'all' ? 'every Spec approval and Merge approval' : 'every Spec approval and Merge approval except on major changes'
  if (askFirst && !(await confirmed($, `Let the agent record ${what} for you, until you stop it?`, 'Approve'))) {
    return 'Nothing was recorded.'
  }
  const scope = asked === 'all' ? [] : ['--but-major']
  const done = await run($, root, ['aidd', 'approve', 'all', ...scope, '--confirmed', asked, '--confirmed-in', 'claude-code'])
  return done.isOk ? firstLine(done.value) : `Nothing was recorded: ${done.error}`
}

// `/aidd decide PROP-1 go` or `/aidd sign-off PROP-1`: what `--show` says the person decides, recorded with `--confirmed`
// for exactly that decision, or for a sign-off exactly that text's hash; a dialog first when it did not come from their
// keyboard (`askFirst`). aidd writes it into the proposal for them to commit.
async function proposalFromCommand($: EngineInterface, root: string, asked: ProposalAsk, askFirst: boolean): Promise<string> {
  const reason = asked.reason === '' ? [] : [`--reason=${asked.reason}`]
  const tail = ['--', asked.id, ...(asked.decision === null ? [] : [asked.decision])]
  const shown = json(await run($, root, ['aidd', 'proposal', asked.verb, '--show', ...reason, ...tail]))
  if (!shown.isOk) {
    return shown.error === NOT_FOUND ? NOT_FOUND : `Nothing was recorded: ${shown.error}`
  }
  const problems = shown.value['problems']
  if (Array.isArray(problems) && problems.length > 0) {
    return `Nothing was recorded: ${String(problems[0])}`
  }
  const hash = typeof shown.value['hash'] === 'string' ? shown.value['hash'] : ''
  const what = asked.decision === null ? `Sign off ${asked.id} (hash ${hash}), so it may be sent?` : `Record ${asked.decision} on ${asked.id}?`
  const title = typeof shown.value['title'] === 'string' ? shown.value['title'] : ''
  if (askFirst && !(await confirmed($, `${what}${title === '' ? '' : ` ${asked.id}: ${title}.`}`, asked.decision === null ? 'Sign off' : 'Decide'))) {
    return 'Nothing was recorded.'
  }
  const done = await run($, root, ['aidd', 'proposal', asked.verb, ...reason, '--confirmed', asked.decision ?? hash, '--confirmed-in', 'claude-code', ...tail])
  if (!done.isOk) {
    return `Nothing was recorded: ${done.error}`
  }
  return done.value.split('\n').find(line => line.startsWith('Recorded')) ?? firstLine(done.value)
}

// `/aidd install [flags]`: `aidd init [flags]` after one dialog that shows what init found.
async function installFromCommand($: EngineInterface, root: string, rest: string): Promise<string> {
  const flags = installArgs(rest)
  const found = await run($, root, ['aidd', 'init', '--dry-run'])
  if (!found.isOk) {
    return found.error === NOT_FOUND ? NOT_FOUND : `aidd could not read this repository: ${found.error}`
  }
  const shown = found.value.split('\n').filter(l => l.trim() !== '').slice(0, 12)
  let answer = ''
  try {
    answer = await $.ui.ask([...shown, '', `Run \`aidd init ${flags.join(' ')}\` here?`].join('\n'), { header: 'Install', options: [NOT_NOW, INSTALL] })
  } catch {
    answer = ''
  }
  if (answer !== INSTALL) {
    return 'Nothing was installed.'
  }
  const done = await run($, root, ['aidd', 'init', ...flags], UPDATE_TIMEOUT_MS)
  return done.isOk ? done.value.trim() : `aidd init failed: ${done.error}`
}

const isOpen = async ($: EngineInterface): Promise<boolean> => (await $.ui.panes()).some(pane => pane.id === PANE)

const close = ($: EngineInterface) => $.ui.close({ id: PANE })

// "15:20", in the time zone the mod's environment has.
const clock = (ms: number): string => {
  const at = new Date(ms)

  return `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`
}

// Who moves next decides a section's color and place: a person, the agent, other work it waits on, or a real block.
type Tone = 'person' | 'agent' | 'waiting' | 'blocked'

export type Group = { key: string; title: string; hint: string; tone: Tone; steps: Step[] }

// Headings for aidd's step codes; any other code reads as its own words ("in_review" → "In review").
const HEADINGS: Record<string, { title: string; hint?: string }> = {
  'spec.spec_approval': { title: 'Needs Spec approval', hint: 'read each Spec and its tests, then approve' },
  'spec.blocked_by': { title: 'Waiting on other work', hint: 'each starts when what it waits on finishes' },
  'spec.blocked': { title: 'Blocked', hint: 'paused, or a Task out of retries: a person decides' },
  'spec.draft': { title: 'Spec being written' },
  'spec.ready': { title: 'Ready to build' },
  'spec.in_progress': { title: 'Being built' },
  'spec.verify': { title: 'Being verified' },
  'spec.review': { title: 'In review' },
  'spec.in_review': { title: 'In review' },
  // The person's standing approval covers these: the agent records the approval, or ships.
  'spec.approve_standing': { title: 'Approving for you', hint: 'your standing approval covers it: the agent records it' },
  'spec.ship_ready': { title: 'Ready to ship', hint: 'your standing approval covers it: the agent runs aidd ship' },
  'spec.merge_standing': { title: 'Approving the merge for you', hint: 'your standing approval covers it' },
  'spec.rework': { title: 'Needs rework' },
  'spec.triage': { title: 'Needs triage' },
  'spec.invalid': { title: 'Spec has problems' },
  'spec.unparsable': { title: 'Spec has problems' },
  'spec.outcome_due': { title: 'Outcome check due' },
  'spec.emergency': { title: 'Emergency change' },
  // A Proposal's stages (METHOD, proposal status): a person decides go/no-go, signs it off, sends it, and converts it.
  'proposal.exploring': { title: 'Proposal: needs a go/no-go', hint: 'read its need and questions, then decide' },
  'proposal.drafting': { title: 'Proposal being written' },
  'proposal.signed_off': { title: 'Proposal ready to send', hint: 'signed off: send it to the addressee' },
  'proposal.submitted': { title: 'Proposal with the addressee', hint: 'record their answer when it comes' },
  'proposal.accepted': { title: 'Proposal accepted', hint: 'turn it into an Initiative: aidd proposal convert' },
}

const words = (code: string): string => {
  const tail = (code.split('.').at(-1) ?? code).replace(/_/g, ' ')

  return tail.charAt(0).toUpperCase() + tail.slice(1)
}

const toneOf = (step: Step): Tone =>
  step.code === 'spec.blocked_by' ? 'waiting' : step.isBlocked ? 'blocked' : step.who === 'agent' ? 'agent' : 'person'

// The items as sections: what waits on you first, then this branch's items grouped by what each needs.
export function groups(waiting: Step[], branch: Step[]): Group[] {
  const mine = new Set(waiting.map(step => step.id))
  const out: Group[] = []
  if (waiting.length > 0) {
    out.push({ key: 'waiting-on-you', title: 'Waiting on you', hint: '', tone: 'person', steps: waiting })
  }
  const byCode = new Map<string, Group>()
  for (const step of branch) {
    if (step.id && mine.has(step.id)) {
      continue
    }
    const tone = toneOf(step)
    const key = `${tone}:${step.code}`
    const heading = HEADINGS[step.code] ?? { title: words(step.code) }
    const group = byCode.get(key) ?? { key, title: heading.title, hint: heading.hint ?? '', tone, steps: [] }
    group.steps.push(step)
    byCode.set(key, group)
  }
  const order: Tone[] = ['person', 'blocked', 'agent', 'waiting']

  return [...out, ...[...byCode.values()].sort((a, b) => order.indexOf(a.tone) - order.indexOf(b.tone))]
}

// What each item holds up, directly or through others: approving SPEC-1 frees SPEC-2, which frees SPEC-3, ...
export function unblocks(all: Step[]): Map<string, string[]> {
  const direct = new Map<string, string[]>()
  for (const step of all) {
    for (const on of step.waitingOn) {
      direct.set(on, [...(direct.get(on) ?? []), step.id])
    }
  }
  const out = new Map<string, string[]>()
  for (const id of direct.keys()) {
    const seen = new Set<string>()
    const queue = [...(direct.get(id) ?? [])]
    while (queue.length > 0) {
      const next = queue.shift() as string
      if (!seen.has(next) && next !== id) {
        seen.add(next)
        queue.push(...(direct.get(next) ?? []))
      }
    }
    out.set(id, [...seen].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })))
  }

  return out
}

const COLOR: Record<Tone, string | undefined> = { person: 'claude', agent: 'suggestion', waiting: undefined, blocked: 'warning' }

// The width of the widest id in a list, at least 6.
const idWidthFor = (ids: string[]): number => Math.max(6, ...ids.map(id => id.length))

// A line cut to its room, with an ellipsis.
const fit = (line: string, room: number): string =>
  room <= 0 ? '' : line.length <= room ? line : `${line.slice(0, Math.max(0, room - 1))}…`

export const register: Register = on => {
  // `/aidd <verb>`: aidd's front door, answered here with no model turn. The command is the aidd skill; with no verb,
  // or a verb this mod does not know, it goes on to the skill, which answers for the agent. Whoever runs it (the
  // person, the SDK, or the agent through the skill), each verb that changes anything asks the person in a dialog
  // first. Another plugin's run is passed on untouched.
  on('command.run', async ($, e, next) => {
    const asked = e.origin.kind !== 'plugin' ? aiddVerb(e.command, e.args) : null
    if (asked === null || !['status', 'close', 'help', 'approve', 'ship', 'decide', 'sign-off', 'update', 'install'].includes(asked.verb)) {
      return next(e)
    }
    if (asked.verb === 'help') {
      return { text: AIDD_HELP }
    }
    const root = await $.session.root()
    // The person's own keyboard is their decision; anything else (the SDK, the agent through the skill) asks first.
    const askFirst = e.origin.kind !== 'composer'
    switch (asked.verb) {
      case 'status': {
        if (asked.rest === 'close') {
          await close($)
          return {}
        }
        const opened = await $.ui.open({ id: PANE, title: TITLE })
        await refresh($)
        // No text: a command's text is a transcript row the model reads.
        return opened.isPlaced ? {} : { text: `The aidd pane could not open here: ${opened.reason}` }
      }
      case 'close':
        await close($)
        return {}
      case 'approve': {
        const standing = standingAsked(`/aidd approve ${asked.rest}`)
        if (standing !== null) {
          return { text: await standingFromPrompt($, root, standing, askFirst) }
        }
        const ids = approvalIds(`approve ${asked.rest}`)
        if (ids === null) {
          return { text: 'Name Specs (`/aidd approve SPEC-1`), `merge`, or nothing for what waits on you.' }
        }
        const said = await approveAsked($, root, ids, askFirst)
        return said === undefined ? {} : { text: said }
      }
      case 'ship':
        $.clock.after(0, () => {
          shipFromPrompt($, root, askFirst).catch(() => $.ui.toast('aidd could not ship: run `aidd ship` in a terminal.'))
        })
        return {}
      case 'decide':
      case 'sign-off': {
        const proposal = proposalAsked(asked.verb, asked.rest)
        return {
          text:
            proposal === null
              ? 'Say `/aidd decide PROP-1 go` (or no-go, with why after it), or `/aidd sign-off PROP-1`.'
              : await proposalFromCommand($, root, proposal, askFirst),
        }
      }
      case 'update':
        return { text: await updateFromCommand($, root) }
      case 'install':
        return { text: await installFromCommand($, root, asked.rest) }
      default:
        return next(e)
    }
  }).catch(() => ({ text: '/aidd failed inside Claude Code; run the aidd command in a shell.' }))

  // "approve SPEC-1", typed by the person at this terminal: handled here, never sent to the model. A bare "approve"
  // is handled only when a Spec waits on your approval; otherwise it is an ordinary prompt.
  on('prompt.submit', async ($, e, next) => {
    const typedHere = e.origin.kind === 'composer' && !e.isMeta && !e.command
    if (typedHere && isShip(e.text)) {
      const root = await $.session.root()
      $.clock.after(0, () => {
        shipFromPrompt($, root).catch(() => $.ui.toast('aidd could not ship: run `aidd ship` in a terminal.'))
      })

      return { drop: 'aidd: shipping this branch. This prompt does not go to the model.' }
    }
    const standing = typedHere ? standingAsked(e.text) : null
    if (standing !== null) {
      const root = await $.session.root()
      $.clock.after(0, () => {
        standingFromPrompt($, root, standing)
          .then(said => $.ui.toast(said, { timeoutMs: 12_000 }))
          .catch(() => $.ui.toast('aidd could not record it: run `aidd approve all` in a terminal.'))
      })
      return { drop: `aidd: ${standing === 'stop' ? 'stopping your standing approval' : 'recording your standing approval'}. This prompt does not go to the model.` }
    }
    const asked = typedHere ? approvalIds(e.text) : null
    if (asked === null) {
      return next(e)
    }
    const root = await $.session.root()
    if ((await approveAsked($, root, asked)) !== undefined) {
      return next(e)
    }
    const what = asked === 'merge' ? 'the merge of this branch' : asked.length > 0 ? asked.join(', ') : 'what waits on you'
    return { drop: `aidd: approving ${what}. This prompt does not go to the model.` }
  })

  // Each turn may change what is open; refresh after it, without holding the turn up.
  on('turn.complete', async ($, e, next) => {
    if (e.agentId === undefined && (await isOpen($))) {
      $.clock.after(0, () => void refresh($))
    }

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const snap: Snapshot | null = await read($, shot)
    const isLoading = await read($, loading)
    const chosen = await read($, selected)
    const focused = await read($, focus)
    const openTask = await read($, opened)
    // Choosing another item closes the Task that was open.
    const choose = async (id: string) => {
      await update($, selected, () => id)
      await update($, opened, () => null)
    }
    const columns = e.props.bodyColumns
    const rows = e.props.scroll.bodyRows
    const isTight = columns < NARROW
    const isDocked = e.props.placement === 'dock'

    const header = (
      <Box key="header" flexDirection="row" justifyContent="space-between" flexWrap="wrap">
        <Box flexShrink={1} minWidth={0}>
          <Text wrap="truncate-start">
            <Text bold>{snap?.head || 'aidd'}</Text>
            {snap ? <Text dimColor>{`  ${snap.root.split('/').at(-1)}`}</Text> : ''}
            <Text dimColor>{isLoading ? ' · refreshing…' : snap ? ` · updated ${clock(snap.at)}` : ''}</Text>
          </Text>
        </Box>
        <Box flexShrink={0} columnGap={1} flexDirection="row">
          {focused ? <Button key="all" label={`All (showing ${focused})`} hotkey="a" onPress={() => void update($, focus, () => null)} /> : ''}
          <Button key="refresh" label="Refresh" hotkey="r" onPress={() => void refresh($)} />
          <Button key="close" label="Close" hotkey="x" role="dismiss" onPress={() => void close($)} />
        </Box>
      </Box>
    )

    const footer = (
      <Text dimColor wrap="truncate-end">
        {isTight
          ? `↑↓ · Enter${openTask ? ' · b' : ''} · a · r · x · ctrl+x tab`
          : `↑↓ move · Enter open${openTask ? ' · b back' : ''} · a all · r refresh · x close · ctrl+x tab: use the pane · Esc prompt`}
      </Text>
    )

    // The pane is as tall as its window: the body takes what is left, and the autopilot line and the key hints stay
    // on the last rows.
    // Inline above the prompt, the pane fits its content instead, so it never takes the whole room.
    const frame = (body: unknown[], pinned: unknown = '') => (
      <Box flexDirection="column" height={isDocked ? rows : undefined}>
        <Box flexDirection="column" flexGrow={1} flexShrink={1} overflow={isDocked ? 'hidden' : 'visible'} gap={1}>
          {body as string[]}
        </Box>
        <Box flexDirection="column" flexShrink={0}>
          {pinned as string}
          {footer}
        </Box>
      </Box>
    )

    if (snap === null) {
      return frame([header, <Text key="wait" dimColor>{isLoading ? 'Asking aidd…' : 'Press r to load.'}</Text>])
    }

    const errors = [snap.waiting, snap.branch]
      .filter((section): section is { isOk: false; error: string } => !section.isOk)
      .map(section => section.error)
    // Focus on an Initiative or an Epic shows only its items; what each item holds up counts over all of them.
    const allMine = snap.waiting.isOk ? snap.waiting.value : []
    const allListed = snap.branch.isOk ? snap.branch.value : []
    const frees = unblocks(groups(allMine, allListed).flatMap(group => group.steps))
    const inFocus = (step: Step) => !focused || step.id === focused || step.parents.some(parent => parent.id === focused)
    const sections = groups(allMine.filter(inFocus), allListed.filter(inFocus))
    const every = sections.flatMap(section => section.steps)
    const detail = every.find(step => step.id === chosen) ?? every[0]
    const count = (tone: Tone) => sections.filter(section => section.tone === tone).reduce((n, section) => n + section.steps.length, 0)
    const pilot = snap.autopilot
    const live = pilot.isOk ? pilot.value.leases.find(lease => !lease.isStale) : undefined

    // One line to read at a glance: who has to move next. A count of zero is left out; autopilot has its own line below.
    const tally = (n: number, label: string, tone: Tone) =>
      n > 0 ? (
        <Text color={COLOR[tone]} dimColor={tone === 'waiting'} bold={tone === 'person'}>
          {n} {label}
        </Text>
      ) : null
    const parts = [
      count('person') > 0 ? tally(count('person'), 'need you', 'person') : <Text color="success">Nothing needs you</Text>,
      tally(count('blocked'), 'blocked', 'blocked'),
      tally(count('agent'), 'with the agent', 'agent'),
      tally(count('waiting'), 'waiting on other work', 'waiting'),
    ].filter(part => part !== null)
    const summary = (
      <Text key="summary" wrap="wrap">
        {parts.flatMap((part, i) => (i === 0 ? [part] : [<Text dimColor> · </Text>, part]))}
      </Text>
    )

    // DIRECTION: a decision ladder (surface seed a2fc9c1f, candidate 7 of 7). THESIS: the lead's next decision first, then
    // every small goal on the four rungs of the person's decisions; it refuses a board of grouped tickets. OWN-WORLD:
    // Claude Code's own terminal theme; the claude color means it waits on you, success that a rung is done, dim that
    // it is still ahead; ◆ ✓ · — carry the same meaning without color. Raised by the wayfinding sign (only the choice
    // ahead, with what to type) and by the ticket wallet (a done rung stays stamped; nothing vanishes).
    const shaped = snap.shape.isOk ? snap.shape.value : null
    const asked = decisions(allMine, shaped, pilot.isOk ? pilot.value.last : null, !(pilot.isOk && pilot.value.leases.some(lease => !lease.isStale)))
    const next = asked[0]
    const band = (
      <Box key="band" flexDirection="column">
        {next ? (
          <Text wrap="truncate-end">
            <Text color={COLOR.person} bold>{`◆ ${next.rung ? `${next.rung} ` : ''}${next.label}`}</Text>
            <Text bold>{next.id ? `  ${next.id}` : ''}</Text>
            <Text>{next.title ? `  ${next.title}` : ''}</Text>
          </Text>
        ) : (
          <Text color="success">✓ Nothing needs you</Text>
        )}
        {next && next.type ? (
          <Text wrap="truncate-end">
            <Text dimColor>{'  type  '}</Text>
            <Text color="suggestion">{next.type}</Text>
            <Text dimColor>{asked.length > 1 ? `   · ${asked.length - 1} more wait on you` : ''}</Text>
          </Text>
        ) : (
          ''
        )}
      </Box>
    )

    // The shape of the work: each big goal, then each small goal on its ladder. Enter on a small goal shows only its work.
    const TONE: Record<Cell['tone'], string | undefined> = { person: COLOR.person, done: 'success', ahead: undefined, none: undefined }
    const smallGoals = shaped?.smallGoals ?? []
    const byGoal = new Map(smallGoals.map(goal => [goal.id, goal]))
    const loose = smallGoals.filter(goal => !shaped?.initiatives.some(init => init.smallGoals.includes(goal.id)))
    // Open Proposals lead: work someone outside the team must agree to before there is a plan.
    const proposals = groups(allMine, allListed)
      .flatMap(group => group.steps)
      .filter(item => item.code.startsWith('proposal.'))
    const ladderIds = [...proposals.map(item => item.id), ...(shaped?.initiatives ?? []).flatMap(init => [init.id, ...init.smallGoals]), ...loose.map(goal => goal.id)]
    const ladderShown = ladderIds.slice(0, PLAN_LINES + 2)
    const leadWidth = Math.max(10, ...ladderIds.map(id => id.length + 6))
    // How a small goal ships, in a column wide enough for the longest name: two spaces, `incremental`, one space.
    const SHIPS_COL = 14
    // Wide, each rung says its decision and its name; narrow, the decision alone, as the band names it.
    const isRoomy = columns >= leadWidth + SHIPS_COL + 11 * 4 + MIN_TITLE
    const CELL = isRoomy ? 11 : 6
    const RUNGS = isRoomy ? ['D1 plan', 'D2 specs', 'D3 release', 'D4 launch'] : ['D1', 'D2', 'D3', 'D4']
    const titleRoom = Math.max(0, columns - leadWidth - SHIPS_COL - CELL * RUNGS.length - 2)
    const ladder =
      ladderIds.length > 0 && (smallGoals.length > 0 || proposals.length > 0) ? (
        <Box key="ladder" flexDirection="column">
          <Text wrap="truncate-end">
            <Text bold>{'Shape of work'.padEnd(leadWidth + titleRoom + SHIPS_COL)}</Text>
            <Text dimColor>{RUNGS.map(r => r.padEnd(CELL)).join('')}</Text>
          </Text>
          {ladderShown.map(id => {
            const proposal = proposals.find(item => item.id === id)
            if (proposal) {
              return (
                <Button key={`ladder-${id}`} plain onPress={() => void update($, focus, now => (now === id ? null : id))}>
                  <Text bold color={focused === id ? COLOR.person : undefined}>{`  ${id}`.padEnd(leadWidth)}</Text>
                  <Text>{fit(proposal.title || proposal.what, titleRoom + SHIPS_COL)}</Text>
                  <Text dimColor>{`  proposal, ${proposal.status}`}</Text>
                </Button>
              )
            }
            const goal = byGoal.get(id)
            const init = shaped?.initiatives.find(one => one.id === id)
            if (init) {
              const shipped = init.smallGoals.filter(gid => {
                const g = byGoal.get(gid)
                return g !== undefined && g.release.total > 0 && g.release.done >= g.release.total && (g.launch === null || g.launch.state === 'done')
              }).length
              return (
                <Button key={`ladder-${id}`} plain onPress={() => void update($, focus, now => (now === id ? null : id))}>
                  <Text bold color={focused === id ? COLOR.person : undefined}>{`  ${id}`.padEnd(leadWidth)}</Text>
                  <Text>{fit(init.title, titleRoom + SHIPS_COL)}</Text>
                  <Text dimColor>{`  ${shipped}/${init.smallGoals.length} small goals done`}</Text>
                </Button>
              )
            }
            if (!goal) {
              return ''
            }
            const isFocused = focused === id
            return (
              <Button key={`ladder-${id}`} plain onPress={() => void update($, focus, now => (now === id ? null : id))}>
                <Text bold={isFocused} color={isFocused ? COLOR.person : undefined}>
                  {`    ${id}`.padEnd(leadWidth)}
                </Text>
                <Text>{fit(goal.title, titleRoom).padEnd(titleRoom)}</Text>
                <Text dimColor>{`  ${goal.ships.padEnd(SHIPS_COL - 2)}`}</Text>
                {cells(goal).map((cell, i) => (
                  <Text key={`cell-${id}-${i}`} color={TONE[cell.tone]} bold={cell.tone === 'person'} dimColor={cell.tone === 'none' || cell.tone === 'ahead'}>
                    {cell.mark.padEnd(CELL)}
                  </Text>
                ))}
              </Button>
            )
          })}
          {ladderIds.length > ladderShown.length ? <Text dimColor>{`  +${ladderIds.length - ladderShown.length} more: aidd goal list`}</Text> : ''}
        </Box>
      ) : snap.shape.isOk ? (
        ''
      ) : (
        <Text key="ladder" dimColor wrap="truncate-end">{`Shape of work: ${snap.shape.error}`}</Text>
      )

    // Rows left for items once the header, the plan, the details (DETAIL_ROWS), autopilot (1), the key hints (1), the
    // gaps, and each section's heading are drawn; at least 2 items a section.
    const fixed = 2 + 2 + (ladderIds.length > 0 ? ladderShown.length + 2 : 0) + DETAIL_ROWS + 3 + sections.length + 2
    const perSection = Math.max(2, Math.floor((rows - fixed - sections.length) / Math.max(1, sections.length)))

    // One column layout for every section, so ids, titles, waits and priorities line up down the pane. The title
    // keeps at least MIN_TITLE cells: when the room is short, the priority goes first, then the waits.
    const noteOf = (step: Step): string => {
      const freed = frees.get(step.id)?.length ?? 0
      return step.waitingOn.length > 0 ? `waits on ${step.waitingOn.join(', ')}` : freed > 0 ? `${freed} wait on it` : ''
    }
    const idWidth = Math.max(6, ...every.map(step => step.id.length)) + 2
    let noteWidth = Math.min(MAX_NOTE, Math.max(0, ...every.map(step => noteOf(step).length)))
    let priorityWidth = Math.max(0, ...every.map(step => step.priority.length))
    // The Epic column shows only when the items serve more than one Epic, and never while one is in focus.
    const epicOf = (step: Step) => step.parents.at(-1)?.id ?? ''
    let epicWidth = !focused && new Set(every.map(epicOf)).size > 1 ? Math.max(...every.map(step => epicOf(step).length)) : 0
    const titleWidth = () =>
      columns - 2 - idWidth - (noteWidth ? noteWidth + 2 : 0) - (epicWidth ? epicWidth + 2 : 0) - (priorityWidth ? priorityWidth + 2 : 0)
    for (const drop of [() => (priorityWidth = 0), () => (epicWidth = 0), () => (noteWidth = 0)]) {
      if (titleWidth() < MIN_TITLE) {
        drop()
      }
    }
    const nameWidth = Math.max(1, titleWidth())

    // A row is one Button: Enter or a click shows its details below.
    const row = (step: Step, tone: Tone) => {
      const isChosen = step.id === detail?.id
      const note = noteOf(step)
      const isLoud = step.priority === 'urgent' || step.priority === 'high'
      const quiet = tone === 'waiting' && !isChosen

      return (
        <Button key={`row-${step.id || step.what}`} plain onPress={() => void choose(step.id)}>
          <Text color={isChosen ? COLOR[tone] : undefined} bold={isChosen}>
            {isChosen ? '› ' : '  '}
          </Text>
          <Text bold={isChosen} dimColor={quiet}>
            {fit(step.id, idWidth - 1).padEnd(idWidth)}
          </Text>
          <Text dimColor={quiet}>{fit(step.title || step.what, nameWidth).padEnd(nameWidth)}</Text>
          {noteWidth ? (
            <Text color={step.waitingOn.length === 0 && note ? COLOR[tone] : undefined} dimColor={step.waitingOn.length > 0}>
              {`  ${fit(note, noteWidth).padEnd(noteWidth)}`}
            </Text>
          ) : (
            ''
          )}
          {epicWidth ? <Text dimColor>{`  ${epicOf(step).padEnd(epicWidth)}`}</Text> : ''}
          {priorityWidth ? <Text dimColor={!isLoud}>{`  ${step.priority.padEnd(priorityWidth)}`}</Text> : ''}
        </Button>
      )
    }

    const section = (group: Group) => {
      const shown = group.steps.slice(0, perSection)

      return (
        <Box key={`section-${group.key}`} flexDirection="column">
          <Text wrap="truncate-end">
            <Text bold color={COLOR[group.tone]}>
              {group.title}
            </Text>
            <Text dimColor>
              {`  ${group.steps.length}`}
              {group.hint ? `  ${group.hint}` : ''}
            </Text>
          </Text>
          {shown.map(step => row(step, group.tone))}
          {group.steps.length > shown.length ? <Text dimColor>{`    +${group.steps.length - shown.length} more: aidd list --branch`}</Text> : ''}
        </Box>
      )
    }

    // `aidd …` in backticks reads as a command to run.
    const commands = (line: string) =>
      line.split('`').map((part, i) => (i % 2 === 1 ? <Text color="suggestion">{part}</Text> : part))

    // A labelled line of the detail card; the value wraps under itself, the labels stay in one column.
    const field = (label: string, value: unknown, isShown: boolean) =>
      isShown ? (
        <Box key={`field-${label}`} flexDirection="row">
          <Box width={12} flexShrink={0}>
            <Text dimColor>{label}</Text>
          </Box>
          <Box flexGrow={1} flexShrink={1} minWidth={0}>
            <Text wrap="wrap">{value as string}</Text>
          </Box>
        </Box>
      ) : (
        ''
      )

    const rule = <Text dimColor>{'─'.repeat(Math.max(0, columns))}</Text>

    // A part of the detail card: a dim heading after a blank line, so About, Status, and Tasks read apart without boxes.
    const group = (title: string) => (
      <Box key={`group-${title}`} marginTop={1}>
        <Text dimColor bold>
          {title}
        </Text>
      </Box>
    )

    // A Spec's Tasks, one row each in a grid: Enter opens one.
    const taskRows = (list: Task[]) => {
      const idWidth = Math.max(...list.map(task => task.id.length)) + 2
      const statusWidth = Math.max(...list.map(task => task.status.length)) + 2
      const roleWidth = Math.max(...list.map(task => task.role.length))
      const room = Math.max(8, columns - 4 - idWidth - statusWidth - roleWidth)
      return list.map(task => (
        <Button key={`task-${task.id}`} plain onPress={() => void update($, opened, () => task.id)}>
          {'  '}
          <Text bold>{task.id.padEnd(idWidth)}</Text>
          {fit(task.title, room).padEnd(room)}
          {'  '}
          <Text color={task.status === 'blocked' ? 'warning' : task.status === 'done' ? 'success' : undefined}>{task.status.padEnd(statusWidth)}</Text>
          <Text dimColor>{task.role}</Text>
        </Button>
      ))
    }

    // The item's folder, `specs/<ID>/`, one row per entry: its docs, its design, and its explorations, each named from
    // the folder. An open exploration waits on a person's pick, so it shows in the person's color.
    const fileRows = (step: Step, base: string) => {
      const kindWidth = Math.max(...step.files.filter(file => file.kind !== 'more').map(file => file.kind.length), 0) + 2
      return step.files.map(file => {
        if (file.kind === 'more') {
          return <Text key="file-more" dimColor>{`  … ${file.count} more`}</Text>
        }
        const name = file.path.startsWith(base) ? file.path.slice(base.length) : file.path
        const isOpen = file.status === 'open'
        return (
          <Text key={`file-${file.path}`} wrap="truncate-end">
            {'  '}
            <Text dimColor>{file.kind.padEnd(kindWidth)}</Text>
            {file.kind === 'exploration' || file.kind === 'design' || file.kind === 'folder' ? `${name}/` : name}
            {file.kind === 'exploration' ? <Text color={isOpen ? COLOR.person : 'success'}>{isOpen ? '  open: a person picks' : '  decided'}</Text> : ''}
            {file.question ? <Text dimColor>{` · ${file.question}`}</Text> : ''}
          </Text>
        )
      })
    }

    // One Task opened from its Spec: why it is where it is, who does it, and what it may change.
    const taskCard = (step: Step, task: Task) => (
      <Box key="details" flexDirection="column">
        {rule}
        <Box flexDirection="row" justifyContent="space-between">
          <Text bold wrap="wrap">
            <Text color={COLOR[toneOf(step)]}>{task.id}</Text>
            {task.title ? `  ${task.title}` : ''}
          </Text>
          <Button key="back" label={`Back to ${step.id}`} hotkey="b" onPress={() => void update($, opened, () => null)} />
        </Box>
        <Text dimColor wrap="truncate-end">{[task.status, task.assignee, `in ${step.id}${step.title ? ` · ${step.title}` : ''}`].filter(Boolean).join(' · ')}</Text>
        {field('Why', task.why, task.why !== '')}
        {field('Role', task.role, task.role !== '')}
        {field('Scope', task.scope.join('\n'), task.scope.length > 0)}
        {field('Waits on', task.dependsOn.join(', '), task.dependsOn.length > 0)}
      </Box>
    )

    // The chosen item in full, under a rule: what the Spec is about, where it stands, and its Tasks.
    const details = (step: Step) => {
      const task = step.taskList.find(one => one.id === openTask)
      if (task) {
        return taskCard(step, task)
      }
      const freed = frees.get(step.id) ?? []
      const meta = [step.priority, step.status, step.owner, step.where].filter(Boolean).join(' · ')
      const said = step.about
      const hasAbout = said.for !== '' || said.problem !== '' || said.goals.length > 0
      // A Proposal says who it is for, its need, and its goal; a Spec, its problem and goals.
      const isProposal = said.kind === 'proposal'
      // The item's own folder, beside its file: `specs/SPEC-12.md` keeps its docs in `specs/SPEC-12/`.
      const folder = `${specsFolder([step])}/${step.id}/`

      return (
        <Box key="details" flexDirection="column">
          {rule}
          <Text bold wrap="wrap">
            <Text color={COLOR[toneOf(step)]}>{step.id}</Text>
            {step.title ? `  ${step.title}` : ''}
          </Text>
          {meta ? <Text dimColor wrap="truncate-end">{meta}</Text> : ''}
          {hasAbout ? group('About') : ''}
          {field('For', said.for, said.for !== '')}
          {field(isProposal ? 'Need' : 'Problem', said.problem, said.problem !== '')}
          {isProposal
            ? field('Goal', said.goals[0] ?? '', said.goals.length > 0)
            : field('Goals', said.goals.map(goal => `• ${goal}`).join('\n'), said.goals.length > 0)}
          {group('Status')}
          {field('Now', step.what, true)}
          {field('Waits on', step.waitingOn.join(', '), step.waitingOn.length > 0)}
          {field('Holds up', freed.join(', '), freed.length > 0)}
          {field('Next', commands(step.how), step.how !== '')}
          {field('Part of', step.why, step.why !== '')}
          {step.taskList.length > 0 ? group(`Tasks · ${step.tasks}`) : ''}
          {step.taskList.length > 0 ? taskRows(step.taskList) : ''}
          {step.files.length > 0 ? group(`Files · ${folder}`) : ''}
          {step.files.length > 0 ? fileRows(step, folder) : ''}
        </Box>
      )
    }

    // Autopilot's one line, pinned above the key hints: its state, then what it did and said last.
    const autopilot = !pilot.isOk ? (
      <Text key="pilot" color="error" wrap="truncate-end">
        Autopilot: {pilot.error}
      </Text>
    ) : (
      <Text key="pilot" wrap="truncate-end">
        <Text bold>Autopilot </Text>
        {live ? <Text color="success">live</Text> : <Text dimColor>idle</Text>}
        <Text dimColor>
          {live ? ` · ${live.work} · ${until(live.expiresAt, snap.at)} of ${live.timebox}` : ''}
          {pilot.value.last ? ` · last step ${pilot.value.last}` : ''}
          {pilot.value.heard ? ` · told you: ${pilot.value.heard}` : ''}
        </Text>
      </Text>
    )

    // The trunk-based flow, pinned above autopilot: amber while a branch or goal is past its limit.
    const flow = shaped ? (
      <Text key="flow" wrap="truncate-end">
        <Text bold>Flow </Text>
        <Text color={shaped.warnings.length > 0 ? 'warning' : undefined} dimColor={shaped.warnings.length === 0}>
          {shaped.warnings.length > 0 ? `${shaped.warnings[0]}${shaped.warnings.length > 1 ? ` (+${shaped.warnings.length - 1} more: aidd goal list)` : ''}` : flowLine(shaped)}
        </Text>
      </Text>
    ) : (
      ''
    )

    const empty =
      sections.length === 0 && errors.length === 0 ? (
        <Box key="empty" flexDirection="column">
          <Text>{focused ? `Nothing is open under ${focused}.` : 'Nothing is open on this branch, and nothing waits on you.'}</Text>
          <Text dimColor wrap="wrap">
            Describe a change to the agent, or tell autopilot what you want: <Text color="suggestion">/aidd-team:autopilot "what you want"</Text>
          </Text>
        </Box>
      ) : (
        ''
      )

    return frame([
      <Box key="top" flexDirection="column">
        {header}
        {band}
        {summary}
        {snap.standing ? (
          <Text color="warning" wrap="wrap">
            {snap.standing}
          </Text>
        ) : null}
      </Box>,
      ...errors.map(error => (
        <Text key={`error-${error}`} color="error" wrap="wrap">
          {error}
        </Text>
      )),
      ladder,
      empty,
      ...sections.map(section),
      detail ? details(detail) : '',
    ], [flow, autopilot])
  })
}
