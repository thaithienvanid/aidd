# Running aidd inside Orca

[Orca](https://github.com/stablyai/orca) is a desktop app that runs coding agents side by side, each in its own git worktree, and ships an `orca` command-line tool. aidd works inside Orca with no extra setup, and a few things get easier there. Orca is always optional. Nothing in aidd needs it, and everything on this page does nothing outside Orca.

The Orca commands below were checked on 2026-10-22 against Orca 1.4.237, using `orca <command> --help` and `orca skills get orca-cli`. The `orca.yaml` format was checked on 2026-09-28 against Orca 1.4.215's source file `src/shared/orca-yaml.ts`. If your Orca is newer and a command fails, check `orca <command> --help`.

## What works as it is

- **Orca's worktrees are real git worktrees.** Run `aidd list --branch`, `aidd test`, and `aidd gate` in any of them, the same as in a worktree you made with `git worktree add`. Each worktree keeps its own files and its own `.aidd/evidence/`.
- **One worktree holds the default branch.** Give every linked worktree its own branch, named for its work. `aidd land` moves the default branch where it is checked out, so the root checkout's files follow, and a linked worktree keeps its own branch. `aidd doctor` notes when a linked worktree holds the default branch, with the two commands that move it back.
- **Approvals are shared.** Local approvals live in the decision records, on the git ref `refs/aidd/decisions`, and git shares refs between all the worktrees of a repository. An approval a person records in one worktree counts in every other one.
- **The guard still guards.** When Orca starts an agent, it runs the repository's own agent hooks in `.claude/` and `.codex/`. So the guard and the session hooks that `aidd init --harness <agent>` wired apply to every agent of that kind Orca starts, such as `--harness claude-code` for Claude Code. An agent with no hook wired runs unguarded, and only the gate checks its work. Claude Code runs PreToolUse hooks in every permission mode, so a deny from the guard still stops the command when Orca starts Claude with `--dangerously-skip-permissions`. The guard reads nothing from Orca.

## The aidd skill in Orca

`.agents/skills/aidd/` is an Agent Skills folder, so Orca finds it as it is. `orca skills installed` lists it as `aidd`, from the source `Repo <repository> .agents`, and every agent Orca starts in the repository can load it.

To have the skill in every project on this machine, install it with the community skills CLI, the one `orca skills install` runs for Orca's own skills:

```bash
npx skills@1.7.2 add https://github.com/thaithienvanid/aidd/tree/v1.0.0 --skill aidd
```

The skill alone doesn't wire the guard or write a config. In a repository you adopt, run `aidd init`, which does both.

## Set up a repository for Orca

Orca reads an optional `orca.yaml` at the root of the repository. The `setup` script runs after Orca creates a worktree, and each entry in `defaultTabs` opens a terminal tab in a new worktree. This one checks the setup and shows the next step:

```yaml
# orca.yaml
scripts:
  setup: |
    aidd doctor
setupAgentStartupPolicy: wait-for-setup   # start the agent after `aidd doctor` has run
defaultTabs:
  - title: aidd list --branch
    command: aidd list --branch
```

To write this file, run `aidd init --orca`, or write it by hand. `aidd init --orca` never replaces an `orca.yaml` that exists, and shows what it would add.

Orca asks you before it runs a repository's scripts, and asks again when they change. There's also `scripts.archive`, which runs before Orca archives a worktree.

## The workspace card

Each Orca worktree has a card with a short comment on it. When aidd's session hooks run inside Orca, they write this change's first step on that card. The comment is one line that starts with `aidd:` and ends with the work's state:

```text
aidd: SPEC-9 waits for Merge approval on its head commit (Approver) | waiting on @alice
```

- The line updates when a session starts and when the agent stops.
- It stays within 160 characters, so a long step is shortened, but never the state.
- aidd replaces only its own line, so anything you or another agent wrote on the card stays.

The state is the first of these that holds:

| State | When |
| --- | --- |
| `red: <tests> failed on HEAD` | the evidence `aidd test` wrote for the current commit records a test as failed on the head |
| `waiting on <who>` | the next step is a person's: an approval names its eligible approvers (two, then `+N`) |
| `stuck: no commit or handoff note for <time>` | the agent stopped, the work is still the agent's, and for 60 minutes or more there was no new commit and no change to an open Spec holding an `aidd-handoff` note (the file's modification time stands for the note's) |
| `working` | the next step is the agent's |

`stuck` is judged only when the agent stops; a session that starts shows `working`. Like the rest of the card, the state is a hint for people, never evidence.

The same update puts the worktree in its column on Orca's board, and marks it for you to look at:

| Board column | When |
| --- | --- |
| `todo` | nothing is open on the branch yet |
| `in-progress` | the state is `working`, `red`, or `stuck` |
| `in-review` | the next step is a person's decision |
| `completed` | the work landed or merged |

- While the next step is a person's decision, aidd marks the worktree unread, so its dot shows in Orca's sidebar. Once the decision is made, aidd clears the dot it set, and leaves one Orca set for its own reasons.
- After `aidd publish` opens the pull request or the merge request, aidd links it on the card, with `--pr <number>` on GitHub or `--gitlab-mr <number>` on GitLab.

The card is there for people to glance at. The gate doesn't read it, so it's never evidence and never an approval.

The update calls `orca worktree show`, then `orca worktree set --worktree path:<worktree>` with only what changed: `--comment <text>`, `--workspace-status <column>`, and `--unread` or `--read`. It gives up after 2 seconds, fails silently, and never changes what the hook tells the agent or what `aidd publish` does. It runs only when the Orca CLI is found and one of the Orca variables `ORCA_PANE_KEY`, `ORCA_WORKTREE_ID`, or `ORCA_AGENT_HOOK_PORT` is set. To turn it off:

```yaml
# .aidd/config.yaml
hooks:
  orca_status: false
```

## One agent per Task

`aidd list --branch --json` lists every Task of a Spec on the branch under `tasks`, in each of its `steps` for that Spec. Each Task has its `id`, `title`, `scope`, `depends_on`, its `skills` and `role` when the Spec names them, and a `status`. The status is `todo`, `in_progress`, `done`, `blocked`, or `stopped`. You start a `todo` Task, a `blocked` one says in `why` what it waits on, and a person re-plans a `stopped` one. [METHOD.md §5.1](METHOD.md#51-status) says what each status means.

Two Tasks whose scopes overlap must depend on one another, and `aidd validate` checks it, so the todo Tasks never change the same files. A Task unlocks once every Task in its `waiting_on` is done. Merge the branches of those Tasks into the Spec's branch. Run `aidd test` on that branch. The next `aidd list --branch --json` lists the Task as `todo`.

To start one Claude Code agent per todo Task, each in its own worktree branched from the Spec's branch, run this in your own terminal:

```bash
spec=specs/SPEC-9.md
aidd list --branch --json | jq -r --arg spec "$spec" '.steps[] | select(.where == $spec) | .tasks[] | select(.status == "todo") | .id' |
while read -r task; do
  orca worktree create --name "$task" --base-branch feat/spec-9 --agent claude \
    --prompt "Implement Task $task of $spec, inside its scope. Run aidd test before you say it is done." --json
done
```

An agent writes out one command per Task instead, with the Task's id in its prompt, such as `--prompt "Implement Task T1 of specs/SPEC-9.md"`. The guard denies a prompt it can't read, so it denies this loop when an agent runs it. The same JSON works for any script or coordinator, with or without Orca.

## Be careful with

- **Full autonomy is not a sandbox.** By default Orca starts each agent with its permission-bypass flag, `--dangerously-skip-permissions` for Claude, and treats the worktree as the boundary. A worktree does not limit the network, your credentials, or git refs, which every worktree shares. aidd's guard stops the approving, merging, landing, and publishing commands it recognizes; it is not a sandbox either. Switch to **Manual** under Settings → Agents → Agent Permissions, or run agents in a real sandbox, when that matters.
- **Removing a worktree hides its agent sessions.** A coding agent such as Claude Code lists its saved sessions by the folder they started in. When Orca, `git worktree remove`, or `aidd worktrees clean` removes a worktree, its sessions stay on disk but stop showing when you resume. To reach them again, add a worktree back at the same path with `git worktree add <path> <branch>`, and resume from there. Start each agent in the worktree it works in, because its status line and `/aidd update` follow that folder.
- **Orca's own gates are not approvals.** Orca's orchestration has decision gates, `ask`, worker status, and `worker_done` messages, and the card has a status. They help agents and humans coordinate. None of them is a Spec approval, a Merge approval, or evidence, because only a person's approval and the evidence from `aidd test` count at the gate.
- **Review `orca.yaml` and `.worktreeinclude` like CI.** `orca.yaml` runs commands on your machine for every new worktree, and `.worktreeinclude` copies git-ignored files, such as `.env`, into each one. Both are protected paths, so the gate makes any change to either a major change. That change needs a specialist Approver from the team profile up. Never list `.aidd/evidence/` in `orca.yaml`'s `worktree.sharedDirectories` or in `.worktreeinclude`. Evidence belongs to one worktree's head, so a shared folder lets one worktree's `aidd test` overwrite another's. The gate checks the head and refuses evidence for another commit, but the run is lost.
- **A browser is outside the guard.** Most of Orca's browser commands, such as `orca fill`, `orca inserttext`, and `orca exec`, can act on a platform's own web page, where only signed approvals, branch protection, and the gate hold. The guard reads only `orca type`.
- **Typing an approval into a terminal is guarded, twice.**
  - The guard denies the known ways an agent's command sends `aidd approve`, `aidd land`, `/aidd approve`, or a decision record into another terminal or program, or starts one there. It denies them even when quoting or escaping splits the words. The known ways are `orca terminal send`, `create`, and `split`; `orca orchestration send`, `ask`, `reply`, and `dispatch`; `orca computer type-text`, `paste-text`, `press-key`, `hotkey`, and `set-value`; `orca emulator type` and `exec`, `orca type`, and `orca automations create` and `edit`; `tmux send-keys` and `new-window`, `screen`, `zellij`, `open -a Terminal`, `osascript`, and the like.
  - The guard also denies `orca agent launch` and `orca worktree create` when `--prompt` holds a decision a person types, such as `approve SPEC-1`, `land it`, `merge it`, `publish`, or `approve all`. It denies `orca orchestration task-create` and `worker-start` the same way when a Task's `--spec` holds one. Orca 1.4.237 puts its own preamble before a worker's brief, so this guards against a later Orca that sends the brief alone. The new agent's prompt hook would record it as the person's words. It denies a prompt it can't read too, such as a variable or a command's output, and a command word it can't read. Orca reads its options anywhere on the line, so the guard does too. `orca claude-teams` starts Claude Code with the words after it, so the guard reads them as it reads `claude -p`. A task prompt such as `Implement Task T1` goes through. Write a prompt, a spec, and a run id inline, because the guard denies a variable there.
  - That is best-effort. `aidd approve` and `aidd land` also refuse in a shell an agent started, and go on only when a person at the terminal answers yes. A person runs `aidd approve` in a terminal they opened themselves, or types `approve SPEC-1` at their coding agent's prompt. A signing key that asks for the person's presence is what makes an approval theirs alone, as [Local-first](ADOPTION.md#local-first-no-github-or-gitlab) explains.
