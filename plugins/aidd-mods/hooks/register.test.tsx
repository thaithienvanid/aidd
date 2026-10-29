import type { CommandRunInput, On, ProcessRunResult } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { andList, checkParts, cliChecked, cliUpdate, cliUpdated, plainTyped, pluginsSaid, publishPlan, REPO_WAITS, repoChecked, shape, updateQuestion } from './aidd'
import { about, aiddVerb, AIDD_HELP, AIDD_MENU, countedLine, EXPLORE_PREFIX, exploreAsked, exploreQuestion, landQuestion, mergeQuestion, mergePreview, approvalIds, approvalQuestion, autopilot, clean, pluginUpdate, frontTitle, initArgs, isLand, isMergeIt, isPublish, isRetiredShip, exploreNote, itemFiles, livingNote, NOT_FOUND, NOT_ON_A_PLATFORM, ON_A_PLATFORM, preview, proposalAsked, repoUpdate, SHIP_RETIRED, specsFolder, standingAsked, standingNote, steps, until } from './aidd'
import { groups, unblocks } from './register'

const ROOT = '/work/shop'

const RUN: CommandRunInput = {
  command: 'aidd',
  args: 'status',
  origin: { kind: 'composer' },
  presentation: { isFullscreen: true, columns: 160 },
}

const PANE = {
  plugin: 'aidd-mods',
  component: 'Pane',
  requestId: 'aidd-status',
  props: { title: 'aidd', isFocused: false, bodyColumns: 90, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

// The root's `height`: set while docked, so the bottom rows stay put; absent inline.
const heightOf = (drawn: unknown): unknown => (drawn as { props?: Record<string, unknown> }).props?.['height']

const out = (exitCode: number, stdout: string, stderr = ''): ProcessRunResult => ({
  exitCode,
  stdout,
  stderr,
  isStdoutTruncated: false,
  isStderrTruncated: false,
})

const BRANCH = {
  schema_version: '1',
  steps: [
    {
      code: 'spec.spec_approval',
      id: 'SPEC-1',
      where: 'specs/SPEC-1.md',
      what: 'SPEC-1 waits for Spec approval of its current hash',
      who: 'Approver',
      how: 'read the Spec, then approve the hash `aidd hash specs/SPEC-1.md` prints',
      priority: 'high',
      status: 'draft',
      owner: '@me',
      labels: ['area:loop'],
      why: [{ kind: 'goal', text: 'g' }, { kind: 'initiative', id: 'INIT-1', progress: '0/3' }, { kind: 'epic', id: 'EPIC-1', progress: '0/3' }],
      tasks: [
        {
          id: 'SPEC-1-T1',
          title: 'Write the event on a local gate run',
          scope: ['src/aidd/gate/', 'tests/test_gate_events.py'],
          depends_on: [],
          assignee: 'agent:developer',
          role: 'developer',
          status: 'blocked',
          why: 'the Spec waits for Spec approval; no Task starts before it',
        },
        { id: 'SPEC-1-T2', title: 'Read it in aidd metrics', scope: ['src/aidd/tracking/'], depends_on: ['SPEC-1-T1'], assignee: 'agent:developer', role: 'developer', status: 'todo', why: '' },
      ],
      files: [
        { path: 'specs/SPEC-1/tech-spec-local-events.md', kind: 'tech-spec' },
        { path: 'specs/SPEC-1/explore/where-events-live', kind: 'exploration', question: 'Where do the events live?', status: 'decided' },
        { path: 'specs/SPEC-1/explore/retention', kind: 'exploration', question: 'How long are events kept?', status: 'open', owner: 'architect' },
      ],
      blocked: false,
    },
    {
      code: 'spec.blocked_by',
      id: 'SPEC-2',
      where: 'specs/SPEC-2.md',
      what: 'SPEC-2 is blocked by SPEC-1: it starts when they finish',
      who: 'author',
      how: 'finish or re-plan what it waits for',
      priority: 'high',
      waiting_on: ['SPEC-1'],
      why: [{ kind: 'goal', text: 'g' }, { kind: 'initiative', id: 'INIT-1', progress: '0/3' }, { kind: 'epic', id: 'EPIC-2', progress: '0/1' }],
      blocked: true,
    },
    { code: 'spec.in_progress', id: 'SPEC-3', where: '../outside.md', what: 'SPEC-3 is being built', who: 'agent', how: '/aidd-team:implement', priority: 'low' },
  ],
}
const WAITING = { schema_version: '1', steps: [{ code: 'nothing_matches', what: 'nothing matches these filters', who: 'author', how: 'drop a filter' }] }
const PILOT = {
  schema_version: '1',
  leases: [{ by: 'me@example.com', expires_at: '2026-10-15T10:06:40Z', session_id: 'ab61ae4e-2f94', started_at: '2026-10-15T08:06:40Z', timebox: '2h', work: 'all', stale: false }],
  journal: [{ at: '2026-10-14T08:13:03Z', code: 'ask.product', result: 'ok', tokens: 186350, work: 'all' }],
  notices: [{ event: 'finished', reason: 'stopped', work: 'all' }],
}

const FILES: Record<string, string> = {
  [`${ROOT}/specs/SPEC-1.md`]: [
    '---',
    'id: SPEC-1',
    'title: "Local gate runs keep their events in the git directory"',
    'hypothesis: "Changes with a local event trail: 0 percent to 100 percent, checked 2026-11-30"',
    '---',
    '## Intent',
    '> "improve the loop" (the owner)',
    '',
    '## Problem',
    '<!-- what is wrong, for whom -->',
    'The maintainer cannot see where a change spends its time.',
    '`aidd metrics` needs an event file, and this repository has none.',
    '',
    'A second paragraph the pane leaves out.',
    '',
    '## Goals',
    '- A local `aidd gate` appends its event.',
    '- `aidd metrics` reads that file.',
    '- TODO: a placeholder goal',
    '',
    '## Acceptance',
    '```gherkin',
    'Scenario: A1 a local gate run leaves one event',
    '  Given a repository',
    'Scenario: A2 metrics reads it',
    '```',
    '',
    '## Design',
    'Long text the pane never shows.',
  ].join('\n'),
  [`${ROOT}/specs/SPEC-2.md`]: '---\ntitle: One suite run per head\n---\n',
  [`${ROOT}/specs/INIT-1.md`]: '---\ntitle: A faster loop\n---\n',
  [`${ROOT}/specs/INIT-2.md`]: '---\nkind: initiative\ntitle: The booking app\nproposal: PROP-0\n---\n',
  [`${ROOT}/proposals/PROP-1/proposal.md`]: [
    '---',
    'kind: proposal',
    'id: PROP-1',
    'title: Rebuild the booking app',
    'audience: client',
    'addressee: Clinic board',
    'goal: "Patients book a visit in under a minute"  # the outcome they can check',
    '---',
    '## Summary',
    'A short pitch.',
    '',
    '## The need',
    'Booking takes a phone call today, and the clinic misses calls at lunch.',
    '',
    '## Estimate',
    'Not shown.',
  ].join('\n'),
  [`${ROOT}/specs/EPIC-1.md`]: '---\ntitle: Cut repeated work\n---\n',
  [`${ROOT}/specs/EPIC-2.md`]: '---\ntitle: Shorten the wait\n---\n',
}

// The session's project root, what each command prints there, and the Spec files.
function answer(on: On, said: Record<string, ProcessRunResult>, seen: string[] = [], read: string[] = []) {
  const clock = mock.clock(on)
  on('session.root', () => ({ value: ROOT }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('fs.read', (_$, e) => {
    read.push(e.path)
    const file = FILES[e.path]
    return file === undefined ? { deny: 'no such file' } : { value: file }
  })
  on('process.run', (_$, e) => {
    const line = e.argv.join(' ')
    seen.push(`${e.init?.cwd} ${line}`)
    const reply = said[line]
    return reply ? { value: reply } : { deny: `unexpected: ${line}` }
  })

  return clock
}

// `aidd goal list --json`: INIT-1 with two small goals, one in review that waits on the person's release.
const SHAPE = {
  schema_version: '1',
  goals: [],
  flow: { branches: [{ branch: 'plan/loop-efficiency', head: 'abc', age_days: 3, behind: 2 }], warnings: ['plan/loop-efficiency is 3 days old, past limits.max_branch_age_days = 2: land it today (behind a flag if unfinished), or split it'] },
  initiatives: [{ id: 'INIT-1', title: 'A faster loop', small_goals: ['EPIC-1', 'EPIC-2'] }],
  small_goals: [
    {
      id: 'EPIC-1', title: 'Cut repeated work', parent: 'INIT-1', reaches: 'incremental', branch: null,
      specs: [{ id: 'SPEC-1', status: 'draft' }, { id: 'SPEC-3', status: 'in_progress' }],
      plan: 'agreed', spec_approval: { done: 1, total: 2, waits: ['SPEC-1'] }, release: { done: 0, total: 2, waits: [] }, launch: null,
    },
    {
      id: 'EPIC-2', title: 'Shorten the wait', parent: 'INIT-1', reaches: 'flagged', branch: null,
      specs: [{ id: 'SPEC-2', status: 'landed' }, { id: 'SPEC-4', status: 'in_review' }],
      plan: 'agreed', spec_approval: { done: 2, total: 2, waits: [] }, release: { done: 1, total: 1, waits: [] }, launch: { spec: 'SPEC-4', state: 'waits' },
    },
  ],
}

const AIDD = {
  'git rev-parse --abbrev-ref HEAD': out(0, 'plan/loop-efficiency\n'),
  'aidd goal list --json': out(0, JSON.stringify(SHAPE)),
  'aidd list --branch --json': out(0, JSON.stringify(BRANCH)),
  'aidd list --waiting-on-me --json': out(0, JSON.stringify(WAITING)),
  'aidd autopilot status --json': out(0, JSON.stringify(PILOT)),
}

test('reads aidd JSON: placeholders dropped, waits, the why chain and tasks kept', async () => {
  expect(steps(WAITING)).toEqual([])
  const parsed = steps(BRANCH)
  const first = parsed.find(step => step.id === 'SPEC-1')
  const second = parsed.find(step => step.id === 'SPEC-2')
  expect([first?.id, first?.what, first?.why, first?.tasks]).toEqual(['SPEC-1', 'waits for Spec approval of its current hash', 'INIT-1 (0/3) → EPIC-1 (0/3)', '2 tasks: 1 blocked, 1 todo'])
  expect(first?.taskList.map(task => [task.id, task.status, task.scope.length, task.dependsOn])).toEqual([
    ['SPEC-1-T1', 'blocked', 2, []],
    ['SPEC-1-T2', 'todo', 1, ['SPEC-1-T1']],
  ])
  expect([second?.id, second?.waitingOn, second?.isBlocked]).toEqual(['SPEC-2', ['SPEC-1'], true])
  const at = Date.parse('2026-10-15T08:14:00Z')
  expect(autopilot(PILOT, at).last).toBe('ask.product ok · 186k tokens · 24h01m ago')
  expect(until('2026-10-15T10:06:40Z', at)).toBe('1h53m left')
  expect(until('2026-10-15T08:00:00Z', at)).toBe('ended 14m ago')
  expect(frontTitle(FILES[`${ROOT}/specs/SPEC-1.md`] ?? '')).toBe('Local gate runs keep their events in the git directory')
  expect(frontTitle('no front matter\ntitle: x\n')).toBe('')
})

test('cards: a person first, then the agent, then blocked; one card per kind of step', async () => {
  const cards = groups([], steps(BRANCH))
  expect(cards.map(card => [card.title, card.tone, card.steps.map(step => step.id)])).toEqual([
    ['Needs Spec approval', 'person', ['SPEC-1']],
    ['Being built', 'agent', ['SPEC-3']],
    ['Waiting on other work', 'waiting', ['SPEC-2']],
  ])
  const mine = steps({ steps: [{ code: 'spec.spec_approval', id: 'SPEC-1', what: 'x', who: 'Approver' }] })
  expect(groups(mine, steps(BRANCH)).map(card => card.title)).toEqual(['Waiting on you', 'Being built', 'Waiting on other work'])
  expect(groups([], steps({ steps: [{ code: 'spec.new_kind', id: 'SPEC-9', what: 'x', who: 'author' }] }))[0]?.title).toBe('New kind')
  // Two overdue kinds get two headings, never two cards both called "Overdue".
  const due = steps({ steps: [{ code: 'flag.overdue', id: 'SPEC-4', what: 'x', who: 'author' }, { code: 'deprecation.overdue', id: 'SPEC-5', what: 'y', who: 'author' }] })
  expect(groups([], due).map(card => card.title).sort()).toEqual(['Flag cleanup overdue', 'Past its sunset'])
})

test('the command opens the pane and writes nothing the model reads', async ($, on) => {
  const seen: string[] = []
  const read: string[] = []
  answer(on, AIDD, seen, read)
  const result = await $.command.run(RUN)
  expect(result.text).toBeUndefined()
  expect(result.context).toBeUndefined()
  expect(seen.sort()).toEqual(Object.keys(AIDD).map(line => `${ROOT} ${line}`).sort())
  // Only work-item files inside the repository are read, for their titles.
  expect(read.sort()).toEqual([`${ROOT}/specs/SPEC-1.md`, `${ROOT}/specs/SPEC-2.md`])
})

test('the pane shows cards, titles, waits and the first item in detail, on every surface', async ($, on) => {
  answer(on, AIDD)
  await $.command.run(RUN)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ text: /^Needs Spec approval$/ })).toBeDefined()
    expect(await ui.find({ text: /Local gate runs keep their events in the git directory/ })).toBeDefined()
    expect(await ui.find({ text: /waits on SPEC-1/ })).toBeDefined()
    expect(await ui.find({ text: /1 wait on it/ })).toBeDefined()
    expect(await ui.find({ text: '1 need you' })).toBeDefined()
    expect(await ui.find({ text: '1 waiting on other work' })).toBeDefined()
    expect(await ui.find({ text: 'INIT-1 (0/3) → EPIC-1 (0/3)' })).toBeDefined()
    expect(await ui.find({ text: 'aidd hash specs/SPEC-1.md' })).toBeDefined()
    expect(await ui.find({ text: /plan\/loop-efficiency/ })).toBeDefined()
    expect(await ui.find({ text: / · told you: finished \(stopped\)/ })).toBeDefined()
    // Autopilot has one line, pinned at the bottom; the summary counts the work only.
    expect(await ui.find({ text: /waiting on other work · autopilot/i })).toBeUndefined()
    expect(await ui.find({ text: /↑↓ move · Enter open · a all/ })).toBeDefined()
    await ui.unmount()
  }
})

test('choosing a row shows that item in detail', async ($, on) => {
  answer(on, AIDD)
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ text: 'finish or re-plan what it waits for' })).toBeUndefined()
  await ui.press({ key: 'row-SPEC-2' })
  expect(await ui.find({ text: 'finish or re-plan what it waits for' })).toBeDefined()
  await ui.unmount()
})

test('a failure is one red line; the rest still shows', async ($, on) => {
  answer(on, {
    ...AIDD,
    'aidd list --branch --json': out(2, '', 'aidd: git rev-parse --show-toplevel: fatal: not a git repository\nmore detail\n'),
    'aidd autopilot status --json': out(0, 'not json'),
  })
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ text: 'aidd: git rev-parse --show-toplevel: fatal: not a git repository' })).toBeDefined()
  expect(await ui.find({ text: /more detail/ })).toBeUndefined()
  expect(await ui.find({ text: /not JSON/ })).toBeDefined()
  await ui.unmount()
})

test('a failed list of what waits on you shows its reason, and never says nothing needs you', async ($, on) => {
  answer(on, { ...AIDD, 'aidd list --waiting-on-me --json': out(1, '', 'aidd: .aidd/config.yaml does not parse\n') })
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ text: 'aidd: .aidd/config.yaml does not parse' })).toBeDefined()
  expect(await ui.find({ text: /Nothing needs you/ })).toBeUndefined()
  expect(await ui.find({ text: /aidd could not say what waits on you: press r to try again/ })).toBeDefined()
  await ui.unmount()
})

test('a prompt the mod fails to read goes on as typed, and the toast says aidd\'s prompt hook records a typed decision', async ($, on) => {
  const toasts: string[] = []
  mock.clock(on)
  on('session.root', () => ({ deny: 'no root' }))
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('prompt.submit', (_$, e) => ({ text: e.text }))
  const result = await $.prompt.submit(typed('land it'))
  expect(result.drop).toBeUndefined()
  expect(result.text).toBe('land it')
  expect(toasts).toEqual([
    'The aidd pane could not read this prompt, so it goes on as you typed it. aidd\'s own prompt hook still reads it, so a decision you typed is recorded there.',
  ])
})

test('a turn whose refresh check fails still ends as it would without the mod', async ($, on) => {
  on('ui.panes', () => ({ deny: 'no panes here' }))
  on('turn.complete', (_$, e) => ({ text: e.answer }))
  const result = await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' })
  expect(result.text).toBe('done')
})

test('says how to install aidd when it is not on the PATH', async ($, on) => {
  mock.clock(on)
  on('session.root', () => ({ value: ROOT }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('process.run', () => ({ deny: 'spawn aidd ENOENT' }))
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ text: NOT_FOUND })).toBeDefined()
  await ui.unmount()
})

test('closes from the Close button and from /aidd status close', async ($, on) => {
  answer(on, AIDD)
  const closed: string[] = []
  on('ui.close', (_$, e) => {
    closed.push(e.id)
    return { value: undefined }
  })
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'close' })
  await ui.unmount()
  const result = await $.command.run({ ...RUN, args: 'status close' })
  expect(result.text).toBeUndefined()
  await $.command.run({ ...RUN, args: 'close' })
  expect(closed).toEqual(['aidd-status', 'aidd-status', 'aidd-status'])
})

// `/aidd <verb>`: the front door. The skill answers a bare `/aidd` and every verb this mod does not know.
const SKILL = (on: On) => on('command.run', () => ({ text: 'the aidd skill' }))

test('reads the verb of /aidd, as the project skill or the plugin skill, and nothing else', async () => {
  expect(aiddVerb('aidd', 'Status close')).toEqual({ verb: 'status', rest: 'close' })
  expect(aiddVerb('aidd:aidd', 'approve SPEC-1 SPEC-2')).toEqual({ verb: 'approve', rest: 'SPEC-1 SPEC-2' })
  expect(aiddVerb('aidd', '   ')).toEqual({ verb: 'menu', rest: '' })
  expect(aiddVerb('aidd-team:plan', 'status')).toBeNull()
  expect(initArgs('--team')).toEqual(['--profile', 'solo', '--team'])
  expect(initArgs('--profile team --approvers @org/leads')).toEqual(['--profile', 'team', '--approvers', '@org/leads'])
  expect(repoUpdate('nothing to update: this repository already matches aidd 1.0.0\n\nThe CLI itself: `aidd self-update`.\n').isDue).toBe(false)
  expect(repoUpdate('would update .agents/skills/aidd/SKILL.md\nThe CLI itself: `aidd self-update`.\n')).toEqual({ isDue: true, lines: ['would update .agents/skills/aidd/SKILL.md'] })
})

test('a bare /aidd from the keyboard lists every decision; from elsewhere, /aidd skill, and an unknown verb go to the skill', async ($, on) => {
  const seen: string[] = []
  on('command.run', (_$, e) => {
    seen.push(e.args)
    return { text: 'the aidd skill' }
  })
  const menu = (await $.command.run({ ...RUN, args: '' })).text ?? ''
  expect(menu).toBe(AIDD_MENU)
  // Every decision, with its typed words and its verb, one line each: a person learns one thing, `/aidd`.
  for (const words of ['approve SPEC-1', 'approve merge', 'land it', 'publish', 'merge it', 'approve all', 'stop approving', 'decide PROP-1 go', 'sign off PROP-1', 'explore branch <topic>']) {
    expect(menu).toContain(`  ${words} `)
  }
  for (const verb of ['/aidd approve SPEC-1', '/aidd approve merge', '/aidd land', '/aidd publish', '/aidd merge', '/aidd approve all', '/aidd stop', '/aidd decide PROP-1 go', '/aidd sign-off PROP-1', '/aidd explore <topic>']) {
    expect(menu).toContain(verb)
  }
  expect(menu).not.toContain('that was me')
  expect((await $.command.run({ ...ELSEWHERE, args: '' })).text).toBe('the aidd skill')
  expect((await $.command.run({ ...RUN, args: 'skill' })).text).toBe('the aidd skill')
  expect(seen).toEqual(['', ''])  // `/aidd skill` reaches the skill as a bare `/aidd`
  expect((await $.command.run({ ...RUN, args: 'explain the gate' })).text).toBe('the aidd skill')
  expect((await $.command.run({ ...RUN, args: 'keep-changes' })).text).toBe('the aidd skill')  // retired: no verb here
  expect((await $.command.run({ ...RUN, args: 'help' })).text).toBe(AIDD_HELP)
  expect(AIDD_HELP).toContain('/aidd stop')
  // A command another plugin runs is never answered here.
  expect((await $.command.run({ ...RUN, args: 'help', origin: { kind: 'plugin', name: 'other' } })).text).toBe('the aidd skill')
})

// What `claude plugin update <plugin> --json` prints, as its last line.
const PLUGIN = (outcome: string) => out(0, `{"command":"update","outcome":"ok","updateOutcome":"${outcome}"}\n`)
const PLUGINS_CURRENT = {
  'claude plugin update aidd@aidd --json': PLUGIN('up_to_date'),
  'claude plugin update aidd-cli@aidd --json': PLUGIN('up_to_date'),
  'claude plugin update aidd-team@aidd --json': PLUGIN('up_to_date'),
  'claude plugin update aidd-mods@aidd --json': PLUGIN('up_to_date'),
}

test('/aidd update asks once, then updates the CLI, this repository, and the plugins', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  answer(
    on,
    {
      'aidd self-update --check': out(0, 'would update from aidd 1.0.0 (d6d3e03ac2a9) to main (06b091a81bcd) with uv: uv tool install\n'),
      'aidd upgrade': out(0, 'would update .agents/skills/aidd/SKILL.md\nwould update .github/workflows/aidd-gate.yml\n\nThe CLI itself: `aidd self-update`.\n'),
      'aidd self-update': out(0, 'updated to main (06b091a81bcd). In each repository, `aidd upgrade` lists the files to bring up to it.\n'),
      'aidd upgrade --yes': out(0, 'updated 2 files\n'),
      ...PLUGINS_CURRENT,
      'claude plugin update aidd@aidd --json': PLUGIN('updated'),
      'claude plugin update aidd-mods@aidd --json': PLUGIN('updated'),
    },
    seen,
  )
  dialog(on, 'Update', asked)
  on('ui.toast', () => ({ value: undefined }))
  const result = await $.command.run({ ...RUN, args: 'update' })
  expect(asked[0]).toMatch(/^The aidd CLI: update from aidd 1\.0\.0[\s\S]*SKILL\.md\n +would update \.github\/workflows\/aidd-gate\.yml\n\nThe Claude Code plugins: [^\n]*\n\nUpdate now\?$/)
  expect(seen.map(line => line.slice(ROOT.length + 1)).filter(line => !line.endsWith('--check') && line !== 'aidd upgrade')).toEqual([
    'aidd self-update',
    'aidd upgrade --yes',
    'claude plugin update aidd@aidd --json',
    'claude plugin update aidd-cli@aidd --json',
    'claude plugin update aidd-team@aidd --json',
    'claude plugin update aidd-mods@aidd --json',
  ])
  expect(result.text).toMatch(/^updated to main \(06b091a81bcd\)[\s\S]*commit them on a branch[\s\S]*Updated the Claude Code plugins aidd and aidd-mods: run \/reload-plugins to load them\.$/)
})

for (const label of ['Not now', '']) {
  test(`/aidd update answered ${JSON.stringify(label)} changes nothing`, async ($, on) => {
    const seen: string[] = []
    answer(on, { 'aidd self-update --check': out(0, 'would update from aidd 1.0.0 to main with uv: uv\n'), 'aidd upgrade': out(0, 'nothing to update: matches\n') }, seen)
    dialog(on, label)
    const result = await $.command.run({ ...RUN, args: 'update' })
    expect(result.text).toBe('Nothing was updated.')
    expect(seen.some(line => line.endsWith('aidd self-update') || line.endsWith('--yes') || line.includes('claude plugin'))).toBe(false)
  })
}

test('/aidd update with the CLI and this repository current still offers the plugins', async ($, on) => {
  const asked: string[] = []
  answer(on, { 'aidd self-update --check': out(0, 'aidd 1.0.0 (06b091a81bcd) is up to date: the latest is main (06b091a81bcd).\n'), 'aidd upgrade': out(0, 'nothing to update: matches\n'), ...PLUGINS_CURRENT })
  dialog(on, 'Update', asked)
  const result = await $.command.run({ ...RUN, args: 'update' })
  expect(asked[0]).toMatch(/^aidd is up to date\. aidd 1\.0\.0[^\n]*\n\nThe Claude Code plugins: [^\n]*\n\nUpdate now\?$/)
  expect(result.text).toBe('The Claude Code plugins are up to date.')
})

test('/aidd update leaves the files to a current CLI when the CLI cannot update, and names the plugin commands when claude cannot run', async ($, on) => {
  const seen: string[] = []
  answer(
    on,
    {
      'aidd self-update --check': out(0, 'would update from aidd 1.0.0 to main with uv: uv\n'),
      'aidd upgrade': out(0, 'would update .agents/skills/aidd/SKILL.md\n'),
      'aidd self-update': out(1, '', 'uv: network unreachable\n'),
      'aidd upgrade --yes': out(0, 'updated 1 file\n'),
    },
    seen,
  )
  dialog(on, 'Update')
  on('ui.toast', () => ({ value: undefined }))
  const result = await $.command.run({ ...RUN, args: 'update' })
  expect(seen.some(line => line.endsWith('aidd upgrade --yes'))).toBe(false)  // the old CLI would write its older files
  expect(result.text).toContain(`The CLI was not updated: uv: network unreachable. ${REPO_WAITS}`)
  expect(result.text).toMatch(
    /^The CLI was not updated: uv: network unreachable\. This repository's aidd files wait[\s\S]*cannot run `claude`\. In a terminal, run `claude plugin marketplace update aidd`, then `claude plugin update aidd@aidd`, `claude plugin update aidd-cli@aidd`, `claude plugin update aidd-team@aidd`, and `claude plugin update aidd-mods@aidd`\. Then run \/reload-plugins here\.$/,
  )
})

test('/aidd update with a failed CLI check never upgrades this repository, and says why in the dialog', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  answer(
    on,
    {
      'aidd self-update --check': out(2, '', 'no release of thaithienvanid/aidd is out yet\n'),
      'aidd upgrade': out(0, 'would update .agents/skills/aidd/references/security.md\n'),
      ...PLUGINS_CURRENT,
    },
    seen,
  )
  dialog(on, 'Update', asked)
  const result = await $.command.run({ ...RUN, args: 'update' })
  expect(asked[0]).toContain(`security.md\n\n${REPO_WAITS}\n\nThe Claude Code plugins:`)
  expect(seen.some(line => line.endsWith('aidd upgrade --yes') || line.endsWith('aidd self-update'))).toBe(false)
  expect(result.text).toBe(`${REPO_WAITS} The Claude Code plugins are up to date.`)
})

test('/aidd update with a CLI it cannot call current, such as a checkout, never upgrades this repository', async ($, on) => {
  const seen: string[] = []
  answer(
    on,
    {
      'aidd self-update --check': out(0, 'aidd runs from the checkout at /src/aidd, so it follows that checkout: `git pull` there updates it.\n'),
      'aidd upgrade': out(0, 'would update .agents/skills/aidd/SKILL.md\n'),
      ...PLUGINS_CURRENT,
    },
    seen,
  )
  dialog(on, 'Update')
  const result = await $.command.run({ ...RUN, args: 'update' })
  expect(seen.some(line => line.endsWith('aidd upgrade --yes'))).toBe(false)
  expect(result.text).toBe(`${REPO_WAITS} The Claude Code plugins are up to date.`)
  expect(cliUpdate('aidd 1.0.0 (06b091a81bcd) is up to date: the latest is v1.0.0 (06b091a81bcd).').isCurrent).toBe(true)
})

test('a failed self-update says the last line it printed, since the installer prints its progress first', async () => {
  const done = { isOk: false as const, error: 'Update from aidd 1.0.0 to 1.0.1 with uv: uv tool install', stderr: 'Resolved 3 packages\nerror: the wheel did not match its checksum.\n\n' }
  expect(cliUpdated(done)).toBe('The CLI was not updated: error: the wheel did not match its checksum.')
  expect(cliUpdated({ isOk: false, error: 'aidd self-update exited 1' })).toBe('The CLI was not updated: aidd self-update exited 1.')
  expect(cliUpdated({ isOk: true, value: 'updated to 1.0.1\nmore\n' })).toBe('updated to 1.0.1')
})

test('a check that failed is said in the update dialog, never read as up to date', async () => {
  const offline = cliChecked({ isOk: false, error: 'error: github.com is unreachable' })
  const current = repoChecked({ isOk: true, value: 'nothing to update: matches\n' })
  expect(checkParts(offline, current)).toEqual(['aidd could not check for a new CLI: error: github.com is unreachable', "This repository's aidd files are up to date."])
  const broken = repoChecked({ isOk: false, error: 'error: .aidd/config.yaml does not parse' })
  const latest = cliChecked({ isOk: true, value: 'aidd 1.0.0 is up to date.\n' })
  expect(checkParts(latest, broken)).toEqual(['aidd 1.0.0 is up to date.', "aidd could not check this repository's files: error: .aidd/config.yaml does not parse"])
  const due = repoChecked({ isOk: true, value: 'would update AGENTS.md\n' })
  const question = updateQuestion(offline, due)
  expect(question).toMatch(/^aidd could not check for a new CLI: error: github\.com is unreachable\n\nThis repository's aidd files \(commit them on a branch afterwards\):\n  would update AGENTS\.md\n\nThis repository's aidd files wait, [^\n]*\n\nThe Claude Code plugins: aidd, aidd-cli, aidd-team, and aidd-mods, at/)
  expect(question).not.toMatch(/up to date/)
})

test('/aidd update with a failed check says so in its dialog, and still offers the plugins', async ($, on) => {
  const asked: string[] = []
  answer(on, { 'aidd self-update --check': out(1, '', 'error: no release of aidd is out yet\n'), 'aidd upgrade': out(2, '', 'error: not an aidd repository\n'), ...PLUGINS_CURRENT })
  dialog(on, 'Update', asked)
  const result = await $.command.run({ ...RUN, args: 'update' })
  expect(asked[0]).toBe(
    "aidd could not check for a new CLI: error: no release of aidd is out yet\n\naidd could not check this repository's files: error: not an aidd repository\n\n" +
      'The Claude Code plugins: aidd, aidd-cli, aidd-team, and aidd-mods, at the newest commit of their marketplace.\n\nUpdate now?',
  )
  expect(result.text).toBe('The Claude Code plugins are up to date.')
})

test('plugin updates read as sentences: one plugin, a list joined with and, and the way by hand in order', async () => {
  expect(andList(['aidd'])).toBe('aidd')
  expect(andList(['aidd', 'aidd-mods'])).toBe('aidd and aidd-mods')
  expect(andList(['aidd', 'aidd-team', 'aidd-mods'])).toBe('aidd, aidd-team, and aidd-mods')
  expect(pluginsSaid(['aidd-mods'], ['aidd-team', 'aidd'], [])).toBe(
    'Updated the Claude Code plugin aidd-mods: run /reload-plugins to load it. The Claude Code plugins aidd-team and aidd are not installed here.',
  )
  expect(pluginsSaid([], [], [{ plugin: 'aidd@aidd', reason: 'offline' }, { plugin: 'aidd-team@aidd', reason: 'offline' }])).toBe(
    'The Claude Code plugins aidd and aidd-team were not updated: offline. In a terminal, run `claude plugin marketplace update aidd`, then ' +
      '`claude plugin update aidd@aidd` and `claude plugin update aidd-team@aidd`. Then run /reload-plugins here.',
  )
})

// What `claude plugin update <plugin> --json` prints when it fails: its JSON line on stdout, its message on stderr.
const PLUGIN_FAILED = (plugin: string, message: string, code: string) =>
  out(1, `${JSON.stringify({ command: 'update', outcome: 'failed', plugin, pluginId: plugin, message, failureCode: code })}\n`, `✘ Failed to update plugin "${plugin}": ${message}\n`)

test('reads what a plugin update said: updated, current, not installed here, or why it failed', async () => {
  expect(pluginUpdate('aidd@aidd', { isOk: true, value: 'note\n{"updateOutcome":"updated"}\n' })).toBe('updated')
  expect(pluginUpdate('aidd@aidd', { isOk: true, value: '{"updateOutcome":"up_to_date"}' })).toBe('current')
  // The JSON failureCode decides first, whatever the message says.
  const notInstalled = '{"command":"update","outcome":"failed","message":"Plugin \\"aidd-team\\" is not installed","failureCode":"not_installed"}'
  expect(pluginUpdate('aidd-team@aidd', { isOk: false, error: 'anything', stdout: notInstalled })).toBe('absent')
  expect(pluginUpdate('aidd-team@aidd', { isOk: false, error: 'x', stdout: '{"failureCode":"not_found","message":"Plugin \\"aidd-team\\" not found"}' })).toBe('absent')
  expect(pluginUpdate('aidd-team@aidd', { isOk: false, error: 'x not found', stdout: '{"failureCode":"network","message":"marketplace not found"}' })).toEqual({ failed: 'marketplace not found' })
  // Without JSON, only Claude Code's own message for this plugin is absent.
  expect(pluginUpdate('aidd-team@aidd', { isOk: false, error: '✘ Failed to update plugin "aidd-team@aidd": Plugin "aidd-team" not found' })).toBe('absent')
  expect(pluginUpdate('aidd-team@aidd', { isOk: false, error: '✘ Failed to update plugin "aidd-team@aidd": Plugin "aidd-team" is not installed' })).toBe('absent')
  expect(pluginUpdate('aidd-team@aidd', { isOk: false, error: '✘ Failed to update plugin "aidd@aidd": Plugin "aidd" not found' })).toEqual({
    failed: '✘ Failed to update plugin "aidd@aidd": Plugin "aidd" not found',
  })
  expect(pluginUpdate('aidd@aidd', { isOk: false, error: 'marketplace "aidd" not found' })).toEqual({ failed: 'marketplace "aidd" not found' })
  expect(pluginUpdate('aidd@aidd', { isOk: false, error: 'marketplace unreachable' })).toEqual({ failed: 'marketplace unreachable' })
  // An exit 0 with no update outcome is no proof of anything: it fails, never reads as up to date.
  expect(pluginUpdate('aidd@aidd', { isOk: true, value: 'Updated.\n' })).toEqual({ failed: 'claude printed no update outcome' })
  expect(pluginUpdate('aidd@aidd', { isOk: true, value: '{"command":"update","outcome":"ok"}\n' })).toEqual({ failed: 'claude printed no update outcome' })
  expect(pluginUpdate('aidd@aidd', { isOk: true, value: '' })).toEqual({ failed: 'claude printed no update outcome' })
  // Only `updated` and `up_to_date` are known: any other outcome is no proof that the plugin is current.
  expect(pluginUpdate('aidd@aidd', { isOk: true, value: '{"updateOutcome":"skipped"}\n' })).toEqual({ failed: 'claude printed an update outcome aidd does not know: skipped' })
})

test('/aidd update tries every plugin past a failure, and reports each one', async ($, on) => {
  const seen: string[] = []
  answer(
    on,
    {
      'aidd self-update --check': out(0, 'aidd 1.0.0 is up to date.\n'),
      'aidd upgrade': out(0, 'nothing to update: matches\n'),
      'claude plugin update aidd@aidd --json': out(1, '', 'marketplace unreachable\n'),
      'claude plugin update aidd-cli@aidd --json': PLUGIN('up_to_date'),
      'claude plugin update aidd-team@aidd --json': PLUGIN_FAILED('aidd-team@aidd', 'Plugin "aidd-team" is not installed', 'not_installed'),
      'claude plugin update aidd-mods@aidd --json': PLUGIN('updated'),
    },
    seen,
  )
  dialog(on, 'Update')
  const result = await $.command.run({ ...RUN, args: 'update' })
  expect(seen.filter(line => line.includes('claude plugin update')).length).toBe(4)
  expect(result.text).toBe(
    'Updated the Claude Code plugin aidd-mods: run /reload-plugins to load it. The Claude Code plugin aidd-team is not installed here. ' +
      'The Claude Code plugin aidd was not updated: marketplace unreachable. In a terminal, run `claude plugin marketplace update aidd`, then `claude plugin update aidd@aidd`. ' +
      'Then run /reload-plugins here.',
  )
})

test('/aidd update reads output with no update outcome as a failure, with the way by hand', async ($, on) => {
  answer(on, {
    'aidd self-update --check': out(0, 'aidd 1.0.0 is up to date.\n'),
    'aidd upgrade': out(0, 'nothing to update: matches\n'),
    ...PLUGINS_CURRENT,
    'claude plugin update aidd-team@aidd --json': out(0, 'Updated aidd-team.\n'),
  })
  dialog(on, 'Update')
  const result = await $.command.run({ ...RUN, args: 'update' })
  expect(result.text).toBe(
    'The Claude Code plugin aidd-team was not updated: claude printed no update outcome. In a terminal, run `claude plugin marketplace update aidd`, ' +
      'then `claude plugin update aidd-team@aidd`. Then run /reload-plugins here.',
  )
})

test('text from a file loses its control characters and bidi overrides before the pane shows it', async () => {
  // The CLI's plain() set, plus the line and paragraph separators: each run, with the spaces beside it, is one space.
  expect(clean('a\u0007b\u001b[31mc\u009bd\u202ee\u2066f\u2069g\u007f')).toBe('a b [31mc d e f g ')
  expect(clean('l\u200er\u200fa\u061cb\u2028c\u2029d')).toBe('l r a b c d')
  expect(clean('plain words, kept')).toBe('plain words, kept')
  expect(frontTitle('---\ntitle: "Pay\u202e the \u001b[2Jbill"\n---\n')).toBe('Pay the [2Jbill')
  const said = about('---\nkind: spec\n---\n## Problem\nWho \u202ehas\u0007 it.\n\n## Goals\n- One \u2067goal\u2069\n')
  expect(said.problem).toBe('Who has it.')
  expect(said.goals).toEqual(['One goal'])
})

test('every field from aidd\'s JSON is cleaned before the pane or a dialog shows it', async () => {
  const listed = steps({
    steps: [
      {
        code: 'spec.draft\u001b',
        id: 'SPEC-7',
        what: 'SPEC-7 waits\u202e',
        how: 'type\napprove',
        owner: '@me\u2028',
        labels: ['area:\u001b[2Jloop'],
        why: [{ kind: 'initiative', id: 'INIT-1', progress: '0/1\u0007' }],
        tasks: [{ id: 'SPEC-7-T1', title: 'Fix\u001b[31m it', why: 'because\u2029', assignee: 'agent\u200f', status: 'todo', role: 'developer', scope: ['src/\u0007'] }],
        files: [{ path: 'specs/SPEC-7/explore/x', kind: 'exploration', question: 'Which\u202e one?', status: 'open' }],
      },
    ],
  })[0]
  expect([listed?.code, listed?.why, listed?.taskList[0]?.why, listed?.taskList[0]?.assignee, listed?.taskList[0]?.scope]).toEqual([
    'spec.draft ',
    'INIT-1 (0/1 )',
    'because ',
    'agent ',
    ['src/ '],
  ])
  expect([listed?.what, listed?.how, listed?.owner, listed?.labels, listed?.taskList[0]?.title, listed?.files[0]?.question]).toEqual([
    'waits ',
    'type approve',
    '@me ',
    ['area: [2Jloop'],
    'Fix [31m it',
    'Which one?',
  ])
  const plan = publishPlan({ branch: 'b', head: 'c'.repeat(40), remote: 'origin', to: 'b', commits: 1, shown: ['ccccccc fix\u001b[2J\nApprove SPEC-9?'] }) ?? ''
  expect(plan.split('\n')[1]).toBe('  ccccccc fix [2J Approve SPEC-9?')
  const found = shape({ initiatives: [{ id: 'INIT-1', title: 'Fast\u202e loop', small_goals: [] }], small_goals: [{ id: 'EPIC-1', title: 'Cut\u0007 work' }] })
  expect([found.initiatives[0]?.title, found.smallGoals[0]?.title]).toEqual(['Fast loop', 'Cut work'])
})

test('/aidd init shows what init found, asks once, then runs aidd init as solo', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  answer(on, { 'aidd init --dry-run': out(0, '# What aidd found\n\n- a Python project\n'), 'aidd init --profile solo --team': out(0, 'wrote .aidd/config.yaml\nNext: run `aidd doctor`.\n') }, seen)
  dialog(on, 'Install', asked)
  const result = await $.command.run({ ...RUN, args: 'init --team' })
  expect(asked[0]).toMatch(/# What aidd found\n- a Python project\n\nRun `aidd init --profile solo --team` here\?$/)
  expect(result.text).toBe('wrote .aidd/config.yaml\nNext: run `aidd doctor`.')
})

test('a typed decision reads the same as aidd reads it: NFKC, no format characters, plain spaces', async () => {
  // The same cases as tests/test_typed_words.py, so the mod and aidd's own prompt hook agree.
  expect(plainTyped('appr\u200bove SPEC-1')).toBe('approve SPEC-1')
  expect(plainTyped('\uff41pprove \uff33\uff30\uff25\uff23\uff0d\uff11')).toBe('approve SPEC-1')
  expect(plainTyped('land\u00a0it')).toBe('land it')
  expect(plainTyped('\ufeffmerge it\u2060')).toBe('merge it')
  expect(approvalIds(plainTyped('appr\u200bove SPEC-1'))).toEqual(['SPEC-1'])
  expect(isLand(plainTyped('land\u2003it'))).toBe(true)
  expect(plainTyped('fix the login page')).toBe('fix the login page')
  expect(plainTyped('approve SPEC-\u202e12\u202c')).toBe('')
  expect(plainTyped('approve SPEC-1\u00b9')).toBe('')
  expect(plainTyped('approve SPEC-\u2460')).toBe('')
  expect(approvalIds(plainTyped('approve SPEC-\u202e12\u202c'))).toBe(null)
})

test('reads a standing approval and its end, and leaves every other prompt alone', async () => {
  expect(standingAsked('approve all')).toBe('all')
  expect(standingAsked('I approve all from now on')).toBe('all')
  expect(standingAsked('automate')).toBe('all')
  expect(standingAsked('approve all but major')).toBe('all-but-major')
  expect(standingAsked('automate, except major')).toBe('all-but-major')
  expect(standingAsked('/aidd approve all')).toBe('all')
  expect(standingAsked('approve all and publish')).toBe('all-and-publish')
  expect(standingAsked('approve all and publish, but major')).toBe('all-and-publish-but-major')
  expect(standingAsked('/aidd:aidd approve all')).toBe('all')
  expect(standingAsked('stop approving')).toBe('stop')
  expect(standingAsked('/aidd approve stop')).toBe('stop')
  expect(standingAsked('/aidd stop')).toBe('stop')
  expect(standingAsked('approve all the tests you wrote')).toBeNull()
  expect(standingAsked('automate the deploy script')).toBeNull()
})

test('a typed "approve all" records a standing approval at once; "stop approving" ends it', async ($, on) => {
  const seen: string[] = []
  const toasts: string[] = []
  const clock = answer(
    on,
    {
      'aidd approve all --show': out(0, JSON.stringify({ scope: 'all', outside_changes: [], problems: [] })),
      'aidd approve all --confirmed all --decided-via claude-code': out(0, 'Approving every Spec approval and Merge approval for you until you stop it.\n'),
      'aidd approve stop': out(0, 'Stopped approving for you: each approval waits for you again.\n'),
    },
    seen,
  )
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  expect((await $.prompt.submit(typed('approve all'))).drop).toMatch(/recording your standing approval/)
  await clock.settle()
  expect((await $.prompt.submit(typed('stop approving'))).drop).toMatch(/stopping your standing approval/)
  await clock.settle()
  expect(seen.map(line => line.slice(ROOT.length + 1))).toEqual(['aidd approve all --show', 'aidd approve all --confirmed all --decided-via claude-code', 'aidd approve stop'])
  expect(toasts).toEqual(['Approving every Spec approval and Merge approval for you until you stop it.', 'Stopped approving for you: each approval waits for you again.'])
})

test('an explore branch says so in the pane; any other branch says nothing', () => {
  expect(exploreNote({ explore_branch: 'explore/cache' })).toBe('explore/cache is an explore branch: free edits, and nothing merges from it')
  expect(exploreNote({ explore_branch: '' })).toBeNull()
  expect(exploreNote({})).toBeNull()
})

test('the pane names the product-level work and the command that opens it', () => {
  const living = [
    { kind: 'product-prototype', home: 'docs/design/app/', files: 7, opened_by: 'aidd prototype' },
    { kind: 'architecture', home: 'docs/architecture/', files: 2 },
  ]
  expect(livingNote({ living })).toBe('Product-level work: product prototype in docs/design/app/, 7 files (`aidd prototype` opens it); architecture in docs/architecture/, 2 files.')
  expect(livingNote({ living: [] })).toBeNull()
  expect(livingNote({})).toBeNull()
})

test('/aidd approve all but major from elsewhere asks first, listing what changed outside the session', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  const shown = { scope: 'all-but-major', outside_changes: [{ what: 'git config core.pager was added', restore: '`git config --unset-all core.pager`' }], problems: [] }
  const counted = 'Since your last decision, these changed outside the session and count as yours: git config core.pager was added. If one wasn\'t you, put it back with `git config --unset-all core.pager`.'
  answer(
    on,
    {
      'aidd approve all --but-major --show': out(0, JSON.stringify(shown)),
      'aidd approve all --but-major --confirmed all-but-major --decided-via claude-code': out(0, `Approving for you.\n${counted}\n`),
    },
    seen,
  )
  dialog(on, 'Approve', asked)
  const result = await $.command.run({ ...ELSEWHERE, args: 'approve all but major' })
  expect(asked[0]).toMatch(/^Let the agent record every Spec approval and Merge approval except on major changes for you, until you stop it\?/)
  expect(asked[0]).toContain('this also changed outside the agent\'s session, and counts as yours with this answer:\n    - git config core.pager was added (to put it back: `git config --unset-all core.pager`)')
  expect(result.text).toBe(`Approving for you. ${counted}`)
})

test('/aidd stop ends the standing approval at once, from the keyboard and from elsewhere alike', async ($, on) => {
  const seen: string[] = []
  answer(on, { 'aidd approve stop': out(0, 'Stopped approving for you: each approval waits for you again.\n') }, seen)
  expect((await $.command.run({ ...RUN, args: 'stop' })).text).toBe('Stopped approving for you: each approval waits for you again.')
  expect((await $.command.run({ ...ELSEWHERE, args: 'stop' })).text).toBe('Stopped approving for you: each approval waits for you again.')
  expect(seen.map(line => line.slice(ROOT.length + 1))).toEqual(['aidd approve stop', 'aidd approve stop'])
})

test('/aidd explore <topic> moves this worktree to its explore branch; from elsewhere it asks first', async ($, on) => {
  const branch = `${EXPLORE_PREFIX}caching`
  const seen: string[] = []
  const asked: string[] = []
  const said: Record<string, ProcessRunResult> = {
    [`git check-ref-format --branch ${branch}`]: out(0, `${branch}\n`),
    [`git rev-parse -q --verify refs/heads/${branch}`]: out(1, ''),
    [`git switch -c ${branch}`]: out(0, ''),
  }
  // HEAD names the explore branch once the switch ran.
  Object.defineProperty(said, 'git symbolic-ref -q --short HEAD', {
    get: () => out(0, seen.some(line => line.endsWith(`git switch -c ${branch}`)) ? `${branch}\n` : 'feat\n'),
    enumerable: true,
  })
  answer(on, said, seen)
  on('ui.panes', () => ({ value: [] }))
  dialog(on, 'Not now', asked)
  expect((await $.command.run({ ...ELSEWHERE, args: 'explore caching' })).text).toBe('Nothing changed: this worktree stays on its branch.')
  expect(asked[0]).toBe(`Move this worktree to the explore branch ${branch}? Nothing merges from it as it is, and its edits are free once you type \`explore branch caching\`, which aidd records as yours.`)
  expect(seen.some(line => line.endsWith(`git switch -c ${branch}`))).toBe(false)
  const done = (await $.command.run({ ...RUN, args: 'explore caching' })).text ?? ''
  expect(done).toMatch(new RegExp(`^This worktree is on ${branch} now`))
  expect(seen).toContain(`${ROOT} git switch -c ${branch}`)
  expect(asked).toHaveLength(1)  // the person's own keyboard is the decision
  expect(exploreAsked('branch explore/cache')).toBe('cache')
  expect(exploreAsked('a..b c')).toBeNull()
  expect((await $.command.run({ ...RUN, args: 'explore' })).text).toMatch(/^Say `\/aidd explore <topic>`/)
})

test('a dialog lists what changed outside the session before the person answers, and a recorded decision says it counts', async () => {
  const changed = [{ what: '.aidd/config.yaml changed its control keys (mode)', restore: '`git checkout -- .aidd/config.yaml`' }]
  const merge = mergePreview({ ...MERGE_SHOWN, outside_changes: changed })
  for (const question of [mergeQuestion(merge), landQuestion({ ...merge, baseBranch: 'main' })]) {
    expect(question).toContain('Since your last decision, this also changed outside the agent\'s session, and counts as yours with this answer:\n    - .aidd/config.yaml changed its control keys (mode) (to put it back: `git checkout -- .aidd/config.yaml`)')
  }
  expect(mergeQuestion(mergePreview(MERGE_SHOWN))).not.toContain('outside the agent')
  // A change that could stop the guard stays held whatever this dialog answers: it counts only because the guard
  // denies an agent's `--confirmed`, so only aidd's own MCP dialog or the person's terminal takes it in.
  const hook = [{ what: 'the git hook pre-commit was added', restore: 'remove the hook pre-commit', held: true, guard: true }]
  expect(mergeQuestion(mergePreview({ ...MERGE_SHOWN, outside_changes: hook }))).toContain(
    "- the git hook pre-commit was added (it could stop the guard, so this answer leaves it held: aidd's own dialog or your terminal takes it in)",
  )
  expect(countedLine('Approved.\nSince your last decision, these changed outside the session and count as yours: x.\n')).toBe(
    'Since your last decision, these changed outside the session and count as yours: x.',
  )
  expect(countedLine('Approved.\n')).toBe('')
})

test('/aidd approve SPEC-1, typed by the person, records at once as a typed approval does', async ($, on) => {
  const seen: string[] = []
  const toasts: string[] = []
  const clock = answer(on, APPROVING, seen)
  dialog(on, 'Approve')
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: [] }))
  const result = await $.command.run({ ...RUN, args: 'approve SPEC-1' })
  expect(result.text).toBeUndefined()
  await clock.settle()
  expect(seen.filter(line => line.includes('--confirmed'))).toEqual([`${ROOT} aidd approve spec SPEC-1 --ref spec/SPEC-1 --confirmed 2db4dfb562091efd455f64b899112210bb7b116e`])
  expect(toasts).toEqual(['Approved SPEC-1 at 2db4dfb56209.'])
})

test('an item that others wait on says how many it frees, through the chain', async () => {
  const chain = steps({
    steps: [
      { code: 'spec.spec_approval', id: 'SPEC-1', what: 'a', who: 'Approver' },
      { code: 'spec.blocked_by', id: 'SPEC-2', what: 'b', who: 'author', waiting_on: ['SPEC-1'], blocked: true },
      { code: 'spec.blocked_by', id: 'SPEC-3', what: 'c', who: 'author', waiting_on: ['SPEC-2'], blocked: true },
      { code: 'spec.blocked_by', id: 'SPEC-10', what: 'd', who: 'author', waiting_on: ['SPEC-3', 'SPEC-2'], blocked: true },
    ],
  })
  const frees = unblocks(chain)
  expect(frees.get('SPEC-1')).toEqual(['SPEC-2', 'SPEC-3', 'SPEC-10'])
  expect(frees.get('SPEC-3')).toEqual(['SPEC-10'])
  expect(frees.get('SPEC-10')).toBeUndefined()
})

test('the pane says when a standing approval is on, and how to end it', async ($, on) => {
  const standing = { scope: 'all-but-major', since: '2026-10-16T16:52:00+07:00', by: 'email:me@example.com' }
  answer(on, { ...AIDD, 'aidd list --branch --json': out(0, JSON.stringify({ ...BRANCH, standing })) })
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(
    await ui.find({ text: 'Standing approval is on, so aidd records your approvals. To end it: `/aidd stop`, or type `stop approving`. It covers all but major, since 2026-10-16 16:52.' }),
  ).toBeDefined()
  await ui.unmount()
  expect(standingNote(BRANCH)).toBeNull()
  expect(standingNote({ standing: { ...standing, scope: 'all-and-publish' } })).toMatch(/It covers all and publishing, since/)
})

test('an empty branch says what to do next', async ($, on) => {
  answer(on, { ...AIDD, 'aidd list --branch --json': out(0, JSON.stringify(WAITING)) })
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ text: 'Nothing is open on this branch, and nothing waits on you.' })).toBeDefined()
  expect(await ui.find({ text: '/aidd-team:autopilot "what you want"' })).toBeDefined()
  await ui.unmount()
})

test('rows line up in one grid, and the pane follows its width and its placement', async ($, on) => {
  answer(on, AIDD)
  await $.command.run(RUN)
  const at = (bodyColumns: number, placement: 'dock' | 'inline') =>
    $.ui.mount({ ...PANE, surface: 'terminal', props: { ...PANE.props, bodyColumns, placement } })
  const rowsOf = async (ui: Awaited<ReturnType<typeof at>>) =>
    Promise.all(['row-SPEC-1', 'row-SPEC-2', 'row-SPEC-3'].map(async key => (await ui.find({ key }))?.text ?? ''))

  const wide = await at(100, 'dock')
  const lines = await rowsOf(wide)
  // Every row is padded to the same grid, so each column starts at the same cell.
  expect(new Set(lines.map(line => line.length)).size).toBe(1)
  const [first = '', second = '', third = ''] = lines
  expect(first.indexOf('1 wait on it')).toBe(second.indexOf('waits on SPEC-1'))
  expect(first.lastIndexOf('high')).toBe(third.lastIndexOf('low'))
  expect(lines[1]).toMatch(/waits on SPEC-1 +EPIC-2 +high/)
  expect(heightOf(await wide.drawn())).toBe(40)
  await wide.unmount()

  const narrow = await at(46, 'dock')
  expect(await narrow.find({ text: /waits on SPEC-1/ })).toBeDefined()
  expect((await rowsOf(narrow))[1]).not.toMatch(/high/)
  await narrow.unmount()

  const tight = await at(38, 'inline')
  expect((await rowsOf(tight))[1]).not.toMatch(/waits on/)
  expect(await tight.find({ text: '↑↓ · Enter · a · r · x · ctrl+x tab' })).toBeDefined()
  // Inline above the prompt, the pane fits its content instead of taking the whole room.
  expect(heightOf(await tight.drawn())).toBeUndefined()
  await tight.unmount()
})

test('the next decision leads, then each small goal on its ladder; choosing one shows only its work', async ($, on) => {
  const mine = { schema_version: '1', steps: [{ code: 'spec.spec_approval', id: 'SPEC-1', where: 'specs/SPEC-1.md', what: 'waits', who: '@me', how: 'approve' }] }
  answer(on, { ...AIDD, 'aidd list --waiting-on-me --json': out(0, JSON.stringify(mine)) })
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  // Only the choice ahead, with what to type.
  const band = (await ui.find({ key: 'band' }))?.text ?? ''
  expect(band).toMatch(/◆ D2 Spec approval {2}SPEC-1 {2}Local gate runs keep their events in the git directory/)
  expect(band).toMatch(/type {2}approve SPEC-1/)
  const rung = async (id: string) => (await ui.find({ key: `ladder-${id}` }))?.text ?? ''
  expect(await rung('INIT-1')).toMatch(/INIT-1 +A faster loop +0\/2 small goals done/)
  // plan ✓ · specs ◆ 1/2 (SPEC-1 waits on you) · release 0/2 still ahead · no launch: it is incremental.
  expect(await rung('EPIC-1')).toMatch(/^ {4}EPIC-1 +Cut repeated work +incremental +✓ +◆ 1\/2 +· +—/)
  expect((await ui.find({ key: 'ladder' }))?.text).toMatch(/D1 plan +D2 specs +D3 release +D4 launch/)
  // A flagged small goal: built and released behind its flag, and its launch waits on you.
  expect(await rung('EPIC-2')).toMatch(/EPIC-2 +Shorten the wait +flagged +✓ +✓ +✓ +◆/)
  // The trunk-based flow, pinned: a branch past its limit says what to do.
  expect(await ui.find({ text: /plan\/loop-efficiency is 3 days old, past limits.max_branch_age_days = 2/ })).toBeDefined()

  await ui.press({ key: 'ladder-EPIC-2' })
  expect(await ui.find({ key: 'row-SPEC-2' })).toBeDefined()
  expect(await ui.find({ key: 'row-SPEC-1' })).toBeUndefined()
  expect(await ui.find({ key: 'row-SPEC-3' })).toBeUndefined()
  expect(await ui.find({ text: /All \(showing EPIC-2\)/ })).toBeDefined()
  await ui.press({ key: 'all' })
  expect(await ui.find({ key: 'row-SPEC-1' })).toBeDefined()
  expect(await ui.find({ key: 'all' })).toBeUndefined()
  await ui.unmount()
})

test('with nothing waiting, the band says so; an old aidd with no goal list still draws the rest', async ($, on) => {
  answer(on, { ...AIDD, 'aidd list --waiting-on-me --json': out(0, JSON.stringify({ schema_version: '1', steps: [] })), 'aidd goal list --json': out(2, '', 'aidd: invalid choice: \'goal\'\n') })
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ text: '✓ Nothing needs you' })).toBeDefined()
  expect(await ui.find({ text: /Shape of work: aidd: invalid choice/ })).toBeDefined()
  expect(await ui.find({ key: 'row-SPEC-1' })).toBeDefined()
  await ui.unmount()
})

test('a Spec file gives the first paragraph of Problem and its Goals', async () => {
  const said = about(FILES[`${ROOT}/specs/SPEC-1.md`] ?? '')
  expect(said.problem).toBe('The maintainer cannot see where a change spends its time. `aidd metrics` needs an event file, and this repository has none.')
  expect(said.goals).toEqual(['A local `aidd gate` appends its event.', '`aidd metrics` reads that file.'])
  // A stub says nothing yet: TODO lines and empty sections give no text.
  expect(about('---\nhypothesis: "TODO: metric"\n---\n## Problem\nTODO: who has it\n## Goals\n- TODO\n')).toEqual({ kind: 'spec', for: '', problem: '', goals: [] })
})

test('the detail card says what the Spec is about, then where it stands, then its Tasks', async ($, on) => {
  answer(on, AIDD)
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ text: 'The maintainer cannot see where a change spends its time. `aidd metrics` needs an event file, and this repository has none.' })).toBeDefined()
  expect(await ui.find({ text: '• A local `aidd gate` appends its event.\n• `aidd metrics` reads that file.' })).toBeDefined()
  // Problem and Goals only: no measure, no Acceptance, nothing past the first paragraph.
  expect(await ui.find({ text: /second paragraph|Long text the pane never shows|placeholder goal|0 percent|scenario/ })).toBeUndefined()
  // Three parts, each under its own heading, in this order.
  const card = (await ui.find({ key: 'details' }))?.text ?? ''
  const at = (part: string) => card.indexOf(part)
  expect([at('About'), at('Status'), at('Tasks · 2 tasks: 1 blocked, 1 todo')].every(n => n >= 0)).toBe(true)
  expect(at('About') < at('Problem') && at('Goals') < at('Status') && at('Status') < at('Now') && at('Part of') < at('Tasks · ')).toBe(true)
  await ui.unmount()
})

test("a work item's folder: the open explorations first, then its docs, and the folder the CLI's own paths name", async () => {
  const files = itemFiles(BRANCH.steps[0]?.files)
  expect(files.map(file => [file.kind, file.status])).toEqual([
    ['exploration', 'open'],
    ['tech-spec', ''],
    ['exploration', 'decided'],
  ])
  expect(itemFiles([{ kind: 'more', count: 3 }, { path: '', kind: 'doc' }, 'junk'])).toEqual([{ path: '', kind: 'more', question: '', status: '', count: 3 }])
  // The pane never assumes `specs/`: a repository with `specs_dir: work` keeps its items, and their folders, there.
  expect(specsFolder(steps({ steps: [{ code: 'spec.draft', id: 'SPEC-9', where: 'work/SPEC-9.md', what: 'x', who: 'agent' }] }))).toBe('work')
  expect(specsFolder([])).toBe('specs')
})

test("the detail card lists the item's folder, and an open exploration says a person picks", async ($, on) => {
  answer(on, AIDD)
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const card = (await ui.find({ key: 'details' }))?.text ?? ''
  expect(card).toContain('Files · specs/SPEC-1/')
  expect(card).toContain('explore/retention/')
  expect(card).toContain('open: a person picks')
  expect(card).toContain('How long are events kept?')
  expect(card).toContain('tech-spec-local-events.md')
  expect(card.indexOf('Tasks · ') < card.indexOf('Files · ')).toBe(true)
  await ui.unmount()
})

test('a Task opens from its Spec, says why, who, and what it may change, and goes back', async ($, on) => {
  answer(on, AIDD)
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ key: 'task-SPEC-1-T1' }))?.text).toMatch(/SPEC-1-T1 +Write the event on a local gate run +blocked +developer/)
  expect((await ui.find({ key: 'task-SPEC-1-T2' }))?.text).toMatch(/SPEC-1-T2 +Read it in aidd metrics +todo +developer/)

  await ui.press({ key: 'task-SPEC-1-T1' })
  expect(await ui.find({ text: 'the Spec waits for Spec approval; no Task starts before it' })).toBeDefined()
  expect(await ui.find({ text: 'src/aidd/gate/\ntests/test_gate_events.py' })).toBeDefined()
  expect(await ui.find({ text: /blocked · agent:developer · in SPEC-1/ })).toBeDefined()
  expect(await ui.find({ key: 'back' })).toBeDefined()
  expect(await ui.find({ text: /b back/ })).toBeDefined()
  expect(await ui.find({ text: /The maintainer cannot see/ })).toBeUndefined()

  await ui.press({ key: 'back' })
  expect(await ui.find({ text: /The maintainer cannot see/ })).toBeDefined()

  await ui.press({ key: 'task-SPEC-1-T2' })
  expect(await ui.find({ text: 'SPEC-1-T1' })).toBeDefined() // what it waits on
  await ui.press({ key: 'row-SPEC-2' }) // choosing another item closes the Task
  expect(await ui.find({ key: 'back' })).toBeUndefined()
  await ui.unmount()
})

const WITH_PROPOSAL = {
  schema_version: '1',
  steps: [
    {
      code: 'proposal.qualifying',
      id: 'PROP-1',
      where: 'proposals/PROP-1/proposal.md',
      what: 'PROP-1 waits for a go/no-go decision',
      who: 'decision maker',
      how: 'read the needs and questions, then record `go_no_go` in proposals/PROP-1/proposal.md',
      status: 'qualifying',
    },
    {
      code: 'spec.draft',
      id: 'SPEC-20',
      where: 'specs/SPEC-20.md',
      what: 'SPEC-20 needs its Spec and tests finished',
      who: 'agent',
      how: '/aidd-team:specify',
      why: [{ kind: 'initiative', id: 'INIT-2', progress: '0/1' }],
    },
  ],
}

test('a Proposal has its own heading, says who it is for, its need and goal, and leads the Shape of work', async ($, on) => {
  answer(on, { ...AIDD, 'aidd list --branch --json': out(0, JSON.stringify(WITH_PROPOSAL)) })
  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ text: /^Proposal: needs a go\/no-go$/ })).toBeDefined()
  expect((await ui.find({ key: 'row-PROP-1' }))?.text).toMatch(/PROP-1 +Rebuild the booking app/)
  // The detail card reads as a Proposal: For, Need, Goal; the goal without its comment.
  expect(await ui.find({ text: 'client · Clinic board' })).toBeDefined()
  expect(await ui.find({ text: 'Booking takes a phone call today, and the clinic misses calls at lunch.' })).toBeDefined()
  expect(await ui.find({ text: 'Patients book a visit in under a minute' })).toBeDefined()
  expect(await ui.find({ text: /^Problem$|Not shown|A short pitch/ })).toBeUndefined()
  // The Shape of work: the Proposal first, with its stage.
  const ladder = (await ui.find({ key: 'ladder' }))?.text ?? ''
  expect(ladder.indexOf('PROP-1')).toBeLessThan(ladder.indexOf('INIT-1'))
  expect((await ui.find({ key: 'ladder-PROP-1' }))?.text).toMatch(/PROP-1 +Rebuild the booking app +proposal, qualifying/)
  // Focus on the Proposal shows it alone.
  await ui.press({ key: 'ladder-PROP-1' })
  expect(await ui.find({ key: 'row-PROP-1' })).toBeDefined()
  expect(await ui.find({ key: 'row-SPEC-20' })).toBeUndefined()
  await ui.unmount()
})

// Approving from the prompt: what the person types, the dialog, and the one write it makes.
const APPROVAL_WAITS = {
  schema_version: '1',
  steps: [{ code: 'spec.spec_approval', id: 'SPEC-1', where: 'specs/SPEC-1.md', what: 'waits', who: '@me', how: 'approve', branch: 'spec/SPEC-1' }],
}
const SHOWN = {
  id: 'SPEC-1',
  title: 'Local gate runs keep their events',
  spec: 'specs/SPEC-1.md',
  acceptance: ['A1', 'A2', 'A3'],
  commit: '2db4dfb562091efd455f64b899112210bb7b116e',
  ref: 'spec/SPEC-1',
  risk: 'route major; touches security; rollback: revert the change',
  warnings: [],
  problems: [],
}
test('the merge and land questions show every gate warning, so a second one never hides', async () => {
  const warnings = ['the change touches a frozen file', 'the Spec has no rollback']
  const merge = mergePreview({ ...MERGE_SHOWN, warnings })
  for (const question of [mergeQuestion(merge), landQuestion({ ...merge, baseBranch: 'main' })]) {
    expect(question).toContain(`! ${warnings[0]}`)
    expect(question).toContain(`! ${warnings[1]}`)
  }
})

test('a revised Spec says why it was reopened in the approval question', async () => {
  const revised = 'the limit was per user, not per card (reopened 2026-10-17; it was approved as 0123456789ab)'
  expect(approvalQuestion([preview({ ...SHOWN, revised })])).toContain(`Revised: ${revised}`)
  expect(approvalQuestion([preview(SHOWN)])).not.toContain('Revised:')
})

test('the approval question shows every warning, so a changed test never hides a late approval', async () => {
  const warnings = ['1 test change since its last approval at 0123456789ab: tests/test_cart.py. Read the diff before you approve.', 'the commit already holds implementation (src/cart.py)']
  const asked = approvalQuestion([preview({ ...SHOWN, warnings })])
  expect(asked).toContain(`! ${warnings[0]}`)
  expect(asked).toContain(`! ${warnings[1]}`)
})

const APPROVING = {
  'aidd list --waiting-on-me --json': out(0, JSON.stringify(APPROVAL_WAITS)),
  'aidd approve spec SPEC-1 --ref spec/SPEC-1 --show': out(0, JSON.stringify(SHOWN)),
  'aidd approve spec SPEC-1 --ref spec/SPEC-1 --confirmed 2db4dfb562091efd455f64b899112210bb7b116e': out(0, 'Approved SPEC-1.\n'),
}
const typed = (text: string, origin: { kind: 'composer' } | { kind: 'plugin'; name: string; asUser: true } = { kind: 'composer' }) => ({ text, origin, wait: false })

// The person's answer in Claude Code's own dialog, which `$.ui.ask` opens as an AskUserQuestion call; `asked` gets the question.
function dialog(on: On, label: string, asked: string[] = []) {
  on('tool.call', { tool: 'AskUserQuestion' }, (_$, e) => {
    const question = e.tool === 'AskUserQuestion' ? (e.questions[0]?.question ?? '') : ''
    asked.push(question)
    return { result: { questions: e.tool === 'AskUserQuestion' ? e.questions : [], answers: { [question]: label } } }
  })
}

test('reads which Specs a typed prompt approves, and leaves every other prompt alone', async () => {
  expect(approvalIds('approve SPEC-1')).toEqual(['SPEC-1'])
  expect(approvalIds('I approve spec-1 and SPEC-4, please')).toEqual(['SPEC-1', 'SPEC-4'])
  expect(approvalIds('approved')).toEqual([])
  expect(approvalIds('  approve all ')).toBeNull()  // a standing approval (standingAsked), not what waits now
  expect(approvalIds('approve the design of the button')).toBeNull()
  expect(approvalIds('please approve SPEC-1')).toBeNull()
  expect(approvalIds('approvers for SPEC-1?')).toBeNull()
  expect(approvalIds('fix the bug')).toBeNull()
  expect(approvalIds('approve the merge')).toBe('merge')
  expect(approvalIds('I approve merging')).toBe('merge')
  expect(approvalIds('approve merge of SPEC-1')).toBeNull()  // which one is unclear: an ordinary prompt
})

const MERGE_SHOWN = {
  branch: 'discount',
  head: 'c'.repeat(40),
  base: 'b'.repeat(40),
  spec: 'specs/SPEC-1.md',
  changed: '2 files changed, 9 insertions(+)',
  decision: 'pending',
  failing: [],
  pending: [],
  warnings: [],
  problems: [],
}

// A request that did not come from the person's keyboard: the SDK, or the agent through the aidd skill.
const ELSEWHERE = { ...RUN, origin: { kind: 'sdk' as const } }

test('a typed "approve the merge" records exactly the head at once, asking nothing', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  const toasts: string[] = []
  const clock = answer(
    on,
    {
      'aidd approve merge --show': out(0, JSON.stringify(MERGE_SHOWN)),
      [`aidd approve merge --confirmed ${'c'.repeat(40)}`]: out(0, 'Approved merging discount.\n'),
    },
    seen,
  )
  dialog(on, 'Approve', asked)
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: [] }))
  const result = await $.prompt.submit(typed('approve the merge'))
  expect(result.drop).toMatch(/approving the merge of this branch/)
  await clock.settle()
  expect(asked).toEqual([])
  expect(seen.filter(line => line.includes('--confirmed'))).toEqual([`${ROOT} aidd approve merge --confirmed ${'c'.repeat(40)}`])
  expect(toasts).toEqual([`Approved merging discount at ${'c'.repeat(12)}.`])
})

test('/aidd approve merge from elsewhere asks with the head, then records exactly that head', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  const toasts: string[] = []
  const clock = answer(
    on,
    {
      'aidd approve merge --show': out(0, JSON.stringify(MERGE_SHOWN)),
      [`aidd approve merge --confirmed ${'c'.repeat(40)}`]: out(0, 'Approved merging discount.\n'),
    },
    seen,
  )
  dialog(on, 'Approve', asked)
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: [] }))
  await $.command.run({ ...ELSEWHERE, args: 'approve merge' })
  await clock.settle()
  expect(asked[0]).toMatch(/discount at c{12} \(specs\/SPEC-1\.md\)\n +2 files changed, 9 insertions\(\+\) · besides your approval the gate waits on nothing else/)
  expect(asked[0]).toMatch(/Approve merging discount\?$/)
  expect(seen.filter(line => line.includes('--confirmed'))).toEqual([`${ROOT} aidd approve merge --confirmed ${'c'.repeat(40)}`])
  expect(toasts).toEqual([`Approved merging discount at ${'c'.repeat(12)}.`])
})

test('a typed "merge it" where a platform merges approves the head with auto-merge, and never lands locally', async ($, on) => {
  const seen: string[] = []
  const toasts: string[] = []
  const clock = answer(
    on,
    {
      'aidd land --show': out(0, JSON.stringify({ ...MERGE_SHOWN, base_branch: 'main', squash: false, merges_on_platform: true, problems: ['merges there'] })),
      'aidd approve merge --show': out(0, JSON.stringify(MERGE_SHOWN)),
      [`aidd approve merge --confirmed ${'c'.repeat(40)} --auto-merge`]: out(0, 'Approved merging discount.\nAuto-merge is on: the pull request merges by itself once `aidd/gate` passes.\n'),
    },
    seen,
  )
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: [] }))
  expect(isMergeIt('merge it')).toBe(true)
  expect(isMergeIt('merge the PR')).toBe(true)
  expect(isMergeIt('merge the two branches')).toBe(false)
  const result = await $.prompt.submit(typed('merge it'))
  expect(result.drop).toMatch(/approving the merge of this branch's pull request/)
  await clock.settle()
  expect(seen.filter(line => line.includes('--confirmed'))).toEqual([`${ROOT} aidd approve merge --confirmed ${'c'.repeat(40)} --auto-merge`])
  expect(seen.some(line => line.includes('aidd land --confirmed'))).toBe(false)
  expect(toasts.at(-1)).toMatch(/^Approved merging discount at c{12}\. Auto-merge is on/)
})

test('"merge it" before the branch is on a platform records nothing and names land it and publish', async ($, on) => {
  const seen: string[] = []
  const toasts: string[] = []
  const clock = answer(on, { 'aidd land --show': out(0, JSON.stringify({ ...MERGE_SHOWN, base_branch: 'main', squash: false })) }, seen)
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  await $.prompt.submit(typed('merge it'))
  await clock.settle()
  expect(seen.some(line => line.includes('--confirmed'))).toBe(false)
  expect(toasts.at(-1)).toBe(NOT_ON_A_PLATFORM)
})

test('a typed "land it" lands exactly the head at once; from elsewhere it asks where it lands first', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  const toasts: string[] = []
  const clock = answer(
    on,
    {
      'aidd land --show': out(0, JSON.stringify({ ...MERGE_SHOWN, base_branch: 'main', squash: false })),
      [`aidd land --confirmed ${'c'.repeat(40)}`]: out(0, 'landed discount\n'),
    },
    seen,
  )
  dialog(on, 'Approve', asked)
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: [] }))
  expect(isLand('land it')).toBe(true)
  expect(isLand('land the plane softly')).toBe(false)
  const result = await $.prompt.submit(typed('land it'))
  expect(result.drop).toMatch(/landing this branch/)
  await clock.settle()
  expect(asked).toEqual([])
  expect(seen.filter(line => line.includes('--confirmed'))).toEqual([`${ROOT} aidd land --confirmed ${'c'.repeat(40)}`])
  expect(toasts.at(-1)).toBe('Landed discount on main.')
  await $.command.run({ ...ELSEWHERE, args: 'land' })
  await clock.settle()
  expect(asked[0]).toMatch(/discount at c{12} on main[\s\S]*The tests run again first[\s\S]*Land discount on main\?$/)
})

test('a change that weakens the guard is asked about even from the keyboard, and the answer names what the dialog showed', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  const digest = 'e'.repeat(64)
  const held = [{ what: '.aidd/config.yaml changed its control keys (mode)', restore: '`git checkout -- .aidd/config.yaml`', held: true }]
  const clock = answer(
    on,
    {
      'aidd land --show': out(0, JSON.stringify({ ...MERGE_SHOWN, base_branch: 'main', squash: false, outside_changes: held, outside_hash: digest })),
      [`aidd land --confirmed ${'c'.repeat(40)} --outside-hash ${digest}`]: out(0, 'landed discount\n'),
    },
    seen,
  )
  dialog(on, 'Approve', asked)
  on('ui.toast', () => ({ value: undefined }))
  on('ui.panes', () => ({ value: [] }))
  await $.prompt.submit(typed('land it'))
  await clock.settle()
  expect(asked[0]).toContain('- .aidd/config.yaml changed its control keys (mode) (it weakens the guard) (to put it back: `git checkout -- .aidd/config.yaml`)')
  expect(seen.filter(line => line.includes('--confirmed'))).toEqual([`${ROOT} aidd land --confirmed ${'c'.repeat(40)} --outside-hash ${digest}`])
})

test('"land it" on a branch its platform merges records nothing and names merge it', async ($, on) => {
  const seen: string[] = []
  const toasts: string[] = []
  const clock = answer(on, { 'aidd land --show': out(0, JSON.stringify({ ...MERGE_SHOWN, base_branch: 'main', squash: false, merges_on_platform: true, problems: ['merges there'] })) }, seen)
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  await $.prompt.submit(typed('land it'))
  await clock.settle()
  expect(seen.some(line => line.includes('--confirmed'))).toBe(false)
  expect(toasts.at(-1)).toBe(ON_A_PLATFORM)
})


test('the retired "ship it" records nothing and names the three words', async ($, on) => {
  const seen: string[] = []
  answer(on, {}, seen)
  expect(isRetiredShip('ship it')).toBe(true)
  expect(isRetiredShip('ship the release notes to the client')).toBe(false)
  const result = await $.prompt.submit(typed('ship it'))
  expect(result.drop).toBe(`aidd: ${SHIP_RETIRED} This prompt does not go to the model.`)
  expect((await $.command.run({ ...RUN, args: 'ship' })).text).toBe(SHIP_RETIRED)
  expect(seen).toEqual([])
})

test('a typed "publish" goes on to aidd\'s own prompt hook; /aidd publish only shows what would leave', async ($, on) => {
  const seen: string[] = []
  const clock = answer(
    on,
    {
      'aidd publish --show': out(
        0,
        JSON.stringify({ branch: 'discount', head: 'c'.repeat(40), remote: 'origin', to: 'discount', base: 'main', commits: 2, shown: ['ccccccc fix', 'ddddddd feat'], pull_request: true }),
      ),
    },
    seen,
  )
  expect(isPublish('publish')).toBe(true)
  expect(isPublish('push it')).toBe(true)
  expect(isPublish('open a PR')).toBe(true)
  expect(isPublish('push back on the design')).toBe(false)
  on('prompt.submit', (_$, e) => ({ text: e.text }))
  const result = await $.prompt.submit(typed('publish'))
  expect(result.drop).toBeUndefined()  // aidd's prompt hook records it; the agent runs `aidd publish`
  expect(result.text).toBe('publish')
  const said = (await $.command.run({ ...RUN, args: 'publish' })).text ?? ''
  await clock.settle()
  expect(said).toMatch(/^Would leave this machine: discount at c{12} to origin\/discount, then a pull request into main \(2 commits the remote lacks\)/)
  expect(said).toMatch(/type `publish` at the prompt/)
  expect(seen.every(line => !line.includes('aidd publish --') || line.endsWith('aidd publish --show'))).toBe(true)
})

test('a merge the gate fails for anything else is not asked about', async ($, on) => {
  const seen: string[] = []
  const toasts: string[] = []
  const clock = answer(on, { 'aidd approve merge --show': out(0, JSON.stringify({ ...MERGE_SHOWN, problems: ['the gate fails on tests; fix that first'] })) }, seen)
  dialog(on, 'Approve')
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  await $.prompt.submit(typed('approve merge'))
  await clock.settle()
  expect(seen.some(line => line.includes('--confirmed'))).toBe(false)
  expect(toasts[0]).toMatch(/the gate fails on tests/)
})

test('a typed "approve SPEC-1" records exactly the commit shown at once, and says which commit', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  const toasts: string[] = []
  const clock = answer(on, APPROVING, seen)
  dialog(on, 'Approve', asked)
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: [] }))
  const result = await $.prompt.submit(typed('approve SPEC-1'))
  expect(result.drop).toMatch(/approving SPEC-1.*does not go to the model/)
  await clock.settle()
  expect(asked).toEqual([])
  expect(seen.filter(line => line.includes('--confirmed'))).toEqual([`${ROOT} aidd approve spec SPEC-1 --ref spec/SPEC-1 --confirmed ${SHOWN.commit}`])
  expect(toasts).toEqual(['Approved SPEC-1 at 2db4dfb56209.'])
})

test('/aidd approve SPEC-1 from elsewhere asks in the dialog, then records exactly the commit shown', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  const toasts: string[] = []
  const clock = answer(on, APPROVING, seen)
  dialog(on, 'Approve', asked)
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: [] }))
  await $.command.run({ ...ELSEWHERE, args: 'approve SPEC-1' })
  await clock.settle()
  expect(asked[0]).toMatch(/SPEC-1 Local gate runs keep their events\n +3 acceptance items · commit 2db4dfb56209\n/)
  expect(asked[0]).toMatch(/Approve SPEC-1\?$/)
  expect(asked[0]).toMatch(/\n +Risk: route major; touches security; rollback: revert the change/)
  expect(seen.filter(line => line.includes('--confirmed'))).toEqual([`${ROOT} aidd approve spec SPEC-1 --ref spec/SPEC-1 --confirmed ${SHOWN.commit}`])
  expect(toasts).toEqual(['Approved SPEC-1.'])
})

test('a re-approval shows what changed since the last approval, line by line', async ($, on) => {
  const asked: string[] = []
  const changed = {
    ...SHOWN,
    since: {
      commit: 'e'.repeat(40),
      files: [{ path: 'specs/SPEC-1.md', added: '1', removed: '1' }],
      lines: ['-- A1: the total drops by 10%', '+- A1: the total drops by 15%'],
      more: 0,
    },
  }
  const clock = answer(on, { ...APPROVING, 'aidd approve spec SPEC-1 --ref spec/SPEC-1 --show': out(0, JSON.stringify(changed)) })
  dialog(on, 'Not now', asked)
  on('ui.toast', () => ({ value: undefined }))
  await $.command.run({ ...ELSEWHERE, args: 'approve SPEC-1' })
  await clock.settle()
  expect(asked[0]).toMatch(/Changed since your last approval \(e{12}\):\n +specs\/SPEC-1\.md  \+1 -1\n +-- A1: the total drops by 10%\n +\+- A1: the total drops by 15%/)
})

// Only the exact Approve records: not now, free text under Other, or a dialog with no answer record nothing.
for (const label of ['Not now', 'yes approve it', '']) {
  test(`the answer ${JSON.stringify(label)} records nothing`, async ($, on) => {
    const seen: string[] = []
    const clock = answer(on, APPROVING, seen)
    dialog(on, label)
    on('ui.toast', () => ({ value: undefined }))
    await $.command.run({ ...ELSEWHERE, args: 'approve' })
    await clock.settle()
    expect(seen.some(line => line.includes('--confirmed'))).toBe(false)
    expect(seen.some(line => line.includes('--show'))).toBe(true)
  })
}

test('a prompt the person did not type, or one that approves nothing waiting, goes to the model as it is', async ($, on) => {
  const seen: string[] = []
  answer(on, { 'aidd list --waiting-on-me --json': out(0, JSON.stringify(WAITING)) }, seen)
  on('prompt.submit', (_$, e) => ({ text: e.text }))
  const fromPlugin = await $.prompt.submit(typed('approve SPEC-1', { kind: 'plugin', name: 'other', asUser: true }))
  expect(fromPlugin.drop).toBeUndefined()
  expect(seen).toEqual([])
  const bare = await $.prompt.submit(typed('approve'))  // nothing waits on you: an ordinary prompt
  expect(bare.drop).toBeUndefined()
  expect(bare.text).toBe('approve')
})

test('/aidd decide and /aidd sign-off read what aidd shows, then record exactly it', async ($, on) => {
  expect(proposalAsked('decide', 'PROP-1 go because it fits')).toEqual({ verb: 'decide', id: 'PROP-1', decision: 'go', reason: 'it fits' })
  expect(proposalAsked('sign-off', 'prop-2')).toEqual({ verb: 'sign-off', id: 'PROP-2', decision: null, reason: '' })
  expect(proposalAsked('decide', 'PROP-1 maybe')).toBeNull()
  expect(proposalAsked('sign-off', 'PROP-1 go')).toBeNull()
  expect(proposalAsked('decide', '--confirmed go')).toBeNull()
  const seen: string[] = []
  const h = 'a'.repeat(32)
  const shown = (extra: object) => out(0, `${JSON.stringify({ id: 'PROP-1', title: 'Move billing', by: '@ana', hash: h, problems: [], ...extra })}\n`)
  const verb = (v: string) => ['aidd', 'proposal', v].join(' ')
  answer(
    on,
    {
      [`${verb('decide')} --show --reason=it fits -- PROP-1 go`]: shown({ decision: 'go' }),
      [`${verb('decide')} --reason=it fits --confirmed go --decided-via claude-code -- PROP-1 go`]: out(
        0,
        'Proposal PROP-1\nRecorded go_no_go in proposals/PROP-1/proposal.md. Commit it: git commit ...\n',
      ),
      [`${verb('sign-off')} --show -- PROP-1`]: shown({}),
      [`${verb('sign-off')} --confirmed ${h} --decided-via claude-code -- PROP-1`]: out(0, 'Recorded sign_off in proposals/PROP-1/proposal.md.\n'),
    },
    seen,
  )
  expect((await $.command.run({ ...RUN, args: 'decide PROP-1 go because it fits' })).text).toMatch(/^Recorded go_no_go/)
  expect((await $.command.run({ ...RUN, args: 'sign-off PROP-1' })).text).toMatch(/^Recorded sign_off/)
})

test('/aidd sign-off from elsewhere asks first, and a problem records nothing', async ($, on) => {
  const seen: string[] = []
  const asked: string[] = []
  const verb = ['aidd', 'proposal', 'sign-off'].join(' ')
  answer(
    on,
    {
      [`${verb} --show -- PROP-1`]: out(0, '{"id": "PROP-1", "hash": "h", "problems": []}\n'),
      [`${verb} --show -- PROP-2`]: out(0, '{"id": "PROP-2", "hash": "h", "problems": ["PROP-2 has no go yet"]}\n'),
    },
    seen,
  )
  dialog(on, 'Not now', asked)
  expect((await $.command.run({ ...ELSEWHERE, args: 'sign-off PROP-1' })).text).toBe('Nothing was recorded.')
  expect(asked[0]).toMatch(/^Sign off PROP-1, as it reads now, so it may be sent\?/)
  expect((await $.command.run({ ...RUN, args: 'sign-off PROP-2' })).text).toBe('Nothing was recorded: PROP-2 has no go yet')
  expect(seen.some(line => line.includes('--confirmed'))).toBe(false)
})

test('the explore question names the topic, never a placeholder', () => {
  expect(exploreQuestion('explore/caching')).toContain('`explore branch caching`')
  expect(exploreQuestion('explore/caching')).not.toContain('<topic>')
})
