import type { About, Autopilot, BranchAge, Decision, ItemFile, Lease, Link, Parent, Rung, Section, Shape, SmallGoal, Snapshot, Step, Task } from '../types'

// Plain functions over what aidd printed: no engine calls here, so Claude Code reads every $ call in register.tsx.

export const TIMEOUT_MS = 20_000

export const NOT_FOUND = '`aidd` did not start: it is not on the PATH Claude Code was started with. Install it (docs/INSTALL.md).'

type Json = Record<string, unknown>

const text = (value: unknown): string => (typeof value === 'string' ? value : '')

// The first line aidd said, for a failure: the rest is detail the pane has no room for.
export const firstLine = (said: string): string => said.trim().split('\n')[0] ?? ''

// The person's standing approval in force (`aidd list --json`'s `standing`), as one line, or null when none is.
export function standingNote(raw: Json): string | null {
  const s = raw['standing']
  if (typeof s !== 'object' || s === null) {
    return null
  }
  const standing = s as Json
  const what = standing['scope'] === 'all-but-major' ? 'all but major' : 'all'
  const since = text(standing['since']).slice(0, 16).replace('T', ' ')
  return `Approving ${what} for you since ${since}: type "stop approving" to end it`
}

// An explore branch (`aidd list --json`'s `explore_branch`), as one line, or null on any other branch.
export function exploreNote(raw: Json): string | null {
  const branch = raw['explore_branch']
  return typeof branch === 'string' && branch !== '' ? `${branch} is an explore branch: free edits, and nothing merges from it` : null
}

export function json(section: Section<string>): Section<Json> {
  if (!section.isOk) {
    return section
  }
  try {
    const parsed: unknown = JSON.parse(section.value)

    return typeof parsed === 'object' && parsed !== null
      ? { isOk: true, value: parsed as Json }
      : { isOk: false, error: 'aidd printed no JSON object' }
  } catch (error) {
    return { isOk: false, error: `aidd printed something that is not JSON: ${error instanceof Error ? error.message : error}` }
  }
}

const RANK: Record<string, number> = { urgent: 0, high: 1, medium: 2, low: 3 }

// Natural order for ids: SPEC-2 before SPEC-10.
const byId = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true })

const strings = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [])

// "INIT-1 (0/3) → EPIC-1 (0/3)": where the item sits, from aidd's `why` chain.
function chain(why: unknown): string {
  const links = Array.isArray(why) ? (why as Json[]) : []

  return links
    .filter(link => text(link['id']))
    .map(link => `${text(link['id'])}${link['progress'] ? ` (${text(link['progress'])})` : ''}`)
    .join(' → ')
}

// The Initiative and the Epic of an item, outermost first, from aidd's `why` chain.
function links(why: unknown): Link[] {
  const chainOf = Array.isArray(why) ? (why as Json[]) : []

  return chainOf
    .filter(link => text(link['id']) && (link['kind'] === 'initiative' || link['kind'] === 'epic'))
    .map(link => ({ kind: text(link['kind']), id: text(link['id']), progress: text(link['progress']) }))
}

// Every Initiative and Epic the items name, once each, in the order first met; titles come later.
export function parentsOf(items: Step[]): Parent[] {
  const seen = new Map<string, Parent>()
  for (const item of items) {
    for (const link of item.parents) {
      if (!seen.has(link.id)) {
        seen.set(link.id, { ...link, title: '', from: '' })
      }
    }
  }

  return [...seen.values()]
}

// The folder the work items sit in, the config's `specs_dir`: the folder of an item the CLI listed whose file is named
// by its id (`<folder>/SPEC-1.md`; a Proposal's `proposals/PROP-1/proposal.md` is not), else `specs`. The CLI is the
// one source of truth for where the work items are; the pane never assumes the folder.
export function specsFolder(items: Step[]): string {
  const where = items.map(item => item.where).find(w => isInside(w) && items.some(item => item.id && w.endsWith(`/${item.id}.md`)))

  return where?.includes('/') ? where.slice(0, where.lastIndexOf('/')) : 'specs'
}

// The id an Initiative or an Epic file is named by, such as EPIC-2: read from `<specs folder>/<id>.md` only.
export const isWorkId = (id: string) => /^[A-Z][A-Z0-9]*-[0-9]+$/.test(id)

// "1 task, blocked" or "3 tasks: 1 done, 2 todo".
function taskLine(tasks: unknown): string {
  const list = Array.isArray(tasks) ? (tasks as Json[]) : []
  if (list.length === 0) {
    return ''
  }
  const counts = new Map<string, number>()
  for (const task of list) {
    const status = text(task['status']) || 'unknown'
    counts.set(status, (counts.get(status) ?? 0) + 1)
  }
  const parts = [...counts].map(([status, n]) => (list.length === 1 ? status : `${n} ${status}`))

  return `${list.length} task${list.length === 1 ? '' : 's'}${list.length === 1 ? ', ' : ': '}${parts.join(', ')}`
}

// Each Task of a Spec, as `aidd list --json` gives it.
function taskList(tasks: unknown): Task[] {
  const list = Array.isArray(tasks) ? (tasks as Json[]) : []

  return list.map(task => ({
    id: text(task['id']),
    title: text(task['title']),
    status: text(task['status']),
    why: text(task['why']),
    assignee: text(task['assignee']),
    role: text(task['role']),
    scope: strings(task['scope']),
    dependsOn: strings(task['depends_on']),
  }))
}

export const NO_ABOUT: About = { kind: '', for: '', problem: '', goals: [] }

// What an item is about, from its file; a TODO is no text, so a stub says nothing yet.
// A Spec: the first paragraph of `## Problem`, and the bullets of `## Goals` (at most three).
// A Proposal: `audience` · `addressee`, the first paragraph of `## The need` (else `## Summary`), and its `goal`.
export function about(source: string): About {
  const body = source.replace(/<!--[\s\S]*?-->/g, '')
  const section = (name: string): string[] => {
    const at = body.search(new RegExp(`^## ${name}\\s*$`, 'm'))
    if (at < 0) {
      return []
    }
    const rest = body.slice(at).split('\n').slice(1)
    const end = rest.findIndex(line => line.startsWith('## '))
    return (end < 0 ? rest : rest.slice(0, end)).map(line => line.trimEnd())
  }
  const real = (line: string) => line !== '' && !/^TODO\b/i.test(line)
  const paragraph = (lines: string[]) => {
    const firstBlank = lines.findIndex((line, i) => line === '' && lines.slice(0, i).some(Boolean))
    const text = (firstBlank < 0 ? lines : lines.slice(0, firstBlank)).filter(Boolean).join(' ').trim()
    return real(text) ? text : ''
  }
  const bullets = (lines: string[]) => lines.filter(line => /^\s*[-*] /.test(line)).map(line => line.replace(/^\s*[-*] /, '').trim())
  const kind = frontField(source, 'kind')

  if (kind === 'proposal') {
    const goal = frontField(source, 'goal')
    return {
      kind,
      for: [frontField(source, 'audience'), frontField(source, 'addressee')].filter(real).join(' · '),
      problem: paragraph(section('The need')) || paragraph(section('Summary')),
      goals: real(goal) ? [goal] : [],
    }
  }
  return { kind: kind || 'spec', for: '', problem: paragraph(section('Problem')), goals: bullets(section('Goals')).filter(real).slice(0, 3) }
}

// `aidd list --json` steps, without the "nothing is open" placeholder rows: what a person holds
// first, then blocked work, then by priority and id.
// The item's folder, from `files` in `aidd list --json`: the open explorations first (a person may need to pick),
// then the documents in the order aidd gives them.
export function itemFiles(raw: unknown): ItemFile[] {
  const list = Array.isArray(raw) ? (raw as Json[]) : []
  const files = list
    .map(entry => ({
      path: text(entry['path']),
      kind: text(entry['kind']),
      question: text(entry['question']),
      status: text(entry['status']),
      count: typeof entry['count'] === 'number' ? entry['count'] : 0,
    }))
    .filter(file => file.kind && (file.path || file.kind === 'more'))
  const open = (file: ItemFile) => file.kind === 'exploration' && file.status === 'open'

  return [...files.filter(open), ...files.filter(file => !open(file))]
}

export function steps(listed: Json): Step[] {
  const raw = Array.isArray(listed['steps']) ? (listed['steps'] as Json[]) : []

  return raw
    .filter(step => !text(step['code']).startsWith('nothing'))
    .map(step => {
      const id = text(step['id'])
      const what = text(step['what'])

      return {
        id,
        code: text(step['code']),
        title: '',
        what: id && what.startsWith(`${id} `) ? what.slice(id.length + 1) : what,
        who: text(step['who']),
        how: text(step['how']),
        priority: text(step['priority']),
        status: text(step['status']),
        owner: text(step['owner']),
        labels: strings(step['labels']),
        waitingOn: strings(step['waiting_on']),
        why: chain(step['why']),
        parents: links(step['why']),
        tasks: taskLine(step['tasks']),
        taskList: taskList(step['tasks']),
        where: text(step['where']),
        isBlocked: step['blocked'] === true,
        about: NO_ABOUT,
        files: itemFiles(step['files']),
      }
    })
    .sort(
      (a, b) =>
        Number(a.who === 'agent') - Number(b.who === 'agent') ||
        Number(b.isBlocked) - Number(a.isBlocked) ||
        (RANK[a.priority] ?? 9) - (RANK[b.priority] ?? 9) ||
        byId(a.id, b.id),
    )
}

// One plain `key: value` line of a work item's front matter, unquoted; '' when it has none.
export function frontField(source: string, key: string): string {
  const front = /^---\n([\s\S]*?)\n---/.exec(source)?.[1] ?? ''
  const line = new RegExp(`^${key}:\\s*(.+?)\\s*$`, 'm').exec(front)?.[1] ?? ''

  return line.replace(/\s+#.*$/, '').replace(/^(["'])(.*)\1$/, '$2')
}

// The `title:` of a work item's front matter: a person reads a Spec by its title, not its id.
export const frontTitle = (source: string): string => frontField(source, 'title')

// Only a plain relative path inside the repository is read.
export const isInside = (where: string) => /^[\w./-]+\.md$/.test(where) && !where.split('/').includes('..')

export function autopilot(status: Json, now: number): Autopilot {
  const leases: Lease[] = (Array.isArray(status['leases']) ? (status['leases'] as Json[]) : []).map(lease => ({
    work: text(lease['work']),
    by: text(lease['by']),
    session: text(lease['session_id']),
    expiresAt: text(lease['expires_at']),
    timebox: text(lease['timebox']),
    isStale: lease['stale'] === true,
  }))
  const journal = Array.isArray(status['journal']) ? (status['journal'] as Json[]) : []
  const notices = Array.isArray(status['notices']) ? (status['notices'] as Json[]) : []
  const entry = journal.at(-1)
  const notice = notices.at(-1)
  const tokens = typeof entry?.['tokens'] === 'number' ? ` · ${Math.round(entry['tokens'] / 1000)}k tokens` : ''

  return {
    leases,
    last: entry ? `${text(entry['code'])} ${text(entry['result'])}${tokens} · ${ago(text(entry['at']), now)}` : null,
    heard: notice ? `${text(notice['event'])}${notice['reason'] ? ` (${text(notice['reason'])})` : ''}` : null,
  }
}

// The words around the ids that still make a prompt an approval: "approve SPEC-1 and SPEC-4 please".
const FILLER = new Set(['and', 'spec', 'specs', 'the', 'both', 'them', 'it', 'please', 'pls', 'now', 'too', 'also', 'these', 'those', 'this'])

// A standing approval, typed by the person: "approve all" (or "automate"), "but major" keeping major changes for them,
// and "stop approving" ending it. The same phrases aidd's own prompt hook reads (src/aidd/cli/commands/typed_decisions.py).
export function standingAsked(text: string): 'all' | 'all-but-major' | 'stop' | null {
  if (/^\s*(?:\/aidd\s+approve\s+stop|stop\s+approving(?:\s+for\s+me)?)\s*[.!]?\s*$/i.test(text)) {
    return 'stop'
  }
  const m = /^\s*(?:\/aidd\s+approve\s+all|(?:i\s+)?approve\s+all(?:\s+from\s+now\s+on)?|automate(?:\s+it|\s+all|\s+everything)?)(\s*,?\s+(?:but|except)\s+major)?\s*[.!]?\s*$/i.exec(text)
  return m ? (m[1] ? 'all-but-major' : 'all') : null
}

// What a typed prompt approves: Spec ids ("approve SPEC-1", "I approve SPEC-1 and SPEC-4", "approve": [] for what
// waits on you), or 'merge' ("approve the merge", "approve merging"), or null when the prompt is anything else, which
// goes to the model as typed.
export function approvalIds(text: string): string[] | 'merge' | null {
  const m = /^\s*(?:i\s+)?approved?\b([\s\S]*)$/i.exec(text)
  if (!m) {
    return null
  }
  const words = (m[1] ?? '').split(/[\s,.;!&+]+/).filter(Boolean)
  const ids: string[] = []
  let merge = false
  for (const word of words) {
    if (/^[A-Za-z][A-Za-z0-9]*-[0-9]+$/.test(word)) {
      ids.push(word.toUpperCase())
    } else if (/^merg(e|ing)$/i.test(word)) {
      merge = true
    } else if (!FILLER.has(word.toLowerCase())) {
      return null
    }
  }
  if (merge) {
    return ids.length === 0 ? 'merge' : null
  }

  return [...new Set(ids)]
}

// "ship", "ship it", "ship this branch", typed by the person: local-first only (`aidd ship`), else null.
export const isShip = (text: string): boolean => /^\s*(?:please\s+)?ship(?:\s+(?:it|this|this branch|now))?\s*[.!]?\s*$/i.test(text)

// How long `aidd ship` may run from the prompt: it runs the tests again on what lands.
export const SHIP_TIMEOUT_MS = 600_000

// `/aidd <verb> [rest]`: aidd's front door. The command is the aidd skill, as a project skill (`aidd`) or the plugin's
// (`aidd:aidd`). With no verb it loads the skill for the agent as before, so this returns null and the hook passes it on.
export type AiddVerb = { verb: string; rest: string }

export function aiddVerb(command: string, args: string): AiddVerb | null {
  if (command !== 'aidd' && command !== 'aidd:aidd') {
    return null
  }
  const [verb = '', ...rest] = args.trim().split(/\s+/).filter(Boolean)
  return verb === '' ? null : { verb: verb.toLowerCase(), rest: rest.join(' ') }
}

export type ProposalAsk = { verb: 'decide' | 'sign-off'; id: string; decision: 'go' | 'no-go' | null; reason: string }

// `/aidd decide PROP-1 go [why]` or `/aidd sign-off PROP-1`: the proposal, and for decide the decision and its reason.
export function proposalAsked(verb: string, rest: string): ProposalAsk | null {
  const [id = '', second = '', ...more] = rest.trim().split(/\s+/).filter(Boolean)
  if (!/^[A-Za-z][A-Za-z0-9]*-\d+$/.test(id)) {
    return null
  }
  if (verb === 'sign-off') {
    return second === '' ? { verb, id: id.toUpperCase(), decision: null, reason: '' } : null
  }
  const decision = second.toLowerCase()
  if (verb !== 'decide' || (decision !== 'go' && decision !== 'no-go')) {
    return null
  }
  return { verb, id: id.toUpperCase(), decision, reason: more.join(' ').replace(/^because\s+/i, '').slice(0, 500) }
}

export const AIDD_HELP = [
  'aidd, from the prompt. Each answers at once, and the model never sees it:',
  '  /aidd status             the pane: what waits on you, this branch, and autopilot (/aidd close hides it)',
  '  /aidd approve [SPEC-1]   approve a Spec; /aidd approve merge approves this branch',
  '  /aidd approve all        let the agent record every approval for you (add "but major" to keep those); /aidd approve stop ends it',
  '  /aidd ship               ship this branch (no platform)',
  '  /aidd decide PROP-1 go   record go or no-go on a proposal (add why after it); /aidd sign-off PROP-1 signs it off',
  '  /aidd update             update the aidd CLI and this repository\'s aidd files, after a dialog',
  '  /aidd install [flags]    adopt aidd here with `aidd init [flags]`, after a dialog (solo unless you name a profile)',
  'Typed by you, approve, ship, decide, and sign-off are recorded at once: your own words are the decision.',
  '  /aidd                    load the aidd skill for the agent',
].join('\n')

// The flags `/aidd install` passes to `aidd init`: solo unless a profile is named, since solo needs no approver list.
export function installArgs(rest: string): string[] {
  const words = rest.split(/\s+/).filter(Boolean)
  return words.some(w => w === '--profile' || w.startsWith('--profile=')) ? words : ['--profile', 'solo', ...words]
}

// What `aidd self-update --check` said: its line, and whether it would change anything.
export function cliUpdate(said: string): { line: string; isDue: boolean } {
  const line = firstLine(said)
  return { line, isDue: /^would update /.test(line) }
}

// What `aidd upgrade` (a dry run) said: the changes it lists, or none when the repository already matches this aidd.
export function repoUpdate(said: string): { lines: string[]; isDue: boolean } {
  const lines = said.split('\n').map(l => l.trimEnd()).filter(l => l.trim() !== '')
  if (lines.length === 0 || /^nothing to update/.test(lines[0] ?? '')) {
    return { lines: [], isDue: false }
  }
  return { lines: lines.filter(l => !/^(The CLI itself|The Claude Code plugins):/.test(l)), isDue: true }
}

// The update dialog: what changes, and where; the person answers once for all of it.
export function updateQuestion(cli: { line: string; isDue: boolean }, repo: { lines: string[]; isDue: boolean }): string {
  const parts: string[] = []
  if (cli.isDue) {
    parts.push(`The aidd CLI: ${cli.line.replace(/^would /, '')}`)
  }
  if (repo.isDue) {
    const shown = repo.lines.slice(0, 8)
    const more = repo.lines.length - shown.length
    parts.push(['This repository\'s aidd files (commit them on a branch afterwards):', ...shown.map(l => `  ${l}`), ...(more > 0 ? [`  and ${more} more`] : [])].join('\n'))
  }
  return [...parts, 'Update now?'].join('\n\n')
}

// How long an update may take: `aidd self-update` installs from git.
export const UPDATE_TIMEOUT_MS = 600_000

// What `aidd approve merge --show` prints: the branch, its head, what changed, and what else the gate waits on.
export type MergePreview = {
  branch: string
  head: string
  spec: string
  changed: string
  decision: string
  pending: string[]
  // What the gate fails on besides the approval: it never stops the person's Merge approval, only the merge.
  failing: string[]
  warnings: string[]
  problems: string[]
  // `aidd ship --show` only: the branch it lands on, and whether the pull request merges on the platform instead.
  baseBranch: string
  mergesOnPlatform: boolean
}

export function mergePreview(raw: Json): MergePreview {
  return {
    baseBranch: text(raw['base_branch']),
    branch: text(raw['branch']),
    head: text(raw['head']),
    spec: text(raw['spec']),
    changed: text(raw['changed']),
    decision: text(raw['decision']),
    pending: strings(raw['pending']),
    failing: strings(raw['failing']),
    warnings: strings(raw['warnings']),
    problems: strings(raw['problems']),
    mergesOnPlatform: raw['merges_on_platform'] === true,
  }
}

// The question the Merge approval dialog asks: the branch, its head, what changed, and what else the gate waits on.
export function mergeQuestion(p: MergePreview): string {
  const waits = p.pending.length > 0 ? p.pending.join(', ') : 'nothing else'
  const warn = p.warnings.length > 0 ? `\n    ! ${p.warnings[0]}` : ''
  const fails = p.failing.length > 0 ? `\n    ! it still fails on ${p.failing.join(', ')}: the merge waits for that fix` : ''

  return (
    `• ${p.branch} at ${p.head.slice(0, 12)}${p.spec ? ` (${p.spec})` : ''}\n    ${p.changed || 'no change'} · ` +
    `besides your approval the gate waits on ${waits}${fails}${warn}\n\nApprove merging ${p.branch}?`
  )
}

// The question the ship dialog asks: what lands where, and that the tests run again first.
export function shipQuestion(p: MergePreview): string {
  const waits = p.pending.length > 0 ? p.pending.join(', ') : 'nothing else'

  return (
    `• ${p.branch} at ${p.head.slice(0, 12)} into ${p.baseBranch}${p.spec ? ` (${p.spec})` : ''}\n    ${p.changed || 'no change'} · ` +
    `besides your approval the gate waits on ${waits}\n    The tests run again first; it lands only if they pass.\n\nShip ${p.branch} into ${p.baseBranch}?`
  )
}

export type Approvable = { id: string; branch: string }

// The Specs waiting on a Spec approval in `aidd list --json`, each with the branch that holds it.
export function approvable(listed: Json): Approvable[] {
  const raw = Array.isArray(listed['steps']) ? (listed['steps'] as Json[]) : []

  return raw.filter(step => text(step['code']) === 'spec.spec_approval' && text(step['id'])).map(step => ({ id: text(step['id']), branch: text(step['branch']) }))
}

// What changed since the person last approved a Spec: the commit that approval named, the files, the first changed lines.
export type Since = { commit: string; files: { path: string; added: string; removed: string }[]; lines: string[]; more: number }

// What `aidd approve spec --show` prints: what a person approves, and why it cannot be recorded.
export type Preview = {
  id: string
  title: string
  acceptance: string[]
  hash: string
  commit: string
  ref: string
  since: Since | null
  // The route, risk dimensions, reversibility, and rollback, in one line, for the go/no-go.
  risk: string
  // The latest `aidd revise`: what was wrong, and the hash it reopened; empty when never revised.
  revised: string
  warnings: string[]
  problems: string[]
}

function since(raw: unknown): Since | null {
  if (typeof raw !== 'object' || raw === null) {
    return null
  }
  const s = raw as Json
  const files = Array.isArray(s['files']) ? (s['files'] as Json[]) : []

  return {
    commit: text(s['commit']),
    files: files.map(f => ({ path: text(f['path']), added: text(f['added']), removed: text(f['removed']) })),
    lines: strings(s['lines']),
    more: typeof s['more'] === 'number' ? s['more'] : 0,
  }
}

export function preview(raw: Json): Preview {
  return {
    id: text(raw['id']),
    title: text(raw['title']),
    acceptance: strings(raw['acceptance']),
    hash: text(raw['hash']),
    commit: text(raw['commit']),
    ref: text(raw['ref']),
    since: since(raw['since']),
    risk: text(raw['risk']),
    revised: text(raw['revised']),
    warnings: strings(raw['warnings']),
    problems: strings(raw['problems']),
  }
}

// A re-approval's change: each file with its counts, then the changed lines, so the person approves the change itself.
function changeLines(s: Since): string {
  const files = s.files.map(f => `    ${f.path}  +${f.added} -${f.removed}`)
  const more = s.more > 0 ? [`      … ${s.more} more changed lines`] : []

  return [`\n    Changed since your last approval (${s.commit.slice(0, 12)}):`, ...files, ...s.lines.map(line => `      ${line}`), ...more].join('\n')
}

// The question the approval dialog asks: each Spec on its own line, what it is and what it freezes, and on a
// re-approval what changed since the last one.
export function approvalQuestion(list: Preview[]): string {
  const lines = list.map(p => {
    const n = p.acceptance.length
    const warn = p.warnings.length ? `\n    ! ${p.warnings[0]}` : ''
    const changed = p.since ? changeLines(p.since) : ''
    const risk = p.risk ? `\n    Risk: ${p.risk}` : ''
    const revised = p.revised ? `\n    Revised: ${p.revised}` : ''
    return `• ${p.id} ${p.title}\n    ${n} acceptance item${n === 1 ? '' : 's'} · commit ${p.commit.slice(0, 12)} · hash ${p.hash.slice(0, 8)}${risk}${revised}${warn}${changed}`
  })
  const what = list.length === 1 ? list[0]!.id : `these ${list.length} Specs`

  return `${lines.join('\n')}\n\nApprove ${what}?`
}

export const map = <A, B>(section: Section<A>, fn: (value: A) => B): Section<B> =>
  section.isOk ? { isOk: true, value: fn(section.value) } : section

const span = (ms: number): string => {
  const minutes = Math.round(Math.abs(ms) / 60_000)
  if (minutes < 1) {
    return 'under 1m'
  }
  if (minutes < 60) {
    return `${minutes}m`
  }
  const hours = Math.floor(minutes / 60)

  return hours < 48 ? `${hours}h${String(minutes % 60).padStart(2, '0')}m` : `${Math.floor(hours / 24)}d`
}

// "1h52m left", "ended 5m ago": relative, so no time zone is needed.
export function until(iso: string, now: number): string {
  const at = Date.parse(iso)

  return Number.isNaN(at) ? iso : at >= now ? `${span(at - now)} left` : `ended ${span(now - at)} ago`
}

export function ago(iso: string, now: number): string {
  const at = Date.parse(iso)

  return Number.isNaN(at) ? iso : `${span(now - at)} ago`
}

const num = (value: unknown): number => (typeof value === 'number' && Number.isFinite(value) ? value : 0)

const rung = (value: unknown): Rung => {
  const r = (typeof value === 'object' && value !== null ? value : {}) as Json
  return { done: num(r['done']), total: num(r['total']), waits: strings(r['waits']) }
}

const age = (value: Json): BranchAge => ({ branch: text(value['branch']), ageDays: num(value['age_days']), behind: num(value['behind']) })

const objects = (value: unknown): Json[] => (Array.isArray(value) ? value.filter((v): v is Json => typeof v === 'object' && v !== null) : [])

// `aidd goal list --json`, as the pane draws it.
export function shape(listed: Json): Shape {
  const flow = (typeof listed['flow'] === 'object' && listed['flow'] !== null ? listed['flow'] : {}) as Json
  const ships = (value: unknown): SmallGoal['ships'] => (value === 'flagged' || value === 'batched' ? value : 'incremental')
  const launchOf = (value: unknown): SmallGoal['launch'] => {
    if (typeof value !== 'object' || value === null) {
      return null
    }
    const l = value as Json
    const state = l['state'] === 'done' || l['state'] === 'waits' ? l['state'] : 'todo'
    return { spec: text(l['spec']), state }
  }
  const goalWarnings = objects(listed['goals']).flatMap(g => strings(g['warnings']))
  return {
    initiatives: objects(listed['initiatives']).map(i => ({ id: text(i['id']), title: text(i['title']), smallGoals: strings(i['small_goals']) })),
    smallGoals: objects(listed['small_goals']).map(g => ({
      id: text(g['id']),
      title: text(g['title']),
      parent: text(g['parent']) || null,
      ships: ships(g['ships']),
      branch: text(g['branch']) || null,
      specs: objects(g['specs']).map(s => ({ id: text(s['id']), status: text(s['status']) })),
      specApproval: rung(g['spec_approval']),
      release: rung(g['release']),
      launch: launchOf(g['launch']),
    })),
    goals: objects(listed['goals']).map(g => ({ ...age(g), releaseReady: g['release_ready'] === true, waiting: strings(g['waiting']) })),
    branches: objects(flow['branches']).map(age),
    warnings: [...goalWarnings, ...strings(flow['warnings'])],
  }
}

// One cell of the ladder: a mark, and whose move it is. ◆ waits on you, ✓ done, a count while it is under way, ·
// still ahead, — not part of this shape.
export type Cell = { mark: string; tone: 'person' | 'done' | 'ahead' | 'none' }

export function cells(goal: SmallGoal): Cell[] {
  const of = (r: Rung): Cell =>
    r.waits.length > 0
      ? { mark: r.total > 1 ? `◆ ${r.done}/${r.total}` : '◆', tone: 'person' }
      : r.total > 0 && r.done >= r.total
        ? { mark: '✓', tone: 'done' }
        : r.done > 0
          ? { mark: `${r.done}/${r.total}`, tone: 'ahead' }
          : { mark: '·', tone: 'ahead' }
  const launch: Cell =
    goal.launch === null
      ? { mark: '—', tone: 'none' }
      : goal.launch.state === 'done'
        ? { mark: '✓', tone: 'done' }
        : goal.launch.state === 'waits'
          ? { mark: '◆', tone: 'person' }
          : { mark: '·', tone: 'ahead' }
  return [{ mark: '✓', tone: 'done' }, of(goal.specApproval), of(goal.release), launch]
}

// The first command in a step's `how`, between backticks, else ''.
const firstCommand = (how: string): string => /`([^`]+)`/.exec(how)?.[1] ?? ''

// The decisions that wait on the person, in the order of the loop: D1 the plan, D2 Spec approval, D3 the release, D4
// the launch, then anything else a person decides. `pilotLast` is autopilot's last step: a plan it made and nobody has
// agreed to yet is D1.
export function decisions(waiting: Step[], found: Shape | null, pilotLast: string | null, isPlanOpen: boolean): Decision[] {
  const launches = new Set((found?.smallGoals ?? []).flatMap(g => (g.launch ? [g.launch.spec] : [])))
  const out: Decision[] = []
  if (isPlanOpen && pilotLast !== null && /^goal\.(product|client) ok/.test(pilotLast)) {
    out.push({ rung: 'D1', label: 'The plan', id: '', title: 'autopilot planned it: agree to go on', type: '/aidd-team:autopilot all' })
  }
  for (const step of waiting) {
    const title = step.title || step.what
    if (step.code === 'spec.spec_approval') {
      out.push({ rung: 'D2', label: 'Spec approval', id: step.id, title, type: `approve ${step.id}` })
    } else if (step.code === 'spec.in_review') {
      const ship = step.how.includes('ship it') ? 'ship it' : 'approve merge'
      out.push(launches.has(step.id) ? { rung: 'D4', label: 'Launch', id: step.id, title, type: ship } : { rung: 'D3', label: 'Release', id: step.id, title, type: ship })
    } else if (step.code === 'goal.release') {
      out.push({ rung: 'D3', label: 'Release', id: step.id, title: step.what, type: `ship it on ${step.id}` })
    } else {
      out.push({ rung: '', label: step.code.split('.').at(-1)?.replace(/_/g, ' ') ?? '', id: step.id, title, type: firstCommand(step.how) })
    }
  }
  const order = ['D1', 'D2', 'D3', 'D4', '']
  return out.sort((a, b) => order.indexOf(a.rung) - order.indexOf(b.rung))
}

// The trunk-based flow in one line: how many branches hold unmerged work, the oldest, and the goals.
export function flowLine(found: Shape): string {
  const n = found.branches.length
  const oldest = found.branches[0]
  const parts = [n === 0 ? 'every branch is merged' : `${n} branch${n === 1 ? '' : 'es'} with unmerged work`]
  if (oldest && oldest.ageDays > 0) {
    parts.push(`oldest ${oldest.branch}, ${oldest.ageDays}d`)
  }
  for (const g of found.goals) {
    parts.push(`${g.branch} ${g.releaseReady ? 'ready to release' : `${g.ageDays}d`}${g.behind ? `, ${g.behind} behind` : ''}`)
  }
  return parts.join(' · ')
}

