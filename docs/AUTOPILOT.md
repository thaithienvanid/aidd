# Autopilot

Autopilot runs the AIDD loop between your decisions. aidd decides each next step from the repository. The team's roles do the work. The run stops whenever a person must decide, and tells you what to decide and how.

Its safety never rests on the model. The guard checks each step an agent takes, the gate decides what merges, and every decision stays a person's. Before 1.0.0 it ran six times with real models, and each run stopped at a person's decision or at a problem it reported ([Real runs](#real-runs)). Set up the harness first, and watch your first runs. The design and its rules are in [METHOD §5.3](METHOD.md#53-autopilot).

## Before you start

- **Claude Code with the delivery team.** Install the `aidd-team` plugin, or run `aidd init --team` ([Install](INSTALL.md#claude-code-plugins)). Other agents can run the same steps by hand with `aidd autopilot next`.
- **A clean setup.** Run `aidd doctor --autopilot`. It checks the hooks, the guard, the held commands, the sandbox, and the permissions, and prints the `permissions.allow` rules a run needs. Then it lists what only you can check.
- **Optional: the status pane.** With the `aidd-mods` plugin, `/aidd status` shows what waits on you and the run, beside the conversation.

## Start a run

| You type | What happens first |
| --- | --- |
| `/aidd-team:autopilot "Let shoppers save a cart for later"` | A new goal: the product manager plans it (`/aidd-team:plan`), or the delivery manager writes a proposal for client work. The plan goes first, even when other work is open. |
| `/aidd-team:autopilot SPEC-12` | That Spec, from the step it is at: specify, implement, verify, or review. |
| `/aidd-team:autopilot EPIC-3`, or a label | Every item of that Epic or label, one step at a time. |
| `/aidd-team:autopilot all` | All open work. Use it to go on after a stop. |

From repository files, the command is `/aidd-autopilot` instead of `/aidd-team:autopilot`.

## What happens each turn

1. aidd computes the one next action from git: `aidd autopilot next`. You can run it yourself to see what comes next.
2. The session runs that step through the team command it names. Each role works as a subagent and writes only its own files. When other Specs can go on at the same time, the action lists them in `also`. Each needs scopes that overlap none of the others, and each runs in its own worktree on its Spec's branch.
3. The session records the result in the journal, in the git directory. Nothing is committed for it.

A run holds a lease on its work, so two runs never work on the same item. The guard stops the session from approving, merging, or shipping, and from editing files outside the role's area. Under the person's standing approval (`approve all`), the approvals it covers become the run's own steps: `aidd approve spec` (`spec.approve_standing`), and after Verify and Review on the head, `aidd ship` (`spec.ship_ready`) or, on a platform, `aidd approve merge` (`spec.merge_standing`) ([METHOD.md §8](METHOD.md#standing-approval)).

## When it stops

| Why | What you do |
| --- | --- |
| **The plan is ready** | Read the plan: `aidd list`, or `aidd list --html` as a page. Then answer **Go on** to agree, or **Stop here**. |
| **A decision waits on you** | The message lists each decision and how to take it. Spec approval happens at your own terminal: `aidd approve spec specs/SPEC-12.md`. Then answer **Go on**. |
| **A limit** | The timebox ended, or a token or cost cap was reached. Start again with the command the message gives. |
| **The same step failed twice** | That item is set aside for a person. Read its handoff note, then fix or re-plan it. |
| **It stalled** | Six steps in a row moved nothing on: each failed, or ran again on a head it had run on. Read `aidd autopilot status` and the handoff notes, fix the cause, then start again. |
| **Nothing is open** | Give autopilot a goal. |

The message at a stop comes from aidd itself, so it always says the same thing for the same state. It ends with the exact command that goes on, such as `/aidd-team:autopilot all`. After a plan or a decision, the session also asks **"Go on now?"**. Only your own answer counts. No answer means the run stays stopped.

You can go on in the same session. After a long run, start a new session or run `/clear` first. The run starts again from the files and the journal, so nothing is lost.

## Limits and settings

Set the limits under `autopilot` in `.aidd/config.yaml` ([Config](CONFIG.md#autopilot)):

```yaml
autopilot:
  timebox: "8h"                          # how long one run may last; default 6h
  max_tokens: 400000                     # optional: stop at this many recorded tokens
  max_cost: {amount: 20, currency: USD}  # optional: stop at this recorded cost
  retro_every: 5                         # optional: a retro after 5 merged changes
  parallel: 3                            # optional: Specs one turn works on at once; default 2
```

- **The timebox** is 6 hours by default. `aidd autopilot start --timebox 90m` sets it for one run.
- **The caps** are off until you set them. In Claude Code, the token cap counts what the session's own transcripts show: the run's lead and every subagent, with cache reads left out, since they bill at a tenth. Elsewhere, and for the cost cap, it counts the spend each step records. You and the gate stay the controls.
- **Parallel work** (`parallel`, 2 by default, at most 4) runs independent Specs side by side, so a goal's Specs are specified and built at once. Approvals and ships stay one at a time, on the branch they act on. A Spec of a goal branch never waits for your Merge approval: once it is verified and reviewed, autopilot runs `aidd integrate`, and you decide once, at the goal's release. A launch always waits for you.
- **Only a person changes a limit.** The session never extends one.
- **The work in progress limit** (`gates.max_open_per_approver`) holds new work, a new goal too, while the Approvers have too many open approvals. The run then asks them to decide first.

## Runs nobody watches

- **Hear when it stops.** Set `autopilot.notify` to a command, such as `["ntfy", "publish", "my-topic"]`. aidd runs it once each time the run stops for you, with the message as its last argument and in `AIDD_NOTICE`. Only the base branch's config counts, so an agent cannot change what runs.
- **Run it headless.** `claude -p "/aidd-team:autopilot all"` runs until the first stop, then exits: nobody is there to answer "Go on now?". The notice tells you what waits. Keep the harness profile below: the sandbox on, a permission mode that asks or denies, and no secrets in the environment.
- **A crashed session gives its work back.** When a session's transcripts show nothing for 20 minutes, a new run may take its lease without waiting out the timebox. A session aidd finds no transcript for keeps its lease until the timebox ends.

## Watch and steer

- `aidd autopilot status` shows the lease, the time left, and the journal's last lines.
- `/aidd status` (the `aidd-mods` plugin) shows your next decision and what to type. Below it come the shape of the work, this branch's work, the flow, and the run. It refreshes after each turn.
- `aidd list --waiting-on-me` lists your decisions. `--html` writes them as one page.
- To stop a run, press Esc or tell the session to stop. It stops at the next step boundary and releases the lease.
- To pause one change, set `blocked_on` in its Spec. The run sets it aside and goes on with the rest.
- To give feedback, use the files: review comments, the feedback log, or the Spec. The run reads them each turn, as data.

## Real runs

Before 1.0.0, autopilot ran six times in Claude Code with real models, on one small repository, each time with a 6 USD cap. Every run took the lease, journaled its steps, and stopped where it should: at a person's decision, or at a problem it reported. None approved, merged, or worked around a denial. Four runs found a problem, and each fix has a test.

| Request | Where it stopped | What it found | The fix | Cost |
| --- | --- | --- | --- | --- |
| Build an open Spec | Merge approval, after Specify, Implement, Verify, and Review | the run was denied aidd's read-only MCP tool and the verifier's own call of the code | `aidd doctor --autopilot` checks the permissions | 2.20 USD |
| A one-line bug fix | a report, before any test ran | `aidd describe` copied Claude Code's `Co-Authored-By` trailer into `assisted_by`, which the schema refused | `describe` lists one word per agent | 0.71 USD |
| The same fix | a report, before any edit | the fix ran outside the lease, and a shell command with a pipe was denied | a fix takes the lease; the doctor checks the sandbox | 0.50 USD |
| A new goal | plan agreement (D1), after the consult round | nothing | none needed | 2.47 USD |
| The same fix, with the permission rules of the time | a report, before any edit | file edits and the team plugin's files were denied | the doctor prints every rule a run needs | 0.54 USD |
| The same fix, with the rules `aidd doctor --autopilot` prints | Merge approval, with the regression test red before the fix and green after | nothing | none needed | 0.54 USD |

## Troubleshooting

| You see | What to do |
| --- | --- |
| Another session holds the lease | Each piece of work has one live run. A session that has been quiet for 20 minutes gives it up to the next run. Otherwise wait for its timebox to end, or stop it at your own terminal: `aidd autopilot stop --session <id>`, with the id `aidd autopilot status` shows. |
| The goal was planned already | The same goal is never planned twice. `aidd list` shows its work. Start with `all` to go on with it. |
| The guard denies an edit in the run | In an autopilot run, only the role that owns a file writes it. The deny message names the role. |
| It stopped at the timebox | Raise `autopilot.timebox`, or start again for another timebox. |
| A step stops on a permission denial | Run `aidd doctor --autopilot`. Add the `permissions.allow` rules it prints, turn the sandbox on, and trust the folder once by running Claude Code there. |
| A step keeps failing | After two failures in a row, the run sets the item aside. Read the role's handoff note, fix the cause, then start again. |

More: [the CLI](CLI.md) (`aidd autopilot`), [the team](TEAM.md), and [How do I…](HOW-TO.md#running-the-team).
