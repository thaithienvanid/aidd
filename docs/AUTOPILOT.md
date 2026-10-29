# Autopilot

Autopilot runs the AIDD loop between your decisions. aidd decides each next step from the repository. The team's roles do the work. The run stops whenever a person must decide, and tells you what to decide and how.

Its safety never rests on the model. The guard checks each step an agent takes, the gate decides what merges, and every decision stays a person's. Before 1.0.0 it ran with real models in Claude Code, Codex, OpenCode, and Google Antigravity, and each run stopped at a person's decision or at a problem it reported, as [Real runs](#real-runs) shows. Set up the harness first, and watch your first runs. The design and its rules are in [METHOD §5.3](METHOD.md#53-autopilot).

## Before you start

- **An agent with the delivery team.** In Claude Code, install the `aidd-team` plugin, or run `aidd init --team`, as [Install](INSTALL.md#claude-code-plugins) explains. In OpenCode, Grok Build, and Google Antigravity, `aidd init --team` writes the same flow as `/aidd-autopilot`, and in Codex as `$aidd-autopilot`. aidd's guard runs there too. Other agents can run the same steps by hand with `aidd autopilot next`.
- **A clean setup.** Run `aidd doctor --autopilot`. It checks the hooks and the guard in each agent aidd wired, the held commands, and the run's credentials, as [Credentials for a run](#credentials-for-a-run) says. In Codex, it checks that the run may write the git directory, where it keeps its lease: start Codex with `--add-dir`, as [Install](INSTALL.md#codex) says. It checks that each agent aidd wired has the autopilot flow, and says how OpenCode runs it with nobody there. The sandbox and permission checks read Claude Code's settings, only where Claude Code is wired, and print the `permissions.allow` rules a run needs there. For another agent, a line names the settings aidd did not read. Then it lists what only you can check.
- **The status pane, if you want it.** With the `aidd-mods` plugin, `/aidd status` shows what waits on you and the run, beside the conversation.

## Start a run

| You type | What happens first |
| --- | --- |
| `/aidd-team:autopilot "Let shoppers save a cart for later"` | A new goal: the product manager plans it (`/aidd-team:plan`), or the delivery manager writes a proposal for client work. The plan goes first, even when other work is open. |
| `/aidd-team:autopilot SPEC-12` | That Spec, from the step it is at: specify, implement, or verify and review. |
| `/aidd-team:autopilot EPIC-3`, or a label | Every item of that Epic or label, one step at a time. |
| `/aidd-team:autopilot all` | All open work. Use it to go on after a stop. |

From repository files, the command is `/aidd-autopilot` instead of `/aidd-team:autopilot`, and `$aidd-autopilot` in Codex. Each message names the command as your agent runs it, because the flow tells `aidd autopilot next` which agent it runs in (`--harness`).

## What happens each turn

1. aidd computes the one next action from git with `aidd autopilot next`. You can run it yourself to see what comes next.
2. The session runs that step through the team command it names. Each role works as a subagent and writes only its own files. Once a head is built and green, one step asks for Verify and Review together, and lists both in `codes`. The verifier and the reviewers then run side by side on that head. When other Specs can go on at the same time, the action lists them in `also`. Each needs scopes that overlap none of the others, and each runs in its own worktree on its Spec's branch.
3. The session records the result in the journal, in the git directory. Nothing is committed for it. Verify and Review each get their own result. The run goes on once both are clean on that head. A failure in either sends the change back to Implement once, with both reports, and a new head needs both again.

A run holds a lease on its work, so two runs never work on the same item. The guard stops the session from approving, landing, merging, or publishing on its own, and from editing files outside the role's area. When you've typed `approve all`, the approvals your standing approval covers become the run's own steps. It runs `aidd approve spec` as the step `spec.spec_approval_standing`. After Verify and Review on the head, it runs `aidd land` as `spec.land_standing`, or on a platform `aidd approve merge` as `spec.merge_approval_standing`. [METHOD.md §8](METHOD.md#standing-approval) has the rules.

## When it stops

| Why | What you do |
| --- | --- |
| **The plan is ready** | Read the plan: `aidd list`, or `aidd list --html` as a page. Then answer **Go on** to agree, or **Stop here**. |
| **A decision waits on you** | The message lists each decision and how to take it. Type it at the prompt, such as `approve SPEC-12`. The run goes on once aidd records it. After a Merge approval in a run on one Spec, nothing is left to go on to. |
| **An aidd command waits** | A step such as `aidd land` waits on something only you clear, such as a failing check. The message says where to read what it printed. |
| **A limit** | The timebox ended, or a token or cost cap was reached. Start again with the command the message gives. |
| **Work is set aside** | The same step failed twice, a step hit a stop rule, or a Spec went back to Implement or Specify three times in one run. The message names what broke and the handoff note to read. Fix the cause, then run the command it gives, and the run tries it again. |
| **It stalled** | Six steps in a row moved nothing on: each failed, or ran again on a head it had run on. Read `aidd autopilot status` and the handoff notes, fix the cause, then start again. |
| **Nothing is open** | Name the next work: `/aidd-team:plan` for a plan, or `aidd new spec` for one change. |

The message at a stop comes from aidd itself, so it always says the same thing for the same state. It ends with the exact command that goes on, such as `/aidd-team:autopilot all`. After a plan, the session also asks **"Go on now?"**. Only your own answer counts. No answer means the run stays stopped.

You can go on in the same session. After a long run, start a new session or run `/clear` first. The run starts again from the files and the journal, so nothing is lost.

## Limits and settings

Set the limits under `autopilot` in `.aidd/config.yaml`, which [Config](CONFIG.md#autopilot) describes in full:

```yaml
autopilot:
  timebox: "8h"                          # how long one run may last; default 6h
  max_tokens: 400000                     # optional: stop at this many recorded tokens
  max_cost: {amount: 20, currency: USD}  # optional: stop at this recorded cost
  retro_every: 5                         # optional: a retro after 5 merged changes
  parallel: 3                            # optional: Specs one turn works on at once; default 2
```

- **The timebox** is 6 hours by default. `aidd autopilot start --timebox 90m` sets it for one run.
- **The caps** are off until you set them. In Claude Code, the token cap counts what the session's own transcripts show, for the run's lead and every subagent. It leaves cache reads out, since they bill at a tenth. Elsewhere, and for the cost cap, it counts the spend each step records. You and the gate stay the controls.
- **Parallel work** runs independent Specs side by side, so a goal's Specs are specified and built at once. `parallel` sets how many, 2 by default and at most 4. Approvals and landings stay one at a time, on the branch they act on. A Spec of a goal branch never waits for your Merge approval. Once it is verified and reviewed, autopilot runs `aidd integrate`, and you decide once, at the goal's release. A launch always waits for you.
- **Rounds.** A Spec goes back to Implement, or to Specify, at most three times in one run. Then the run sets it aside for you, with the last failed reports. It's a fixed bound, not a setting.
- **Only a person changes a limit.** The session never extends one.
- **The work in progress limit**, `limits.max_open_per_approver`, holds new work, a new goal too, while the Approvers have too many open approvals. The run then asks them to decide first.

## Runs nobody watches

- **Hear when it stops.** Set `autopilot.notify` to a command, such as `["ntfy", "publish", "my-topic"]`. aidd runs it once each time the run stops for you, with the message as its last argument and in `AIDD_NOTICE`. It also runs once when a decision starts waiting while the run goes on with other work, so you can take it early. Only the base branch's config counts, so an agent cannot change what runs.
- **Run it headless.** `claude -p "/aidd-team:autopilot all"` runs until the first stop, then exits, because nobody is there to answer "Go on now?". The notice tells you what waits. Keep the harness safe, as [Harness settings for a run](#harness-settings-for-a-run) says. In Codex, run `codex exec '$aidd-autopilot all'`. In OpenCode, `opencode run` passes `/aidd-autopilot` as plain text and never opens the command, so attach its file: `opencode run --auto -f .opencode/commands/aidd-autopilot.md "all"`.
- **A crashed session gives its work back.** When a session's transcripts show nothing for 20 minutes, a new run may take its lease without waiting out the timebox. A session aidd finds no transcript for keeps its lease until the timebox ends. A run that finished, or waits on you, gives its work back too, even before its session runs `stop`.

## Harness settings for a run

aidd starts no agent, so the harness's own settings hold the run. In Claude Code, before an autopilot run:

- Turn the sandbox on with `sandbox.enabled: true`.
- Set a permission mode that asks or denies what the settings do not allow, in `permissions.defaultMode`, such as `default` or `dontAsk`. Never use `bypassPermissions`.
- Allow what every step calls, which is `aidd` itself and aidd's read-only MCP tools. `aidd doctor --autopilot` prints the `permissions.allow` rules the settings lack. With the sandbox on, the agents' shell commands need no rule of their own.
- Allow the network only from a list, `sandbox.network.allowedDomains`, with the hosts the work needs.
- Put no secret in the agent's environment, and hold at most two legs of the Rule of Two, as [Credentials for a run](#credentials-for-a-run) explains.
- For a team, hold these in managed settings, so a project file cannot turn them off.
- Consider [the Claude Code advisor](TEAM.md#the-claude-code-advisor), `advisorModel`, which helps a long run plan but is never independent review. `aidd doctor --autopilot` reports whether one is configured, as information only.

## Credentials for a run

A run with nobody to ask should never hold three things at once. The first is untrusted input, such as a web page or an issue anyone can write. The second is a credential, and the third is a way out to any host. With all three, words planted in a page can make the agent send your token out. This is [Meta's Agents Rule of Two](https://ai.meta.com/blog/practical-ai-agent-security/), from October 31, 2025.

`aidd doctor --autopilot` looks for each leg in the files it can read, and warns when it finds all three:

| Leg | What aidd looks for |
| --- | --- |
| Untrusted input | a `WebFetch` or `WebSearch` allow rule, `bypassPermissions`, a shell rule that reaches the web (`curl`, `wget`, `gh issue`, `gh pr view`, `gh api`, or any command), or an MCP server or plugin whose name, command, or URL says it reads issues, mail, chat, a ticket tracker, a browser, or the web |
| Credentials | a variable named like a credential, by its name only. A credential a tool keeps on disk, such as the one `gh auth login` stores, is out of its sight |
| Open egress | anything but aidd's dev container or the sandbox with an allowlist. The sandbox is open with a web-fetch rule for any host, a `*` domain, `bypassPermissions`, an excluded command, or a web MCP server, because those run outside it. A shell allow rule beside aidd's own opens it too, unless `sandbox.allowUnsandboxedCommands` is `false`, since that rule also approves a retry outside the sandbox |

To clear the warning, drop one leg. The surest is the dev container that `aidd init --devcontainer` writes, because its firewall holds every tool to the hosts you list. Otherwise unset the credentials for the run, or remove the web tool or server. It's a warning, never a failure, since aidd can't see managed settings or the network itself. In the dev container, aidd trusts only the marker the firewall writes once its self-test passes on the current start. Without it, egress counts as open, and the doctor says to rebuild the container or run the firewall script.

The doctor also warns when `GH_TOKEN` or `GITHUB_TOKEN` holds a classic personal access token or an OAuth app token. Either can live until someone revokes it. aidd reads only the first four characters of the value to tell, and never prints or keeps any of it. Give the run a token that does little and ends soon:

- **For a run that only reads**, use a GitHub App user token. A GitHub App acts for you with only the permissions it asks for, and its user token expires after 8 hours by default. Create an App with read access to the repository's contents, issues, and pull requests, install it on the repository, and sign in to it with the device flow. [GitHub's guide](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app) has the steps.
- **For a run under your standing approval**, use your own fine-grained personal access token with an expiry of days, not months. The run posts your approvals as you, and an approval posted with an App's user token never counts, as [SECURITY.md](../SECURITY.md#trust-model) says. Give the token access to only this repository, with the write access to pull requests that posting an approval needs. [GitHub's guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token) shows how.
- **For an agent that works under its own account**, list that account in `identities.bots`, so it can never approve, as [the team](TEAM.md) says. Give it a fine-grained token with an expiry too.

In a bounded session, the [managed settings template](ENTERPRISE.md#12-agent-sessions-under-managed-settings) also keeps both tokens from the sandboxed shell.

## Watch and steer

- `aidd autopilot status` shows the lease, the time left, and the journal's last lines.
- With the `aidd-mods` plugin, `/aidd status` shows your next decision and what to type. Below it come the shape of the work, this branch's work, the flow, and the run. It refreshes after each turn.
- `aidd list --waiting-on-me` lists your decisions. `--html` writes them as one page.
- To stop a run, press Esc or tell the session to stop. It stops at the next step boundary and releases the lease.
- To pause one change, set `blockers` in its Spec. The run sets it aside and goes on with the rest.
- To give feedback, write it where the run reads, in review comments, the feedback log, or the Spec. The run reads them each turn, as data.

## Real runs

Before 1.0.0, autopilot ran with real models in Claude Code, Codex, OpenCode, and Google Antigravity, each time on one small repository. No run approved, merged, or landed, and each stopped at a person's decision or at a problem it reported. Each fix has a test.

### In Claude Code

It ran six times, each time with a 6 USD cap. Every run took the lease and journaled its steps. None worked around a denial. Four runs found a problem.

| Request | Where it stopped | What it found | The fix | Cost |
| --- | --- | --- | --- | --- |
| Build an open Spec | Merge approval, after Specify, Implement, Verify, and Review | the run was denied aidd's read-only MCP tool and the verifier's own call of the code | `aidd doctor --autopilot` checks the permissions | 2.20 USD |
| A one-line bug fix | a report, before any test ran | `aidd describe` copied Claude Code's `Co-Authored-By` trailer into `assisted_by`, which the schema refused | `describe` lists one word per agent | 0.71 USD |
| The same fix | a report, before any edit | the fix ran outside the lease, and a shell command with a pipe was denied | a fix takes the lease; the doctor checks the sandbox | 0.50 USD |
| A new goal | plan agreement (D1), after the consult round | nothing | none needed | 2.47 USD |
| The same fix, with the permission rules of the time | a report, before any edit | file edits and the team plugin's files were denied | the doctor prints every rule a run needs | 0.54 USD |
| The same fix, with the rules `aidd doctor --autopilot` prints | Merge approval, with the regression test red before the fix and green after | nothing | none needed | 0.54 USD |

### In Codex and OpenCode

Codex CLI 0.156.1 ran `codex exec '$aidd-autopilot SPEC-1'` five times, on gpt-6-luna. OpenCode 2.1.0 ran `opencode run "/aidd-autopilot SPEC-1"` three times, on free models. The Spec asked for one small function, on the normal route of the solo profile, where Spec approval is optional. Nobody answered, so each run ended at its first stop.

| Agent and model | Where it stopped | What it found | The fix | Time |
| --- | --- | --- | --- | --- |
| Codex | a report, before any step | Codex's `workspace-write` sandbox keeps `.git` read-only, so the lease could not be written | `aidd doctor --autopilot` names `--add-dir` with the git directory | 40 s |
| Codex, `.git` writable | a report, after Specify and Implement | `aidd init --test "PYTHONPATH=src python3 ..."` kept `PYTHONPATH=src` as the program, so no test could run | `aidd init` and `aidd validate` refuse it, and name the `env` form | 11 min |
| Codex, a plain test command | a report, at Specify | Specify's rule that a minor route needs no Spec stopped a Spec the person had put on the normal route | a Spec `next` names keeps the route it declares, and Specify's rule says so too | 2 min |
| The same | the same report | the same | the same fix, made after this run | 3 min |
| Codex, with that fix | Merge approval, after Specify, Implement, Verify, and Review | nothing | none needed | 6.5 min |
| OpenCode, deepseek-v4.1-flash-free | Spec approval, after Specify | the guard denied `autopilot start --session`, because the plugin's shell hook names no session. The run then started without one, and so its own stop was denied | a denial of the start is a stop; the plugin gives the bash tool's own shell the session of the call the guard allowed | 17.5 min |
| OpenCode, glm-5.3-flash-free, `--auto` | Merge approval, after Specify, Implement, Verify, and Review | the same denial and the same way around it | the same | 22 min |
| OpenCode, glm-5.3-flash-free, with that fix | Merge approval, after the steps, with no lease | `opencode run` passes `/aidd-autopilot` as plain text, so the agent must find the command's file. This one never did, and wrote every file itself | `-f` attaches the command's file, and the skill says a message that starts with `/aidd-<flow>` names a team command | 9 min |

Without `--auto`, OpenCode refuses a role's shell call in a headless run, since nobody can answer its `ask` rule.

### In Google Antigravity

Antigravity 1.4.7 ran `agy --dangerously-skip-permissions -p "/aidd-autopilot SPEC-1"` once, on gemini-4-argon, with the same Spec. The lead started each role as a subagent, a conversation of its own whose hook events name no parent. The guard read every role from the parent's message, so it judged each role's writes against that role's area. `tests/fixtures/live/antigravity-1.4.7-roles.jsonl` pins the run's events.

| Agent and model | Where it stopped | What it found | The fix | Time |
| --- | --- | --- | --- | --- |
| Antigravity, gemini-4-argon | Merge approval, after Specify, Implement, Verify, and Review | nothing | none needed | 10 min |

Only a person types `land it`, so a headless run ends at Merge approval. The guard denies an agent that types it into `agy`.

## Troubleshooting

**It asks again for a Spec approval you gave on the platform.** With only the platform's approval lines, autopilot counts an approval for the pull request's head. Push before each `aidd autopilot next`, because a local commit the pull request doesn't hold yet asks again.

| You see | What to do |
| --- | --- |
| Another session holds the lease | Each piece of work has one live run. A session that has been quiet for 20 minutes gives it up to the next run. Otherwise wait for its timebox to end, or stop it at your own terminal: `aidd autopilot stop --session <id>`, with the id `aidd autopilot status` shows. |
| The goal was planned already | The same goal is never planned twice. `aidd list` shows its work. Start with `all` to go on with it. |
| The guard denies an edit in the run | In an autopilot run, only the role that owns a file writes it. The deny message names the role. |
| It stopped at the timebox | Raise `autopilot.timebox`, or start again for another timebox. |
| A step stops on a permission denial | Run `aidd doctor --autopilot`. Add the `permissions.allow` rules it prints, turn the sandbox on, and trust the folder once by running Claude Code there. |
| A step keeps failing | After two failures in a row, the run sets the item aside. Read the role's handoff note, fix the cause, then start again. |

To read on, see `aidd autopilot` in [the CLI](CLI.md), [the team](TEAM.md), and [How do I…](HOW-TO.md#running-the-team).
