# Running aidd inside Orca

[Orca](https://github.com/stablyai/orca) is a desktop app that runs coding agents side by side, each in its own git worktree, and ships an `orca` command-line tool. aidd works inside Orca with no extra setup, and a few things get easier there. Orca is always optional: nothing in aidd needs it, and everything on this page does nothing outside Orca.

The Orca commands and file formats below were checked on 2026-09-28 against Orca 1.4.215 (`orca <command> --help`) and its source (`src/shared/orca-yaml.ts`). If your Orca is newer and a command fails, check `orca <command> --help`.

## What works as it is

- **Orca's worktrees are real git worktrees.** Run `aidd next`, `aidd test`, and `aidd gate` in any of them, the same as in a worktree you made with `git worktree add`. Each worktree keeps its own files and its own `aidd-evidence/`.
- **Approvals are shared.** Local approvals live on the git ref `refs/aidd/approvals`, and git shares refs between all the worktrees of a repository. An approval a person records in one worktree counts in every other one.
- **The guard still guards.** Orca runs the repository's own agent hooks (`.claude/` and `.codex/`) when it starts an agent. So the edit-time guard and the session hooks that `aidd init` wired apply to every agent Orca starts. Claude Code runs PreToolUse hooks in every permission mode, so a deny from the guard still stops the command when Orca starts Claude with `--dangerously-skip-permissions`. The guard reads nothing from Orca.

## Set up a repository for Orca

Orca reads an optional `orca.yaml` at the root of the repository. The `setup` script runs after Orca creates a worktree, and each entry in `defaultTabs` opens a terminal tab in a new worktree. This one checks the setup and shows the next step:

```yaml
# orca.yaml
scripts:
  setup: |
    aidd doctor
setupAgentStartupPolicy: wait-for-setup   # start the agent after `aidd doctor` has run
defaultTabs:
  - title: aidd next
    command: aidd next
```

Orca asks you before it runs a repository's scripts, and asks again when they change. `scripts.archive` also exists: it runs before Orca archives a worktree.

## The workspace card

Each Orca worktree has a card with a short comment on it. When aidd's session hooks run inside Orca, they write the first step of `aidd next` on that card, as one line that starts with `aidd next:` and ends with the work's state:

```text
aidd next: SPEC-9 waits for Merge approval on its head commit (an approver) | waiting on @alice
```

- The line updates when a session starts and when the agent stops.
- It stays within 160 characters: a long step is shortened, never the state.
- aidd replaces only its own line, so anything you or another agent wrote on the card stays.

The state is the first of these that holds:

| State | When |
| --- | --- |
| `red: <tests> failed on HEAD` | the evidence `aidd test` wrote for the current commit records a test as failed on the head |
| `waiting on <who>` | the next step is a person's: an approval names its eligible approvers (two, then `+N`) |
| `stuck: no commit or handoff note for <time>` | the agent stopped, the work is still the agent's, and for 60 minutes or more there was no new commit and no change to an open Spec holding an `aidd-handoff` note (the file's modification time stands for the note's) |
| `working` | the next step is the agent's |

`stuck` is judged only when the agent stops; a session that starts shows `working`. Like the rest of the card, the state is a hint for people: it is never evidence.

The card is there for people to glance at. It is never evidence and never an approval: the gate does not read it.

The update calls `orca worktree show` and `orca worktree set --worktree path:<worktree> --comment <text>`. It gives up after 2 seconds, fails silently, and never changes what the hook tells the agent. It runs only when an Orca variable (`ORCA_PANE_KEY`, `ORCA_WORKTREE_ID`, or `ORCA_AGENT_HOOK_PORT`) is set and the Orca CLI is found. To turn it off:

```toml
# .aidd/config.toml
[hooks]
orca_status = false
```

## One agent per Task

`aidd next --json` lists every Task of each active Spec under `tasks`, with its `id`, `title`, `scope`, `depends_on`, its `skills` and `role` when the Spec names them, and a `status`:

- `ready`: the Spec is approved and the Task waits for nothing. Start it.
- `blocked`: the Spec is not approved yet, is blocked, or the Task waits for the Tasks in `waiting_on`. `why` says which.
- `done`: the Spec is past implementation.

Two Tasks whose scopes overlap must depend on one another (`aidd validate` checks it), so the ready Tasks never change the same files. aidd does not record when one Task finishes, so a Task with Tasks in `waiting_on` stays `blocked` in the JSON even after they are done: once their branches are merged into the Spec's branch, start it yourself.

To start one Claude Code agent per ready Task, each in its own worktree branched from the Spec's branch:

```bash
spec=specs/SPEC-9.md
aidd next --json | jq -r --arg spec "$spec" '.[] | select(.where == $spec) | .tasks[] | select(.status == "ready") | .id' |
while read -r task; do
  orca worktree create --name "$task" --base-branch feat/spec-9 --agent claude \
    --prompt "Implement Task $task of $spec, inside its scope. Run aidd test before you say it is done." --json
done
```

The same JSON works for any script or coordinator, with or without Orca.

## Be careful with

- **Full autonomy is not a sandbox.** By default Orca starts each agent with its permission-bypass flag (Claude: `--dangerously-skip-permissions`), and treats the worktree as the boundary. A worktree does not limit the network, your credentials, or git refs, which every worktree shares. aidd's guard stops the approving, merging, and shipping commands it recognizes; it is not a sandbox either. Switch to **Manual** under Settings → Agents → Agent Permissions, or run agents in a real sandbox, when that matters.
- **Orca's own gates are not approvals.** Orca's orchestration has decision gates, `ask`, worker status, and `worker_done` messages, and the card has a status. They help agents and people coordinate. None of them is a Spec approval, a Merge approval, or evidence: only a person's approval and the evidence from `aidd test` count at the gate.
- **Review `orca.yaml` and `.worktreeinclude` like CI.** `orca.yaml` runs commands on your machine for every new worktree, and `.worktreeinclude` copies git-ignored files (such as `.env`) into each one. Both are protected paths, so the gate makes any change to either a major change, with a specialist's review.
- **Typing an approval into a terminal is guarded, twice.**
  - The guard denies the known ways an agent's command sends `aidd approve`, `aidd ship`, `/aidd approve`, or an approval record into another terminal or program, or starts one there, even when quoting or escaping splits the words: `orca terminal send`, `create`, and `split`; `orca orchestration send`, `ask`, `reply`, and `dispatch`; `orca computer type-text`, `paste-text`, `press-key`, and `hotkey`; `tmux send-keys` and `new-window`, `screen`, `zellij`, `open -a Terminal`, `osascript`, and the like.
  - That is best-effort, so the approval itself asks for more: `aidd approve` and `aidd ship` show a one-time code and go on only when it is typed back, and an agent cannot know that code before the prompt appears. A person runs `aidd approve` in a terminal they opened themselves.
