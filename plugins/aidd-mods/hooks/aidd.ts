import type { About, Autopilot, BranchAge, Decision, ItemFile, Lease, Link, Parent, Rung, Section, Shape, SmallGoal, Snapshot, Step, Task } from '../types'

// Plain functions over what aidd printed: no engine calls here, so Claude Code reads every $ call in register.tsx.

export const TIMEOUT_MS = 20_000

export const NOT_FOUND = '`aidd` did not start: it is not on the PATH Claude Code was started with. Install it (docs/INSTALL.md).'

type Json = Record<string, unknown>

// The characters that can redraw a terminal or reorder what a person reads: the C0 and C1 controls (line breaks and ESC
// among them), DEL, the bidi marks, embeddings, overrides, and isolates, and the Unicode line and paragraph separators.
// The CLI's `plain()` (src/aidd/cli/commands/decide.py) owns this set; OpenCode's `oneLine` (status.js) uses it too.
const UNSAFE = / *(?:[\u0000-\u001f\u007f-\u009f\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069] *)+/g

// Text from a file or an agent, as the pane shows it: each run of those characters, with the spaces beside it, is one
// space, so a Spec's words can't move the cursor, recolor the pane, or reorder what a person reads.
export const clean = (said: string): string => said.replace(UNSAFE, ' ')

// Every string the pane reads from aidd's JSON is cleaned here, at the boundary, since a title, a Task, a label, or a
// commit subject comes from a file or an agent.
const text = (value: unknown): string => (typeof value === 'string' ? clean(value) : '')

// The first line aidd said, for a failure: the rest is detail the pane has no room for.
export const firstLine = (said: string): string => said.trim().split('\n')[0] ?? ''

// The last line a command printed, for a failure whose reason comes after its progress, such as an installer's.
export const lastLine = (said: string): string =>
  said
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .at(-1) ?? ''

// "aidd", "aidd and aidd-mods", or "aidd, aidd-team, and aidd-mods".
export function andList(words: readonly string[]): string {
  if (words.length <= 2) {
    return words.join(' and ')
  }
  return `${words.slice(0, -1).join(', ')}, and ${words.at(-1)}`
}

// The person's standing approval in force (`aidd list --json`'s `standing`), as the line that says so and how to end
// it, or null when none is. OpenCode's status says the same (status.js `standingLine`).
export function standingNote(raw: Json): string | null {
  const s = raw['standing']
  if (typeof s !== 'object' || s === null) {
    return null
  }
  const standing = s as Json
  const scope = text(standing['scope'])
  const what = `all${scope.includes('and-publish') ? ' and publishing' : ''}${scope.endsWith('but-major') ? ' but major' : ''}`
  const since = text(standing['since']).slice(0, 16).replace('T', ' ')
  return `Standing approval is on, so aidd records your approvals. To end it: \`/aidd stop\`, or type \`stop approving\`. It covers ${what}, since ${since}.`
}

// The word that names an explore branch, in `/aidd explore <topic>` and the typed `explore branch <topic>`, and the
// branch's prefix: one place each to rename (aidd's own are workitems.EXPLORE_WORD and EXPLORE_PREFIX).
export const EXPLORE_WORD = 'explore'
export const EXPLORE_PREFIX = `${EXPLORE_WORD}/`

// `/aidd explore <topic>`: the topic, as the typed words take it (letters, digits, `.`, `_`, `-`), or null.
export function exploreAsked(rest: string): string | null {
  const m = new RegExp(`^(?:branch\\s+)?(?:${EXPLORE_PREFIX})?([A-Za-z0-9][A-Za-z0-9._-]{0,60})$`, 'i').exec(rest.trim())
  return m ? (m[1] ?? null) : null
}

export const EXPLORE_USAGE = `Say \`/aidd ${EXPLORE_WORD} <topic>\`, such as \`/aidd ${EXPLORE_WORD} caching\`: letters, digits, \`.\`, \`_\`, or \`-\`.`

export const exploreQuestion = (branch: string): string =>
  `Move this worktree to the ${EXPLORE_WORD} branch ${branch}? Nothing merges from it as it is, and its edits are free once you type \`${EXPLORE_WORD} branch ${branch.slice(EXPLORE_PREFIX.length)}\`, which aidd records as yours.`

// What changed outside the agent's session since the person's last decision, as a preview (`--show`) lists it: the
// person's answer takes it in as theirs, so a dialog shows it before they answer. `held` marks a change that weakens the
// guard, which only a dialog takes in: one is asked about even from the person's keyboard.
export type Outside = { what: string; restore: string; held: boolean; guard: boolean }[]

export function outside(raw: Json): Outside {
  const listed = Array.isArray(raw['outside_changes']) ? (raw['outside_changes'] as Json[]) : []
  return listed.filter(c => typeof c === 'object' && c !== null).map(c => ({ what: text(c['what']), restore: text(c['restore']), held: c['held'] === true, guard: c['guard'] === true }))
}

// The hash a preview names for what it showed changed, which the confirmed answer passes on (`--outside-hash`), so it
// takes in exactly that; [] when nothing changed.
export const outsideHash = (raw: Json): string[] => {
  const hash = text(raw['outside_hash'])
  return /^[0-9a-f]{64}$/.test(hash) ? ['--outside-hash', hash] : []
}

export const weakens = (changes: Outside): boolean => changes.some(c => c.held)

// What a change asks of the answer: one that could stop the guard itself stays held whatever this dialog answers,
// since only aidd's own MCP dialog or the person's terminal takes it in.
const tag = (c: Outside[number]): string =>
  c.guard ? " (it could stop the guard, so this answer leaves it held: aidd's own dialog or your terminal takes it in)" : c.held ? ' (it weakens the guard)' : ''

// The lines a dialog shows for it, before its question; none when nothing changed.
export function outsideLines(changes: Outside): string {
  if (changes.length === 0) {
    return ''
  }
  const each = changes.map(c => `\n    - ${c.what}${tag(c)} (to put it back: ${c.restore})`).join('')
  return `\n\nSince your last decision, this also changed outside the agent's session, and counts as yours with this answer:${each}`
}

// The line aidd adds after a decision it recorded when something changed outside the session since the last one, or ''.
export const countedLine = (said: string): string =>
  said
    .split('\n')
    .map(line => clean(line).trim())
    .find(line => line.startsWith('Since your last decision')) ?? ''

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

const strings = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string').map(clean) : [])

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
    const text = clean((firstBlank < 0 ? lines : lines.slice(0, firstBlank)).filter(Boolean).join(' ')).trim()
    return real(text) ? text : ''
  }
  const bullets = (lines: string[]) => lines.filter(line => /^\s*[-*] /.test(line)).map(line => clean(line.replace(/^\s*[-*] /, '')).trim())
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

// One plain `key: value` line of a work item's front matter, unquoted and clean; '' when it has none.
export function frontField(source: string, key: string): string {
  const front = /^---\n([\s\S]*?)\n---/.exec(source)?.[1] ?? ''
  const line = new RegExp(`^${key}:\\s*(.+?)\\s*$`, 'm').exec(front)?.[1] ?? ''

  return clean(line.replace(/\s+#.*$/, '').replace(/^(["'])(.*)\1$/, '$2'))
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

// A standing approval's scope: `approve all`, with "and publish" letting the agent publish for the person too, and "but
// major" keeping major changes for them.
export type StandingScope = 'all' | 'all-but-major' | 'all-and-publish' | 'all-and-publish-but-major'

// A standing approval, typed by the person: "approve all" (or "automate"), "and publish", "but major", and "stop
// approving" (`/aidd stop`) ending it. The same phrases aidd's own prompt hook reads (src/aidd/workitems/typed_words.py).
export function standingAsked(text: string): StandingScope | 'stop' | null {
  if (/^\s*(?:\/aidd(?::aidd)?\s+(?:approve\s+)?stop|stop\s+approving(?:\s+for\s+me)?)\s*[.!]?\s*$/i.test(text)) {
    return 'stop'
  }
  const m =
    /^\s*(?:\/aidd(?::aidd)?\s+approve\s+all|(?:i\s+)?approve\s+all(?:\s+from\s+now\s+on)?|automate(?:\s+it|\s+all|\s+everything)?)(\s*,?\s+and\s+publish)?(\s*,?\s+(?:but|except)\s+major)?\s*[.!]?\s*$/i.exec(
      text,
    )
  return m ? (`all${m[1] ? '-and-publish' : ''}${m[2] ? '-but-major' : ''}` as StandingScope) : null
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

// The three steps after Review, each the person's own word, read as aidd's prompt hook reads them
// (src/aidd/workitems/typed_words.py): "land it" lands this branch on the local trunk (`aidd land`); "merge it" is the
// Merge approval on its pull or merge request, with auto-merge; "publish" ("push it", "open a PR") takes it off this
// machine, which aidd's own prompt hook records and the agent runs (`aidd publish`): this mod never pushes.
export const isLand = (text: string): boolean => /^\s*(?:\/aidd(?::aidd)?\s+land|(?:please\s+)?land(?:\s+(?:it|this|this branch|now))?)\s*[.!]?\s*$/i.test(text)

export const isMergeIt = (text: string): boolean =>
  /^\s*(?:\/aidd(?::aidd)?\s+merge|(?:please\s+)?merge(?:\s+(?:it|this|now|(?:the|this)\s+(?:pr|mr|pull\s+request|merge\s+request)))?)\s*[.!]?\s*$/i.test(text)

export const isPublish = (text: string): boolean =>
  /^\s*(?:\/aidd(?::aidd)?\s+publish|(?:please\s+)?(?:publish|push)(?:\s+(?:it|this|this branch|now|to\s+(?:the\s+)?remote))?|(?:please\s+)?(?:open|create|make)\s+(?:a|the)\s+(?:pr|mr|pull\s+request|merge\s+request))\s*[.!]?\s*$/i.test(
    text,
  )

// "ship it" named all three once: it records nothing now, and says which word to type.
export const isRetiredShip = (text: string): boolean => /^\s*(?:\/aidd(?::aidd)?\s+ship|(?:please\s+)?ship(?:\s+(?:it|this|this branch|now))?)\s*[.!]?\s*$/i.test(text)


export const SHIP_RETIRED =
  '`ship it` named three steps: `land it` lands this branch on the local trunk, `publish` takes it off this machine, and `merge it` merges its PR/MR.'

// Where a branch stands for "land it" and "merge it": its pull or merge request merges on the platform, or it lands here.
export const ON_A_PLATFORM = 'This branch is on its platform, where its pull or merge request merges: type `merge it` there.'
export const NOT_ON_A_PLATFORM = 'This branch is not on a platform yet: type `land it` to land it on the local trunk, or `publish` to push it and open its PR/MR.'

// How long `aidd land` may run from the prompt: it runs the tests again on what lands.
export const LAND_TIMEOUT_MS = 600_000

// `/aidd <verb> [rest]`: aidd's front door. The command is the aidd skill, as a project skill (`aidd`) or the plugin's
// (`aidd:aidd`). With no verb it is the menu of the person's decisions (`menu`).
export type AiddVerb = { verb: string; rest: string }

export function aiddVerb(command: string, args: string): AiddVerb | null {
  if (command !== 'aidd' && command !== 'aidd:aidd') {
    return null
  }
  const [verb = '', ...rest] = args.trim().split(/\s+/).filter(Boolean)
  return { verb: verb === '' ? 'menu' : verb.toLowerCase(), rest: rest.join(' ') }
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
  '  /aidd                    every decision that is yours, and the words that make it',
  '  /aidd status             the pane: what waits on you, this branch, and autopilot (/aidd close hides it)',
  '  /aidd approve [SPEC-1]   approve a Spec; /aidd approve merge approves this branch',
  '  /aidd approve all        let the agent record every approval for you (add "and publish", or "but major" to keep those)',
  '  /aidd stop               end that standing approval',
  '  /aidd land               land this branch on the local trunk, once the gate passes',
  '  /aidd publish            what would leave this machine; type `publish` to push it and open its PR/MR',
  '  /aidd merge              approve merging this branch\'s PR/MR, which merges once `aidd/gate` passes',
  '  /aidd decide PROP-1 go   record go or no-go on a proposal (add why after it); /aidd sign-off PROP-1 signs it off',
  `  /aidd ${EXPLORE_WORD} <topic>     move this worktree to a throwaway branch where every edit is free`,
  '  /aidd update             update the aidd CLI, this repository\'s aidd files, and the Claude Code plugins, after a dialog',
  '  /aidd init [flags]       adopt aidd here with `aidd init [flags]`, after a dialog (solo unless you name a profile)',
  '  /aidd skill              load the aidd skill for the agent',
  'Typed by you, the words /aidd lists are recorded at once: your own words are the decision.',
].join('\n')

// `/aidd` alone: every decision that is the person's, one line each: the words to type, the verb, and when it is
// theirs. OpenCode's terminal lists the same (status.js `menuLines`), and tests/test_opencode.py holds both to one list.
export const AIDD_MENU = [
  'Your decisions. Type the words at the prompt, or run the /aidd verb beside them:',
  '  approve SPEC-1          /aidd approve SPEC-1     a Spec waits on you: approve it as it reads, and the agent builds it',
  '  approve merge           /aidd approve merge      a reviewed branch: your Merge approval of its head',
  '  land it                 /aidd land               a reviewed branch: land it on your local trunk once the gate passes',
  '  publish                 /aidd publish            take this branch off your machine: push it and open its PR/MR',
  '  merge it                /aidd merge              a branch with a PR/MR: approve it, and it merges once aidd/gate passes',
  '  approve all             /aidd approve all        let the agent approve for you until you stop it (add "and publish" or "but major")',
  '  stop approving          /aidd stop               end that standing approval: each decision waits on you again',
  '  decide PROP-1 go        /aidd decide PROP-1 go   a proposal waits on your go or no-go (add why after it)',
  '  sign off PROP-1         /aidd sign-off PROP-1    a proposal is ready to send, as it reads now',
  `  ${EXPLORE_WORD} branch <topic>  /aidd ${EXPLORE_WORD} <topic>    try an idea on a throwaway branch: every edit is free, and nothing merges from it`,
  '"approve" alone approves every Spec that waits on you. /aidd status shows what waits on you now, and /aidd help lists every verb.',
].join('\n')

// The flags `/aidd init` passes to `aidd init`: solo unless a profile is named, since solo needs no approver list.
export function initArgs(rest: string): string[] {
  const words = rest.split(/\s+/).filter(Boolean)
  return words.some(w => w === '--profile' || w.startsWith('--profile=')) ? words : ['--profile', 'solo', ...words]
}

// What `aidd self-update --check` said: its line, whether it would change anything, and whether it said this CLI is
// the latest. `failed` is why the check could not run (offline, or before the first release), so a failed check never
// reads as up to date. Any other line, such as a checkout's, leaves the CLI unknown, never current.
export type CliCheck = { line: string; isDue: boolean; isCurrent: boolean; failed?: string }

export function cliUpdate(said: string): CliCheck {
  const line = clean(firstLine(said))
  return { line, isDue: /^would update /.test(line), isCurrent: / is up to date: the latest is /.test(line) }
}

export const cliChecked = (said: Ran): CliCheck =>
  said.isOk ? cliUpdate(said.value) : { line: '', isDue: false, isCurrent: false, failed: said.error }

// What `aidd upgrade` (a dry run) said: the changes it lists, or none when the repository already matches this aidd.
// `failed` is why the dry run could not run, so a failed one is said, never dropped.
export type RepoCheck = { lines: string[]; isDue: boolean; failed?: string }

export function repoUpdate(said: string): RepoCheck {
  const lines = said.split('\n').map(l => clean(l).trimEnd()).filter(l => l.trim() !== '')
  if (lines.length === 0 || /^nothing to update/.test(lines[0] ?? '')) {
    return { lines: [], isDue: false }
  }
  return { lines: lines.filter(l => !/^(The CLI itself|The Claude Code plugins):/.test(l)), isDue: true }
}

export const repoChecked = (said: Ran): RepoCheck => (said.isOk ? repoUpdate(said.value) : { lines: [], isDue: false, failed: said.error })

// Why this repository's aidd files don't update on a CLI that may be behind, in OpenCode's words too (status.js
// `REPO_WAITS`): `aidd upgrade` writes the files of the CLI that runs it, so an older CLI would write older files.
export const REPO_WAITS =
  "This repository's aidd files wait, because aidd can't tell that this CLI is current, and an older one would write older files over newer ones. Update the CLI (docs/INSTALL.md), then run `aidd upgrade --yes`."

// What each check found, in OpenCode's words too (status.js `checkParts`): what would change, why a check could not
// run, or that aidd is up to date.
export function checkParts(cli: CliCheck, repo: RepoCheck): string[] {
  if (!cli.isDue && !repo.isDue && !cli.failed && !repo.failed) {
    return [`aidd is up to date. ${cli.line}`.trim()]
  }
  const parts: string[] = []
  if (cli.failed) {
    parts.push(`aidd could not check for a new CLI: ${cli.failed}`)
  } else if (cli.isDue) {
    parts.push(`The aidd CLI: ${cli.line.replace(/^would /, '')}`)
  } else if (cli.line) {
    parts.push(cli.line)
  }
  if (repo.failed) {
    parts.push(`aidd could not check this repository's files: ${repo.failed}`)
  } else if (repo.isDue) {
    const shown = repo.lines.slice(0, 8)
    const more = repo.lines.length - shown.length
    parts.push(['This repository\'s aidd files (commit them on a branch afterwards):', ...shown.map(l => `  ${l}`), ...(more > 0 ? [`  and ${more} more`] : [])].join('\n'))
    if (!cli.isDue && !cli.isCurrent) {
      parts.push(REPO_WAITS)
    }
  } else {
    parts.push('This repository\'s aidd files are up to date.')
  }
  return parts
}

// What `aidd self-update` did: its first line, or why it failed. The installer prints its progress first, so the
// reason is the last line it printed.
export function cliUpdated(done: Ran): string {
  if (done.isOk) {
    return firstLine(done.value)
  }
  return `The CLI was not updated: ${(clean(lastLine(done.stderr ?? '')) || done.error).replace(/\.$/, '')}.`
}

// The Claude Code plugins aidd's marketplace serves. Each is versioned by its commit, so an update brings the newest.
export const PLUGINS = ['aidd@aidd', 'aidd-team@aidd', 'aidd-mods@aidd'] as const

export const shortName = (plugin: string): string => plugin.replace(/@aidd$/, '')

// What each plugin update came to, as the person reads it: the ones updated and the next step, the ones not installed
// here, and why any failed, with the way by hand that `aidd upgrade` and docs/INSTALL.md name.
export function pluginsSaid(updated: string[], absent: string[], failed: { plugin: string; reason: string }[]): string {
  const said: string[] = []
  const plugins = (names: string[]) => `plugin${names.length === 1 ? '' : 's'} ${andList(names)}`
  if (updated.length > 0) {
    said.push(`Updated the Claude Code ${plugins(updated)}: run /reload-plugins to load ${updated.length === 1 ? 'it' : 'them'}.`)
  }
  if (absent.length > 0) {
    said.push(`The Claude Code ${plugins(absent)} ${absent.length === 1 ? 'is' : 'are'} not installed here.`)
  }
  const reasons = new Map<string, string[]>()
  for (const { plugin, reason } of failed) {
    reasons.set(reason, [...(reasons.get(reason) ?? []), shortName(plugin)])
  }
  for (const [reason, names] of reasons) {
    const which = names.length === PLUGINS.length ? 'plugins were' : `${plugins(names)} ${names.length === 1 ? 'was' : 'were'}`
    said.push(`The Claude Code ${which} not updated: ${reason.replace(/\.$/, '')}.`)
  }
  if (failed.length > 0) {
    const updates = failed.map(f => `\`claude plugin update ${f.plugin}\``)
    said.push(`In a terminal, run \`claude plugin marketplace update aidd\`, then ${andList(updates)}. Then run /reload-plugins here.`)
  }
  return said.length > 0 ? said.join(' ') : 'The Claude Code plugins are up to date.'
}

// The update dialog: what changes, and where; the person answers once for all of it. The plugins are always in it,
// because only an update can tell whether a newer commit waits.
export function updateQuestion(cli: CliCheck, repo: RepoCheck): string {
  const plugins = `The Claude Code plugins: ${andList(PLUGINS.map(shortName))}, at the newest commit of their marketplace.`
  return [...checkParts(cli, repo), plugins, 'Update now?'].join('\n\n')
}

// What a command said: on a failure, its `stdout` and `stderr` too. A `--json` command puts its result line on stdout.
export type Ran = { isOk: true; value: string } | { isOk: false; error: string; stdout?: string; stderr?: string }

// The last line a command printed, as a JSON object, or null when it isn't one.
function lastJson(said: string): Json | null {
  try {
    const parsed: unknown = JSON.parse(said.trim().split('\n').at(-1) ?? '')
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? (parsed as Json) : null
  } catch {
    return null
  }
}

const literally = (said: string): string => said.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// What `claude plugin update <plugin> --json` said: `updated`, `current`, `absent` (not installed here, so nothing to
// update), or the reason it failed. Its JSON `failureCode` decides first. Without one, only Claude Code's own "not
// installed" or "not found" message for this plugin is absent. Output with no update outcome, or one other than
// `updated` and `up_to_date`, is a failure.
export function pluginUpdate(plugin: string, said: Ran): 'updated' | 'current' | 'absent' | { failed: string } {
  if (!said.isOk) {
    const result = lastJson(said.stdout ?? '')
    const code = text(result?.['failureCode'])
    if (code !== '') {
      return code === 'not_installed' || code === 'not_found' ? 'absent' : { failed: text(result?.['message']) || said.error }
    }
    const name = literally(plugin.replace(/@.*$/, ''))
    const absent = new RegExp(`^(?:✘ )?Failed to update plugin "${literally(plugin)}": Plugin "${name}(?:@[^"]*)?" (?:is not installed|not found)\\.?$`)
    return absent.test(said.error) ? 'absent' : { failed: said.error }
  }
  const outcome = text(lastJson(said.value)?.['updateOutcome'])
  if (outcome === '') {
    return { failed: 'claude printed no update outcome' }
  }
  // Only the outcomes Claude Code is known to print count; any other is no proof that the plugin is current.
  return outcome === 'updated' ? 'updated' : outcome === 'up_to_date' ? 'current' : { failed: `claude printed an update outcome aidd does not know: ${outcome}` }
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
  // What changed outside the agent's session since the person's last decision, which their answer takes in, and the
  // flags that name what it showed.
  outside: Outside
  seen: string[]
  problems: string[]
  // `aidd land --show` only: the branch it lands on, and whether the pull request merges on the platform instead.
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
    outside: outside(raw),
    seen: outsideHash(raw),
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
    `besides your approval the gate waits on ${waits}${fails}${warn}${outsideLines(p.outside)}\n\nApprove merging ${p.branch}?`
  )
}

// The question the land dialog asks: what lands where, and that the tests run again first.
export function landQuestion(p: MergePreview): string {
  const waits = p.pending.length > 0 ? p.pending.join(', ') : 'nothing else'

  return (
    `• ${p.branch} at ${p.head.slice(0, 12)} on ${p.baseBranch}${p.spec ? ` (${p.spec})` : ''}\n    ${p.changed || 'no change'} · ` +
    `besides your approval the gate waits on ${waits}\n    The tests run again first; it lands only if they pass.${outsideLines(p.outside)}\n\n` +
    `Land ${p.branch} on ${p.baseBranch}?`
  )
}

// What `aidd publish --show` says would leave this machine, as the lines `/aidd publish` shows, or null when it said
// nothing readable.
export function publishPlan(raw: Json): string | null {
  const branch = text(raw['branch'])
  if (branch === '') {
    return null
  }
  const n = typeof raw['commits'] === 'number' ? raw['commits'] : 0
  const pr = raw['pull_request'] === true ? `, then a pull request into ${text(raw['base'])}` : ''
  const shown = strings(raw['shown']).map(c => `  ${c}`)
  return [
    `Would leave this machine: ${branch} at ${text(raw['head']).slice(0, 12)} to ${text(raw['remote'])}/${text(raw['to'])}${pr} (${n} commit${n === 1 ? '' : 's'} the remote lacks)`,
    ...shown,
    ...outside(raw).map(c => `Since your last decision, ${c.what}: it counts as yours when you publish (to put it back: ${c.restore})`),
    'To publish it, type `publish` at the prompt: aidd records it from your words, and the agent runs `aidd publish`. Or run `aidd publish` in your own terminal.',
  ].join('\n')
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
  commit: string
  ref: string
  since: Since | null
  // The route, risk dimensions, reversibility, and rollback, in one line, for the go/no-go.
  risk: string
  // The latest `aidd revise`: what was wrong, and the hash it reopened; empty when never revised.
  revised: string
  warnings: string[]
  // What changed outside the agent's session since the person's last decision, which their answer takes in, and the
  // flags that name what it showed.
  outside: Outside
  seen: string[]
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
    commit: text(raw['commit']),
    ref: text(raw['ref']),
    since: since(raw['since']),
    risk: text(raw['risk']),
    revised: text(raw['revised']),
    warnings: strings(raw['warnings']),
    outside: outside(raw),
    seen: outsideHash(raw),
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
    return `• ${p.id} ${p.title}\n    ${n} acceptance item${n === 1 ? '' : 's'} · commit ${p.commit.slice(0, 12)}${risk}${revised}${warn}${changed}`
  })
  const what = list.length === 1 ? list[0]!.id : `these ${list.length} Specs`
  const changed = [...new Map(list.flatMap(p => p.outside).map(c => [c.what, c])).values()]

  return `${lines.join('\n')}${outsideLines(changed)}\n\nApprove ${what}?`
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
  const reaches = (value: unknown): SmallGoal['reaches'] => (value === 'flagged' || value === 'batched' ? value : 'incremental')
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
      reaches: reaches(g['reaches']),
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
    } else if (step.code === 'spec.merge_approval') {
      const words = step.how.includes('land it') ? 'land it' : step.how.includes('merge it') ? 'merge it' : 'approve merge'
      out.push(launches.has(step.id) ? { rung: 'D4', label: 'Launch', id: step.id, title, type: words } : { rung: 'D3', label: 'Release', id: step.id, title, type: words })
    } else if (step.code === 'spec.publish') {
      out.push({ rung: 'D3', label: 'Publish', id: step.id, title, type: 'publish' })
    } else if (step.code === 'goal.release') {
      out.push({ rung: 'D3', label: 'Release', id: step.id, title: step.what, type: `land it on ${step.id}` })
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
