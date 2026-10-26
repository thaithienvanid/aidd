// One item of `aidd list --json`: what is open, who holds it, and the next step.
export type Step = {
  id: string
  code: string
  title: string
  what: string
  who: string
  how: string
  priority: string
  status: string
  owner: string
  labels: string[]
  waitingOn: string[]
  why: string
  // "1 task, blocked": the Tasks in one line; `taskList` holds each one.
  tasks: string
  taskList: Task[]
  where: string
  isBlocked: boolean
  // The Initiative and the Epic it serves, from aidd's `why` chain, outermost first.
  parents: Link[]
  // What the Spec file says, for the detail card: read after `aidd list`, empty when there is no file to read.
  about: About
  // What the item's folder (`specs/<ID>/`) holds, as `aidd list --json` gives it: its docs, design, and explorations.
  files: ItemFile[]
}

// One entry of a work item's folder. `kind` is a linked document's kind (`tech-spec`, or `doc`), `design`,
// `exploration` (with its question and status, `open` or `decided`), `folder`, or `more` (with `count`).
export type ItemFile = { path: string; kind: string; question: string; status: string; count: number }

// One Task of a Spec, as `aidd list --json` gives it.
export type Task = {
  id: string
  title: string
  status: string
  why: string
  assignee: string
  role: string
  scope: string[]
  dependsOn: string[]
}

// What an item is about, from its file. A Spec: the first paragraph of Problem, and its Goals. A Proposal: who it is
// for (audience · addressee), the first paragraph of its need, and its goal.
export type About = { kind: string; for: string; problem: string; goals: string[] }

// One link of the chain: an Initiative or an Epic, with its progress as aidd counts it ("0/3").
export type Link = { kind: string; id: string; progress: string }

// An Initiative or an Epic as the pane lists it: its link, the title its file gives, and the Proposal it was made from
// (`proposal:` in its front matter, from `aidd proposal convert`), or ''.
export type Parent = Link & { title: string; from: string }

// One autopilot lease from `aidd autopilot status --json`.
export type Lease = { work: string; by: string; session: string; expiresAt: string; timebox: string; isStale: boolean }

export type Autopilot = { leases: Lease[]; last: string | null; heard: string | null }

// A section is what aidd answered, or the line it failed with.
export type Section<T> = { isOk: true; value: T } | { isOk: false; error: string }

// One rung of a small goal's decision ladder: how many are past it, of how many, and what waits on a person now.
export type Rung = { done: number; total: number; waits: string[] }

// A small goal (an Epic on the default branch), as `aidd goal list --json` gives it: how it reaches users, and where each of
// the person's decisions stands (D1 the plan, D2 Spec approval, D3 the release, D4 the launch of a flagged one).
export type SmallGoal = {
  id: string
  title: string
  parent: string | null
  reaches: 'incremental' | 'flagged' | 'batched'
  branch: string | null
  specs: { id: string; status: string }[]
  specApproval: Rung
  release: Rung
  launch: { spec: string; state: 'todo' | 'waits' | 'done' } | null
}

// A branch with work the default branch lacks, or a goal branch: how old, and how far behind.
export type BranchAge = { branch: string; ageDays: number; behind: number }

// The shape of the work: big goals, small goals, the goal branches, and the trunk-based flow.
export type Shape = {
  initiatives: { id: string; title: string; smallGoals: string[] }[]
  smallGoals: SmallGoal[]
  goals: (BranchAge & { releaseReady: boolean; waiting: string[] })[]
  branches: BranchAge[]
  warnings: string[]
}

// One decision that waits on the person: which of the four (D1 to D4; '' for another kind), its words, and what to type.
export type Decision = { rung: string; label: string; id: string; title: string; type: string }

export type Snapshot = {
  root: string
  head: string
  at: number
  branch: Section<Step[]>
  waiting: Section<Step[]>
  autopilot: Section<Autopilot>
  // The shape of the work from `aidd goal list --json`.
  shape: Section<Shape>
  // The person's standing approval in force, as one line; null when none is.
  standing: string | null
}

declare module 'claude-code' {
  interface PluginState {
    'aidd-mods': { snapshot: Snapshot | null; isLoading: boolean; selected: string | null; focus: string | null; task: string | null }
  }
}
