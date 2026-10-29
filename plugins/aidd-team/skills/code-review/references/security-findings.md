# Security findings

Load this when a review traces untrusted input, or when the security engineer reviews a change. It says what counts as a security finding, how severe it is, and what the report covers.

## What makes a finding

A security finding names all six parts. Each comes from the code, with its `file:line`:

| Part | The question it answers |
| --- | --- |
| Actor | Who has less trust than the code assumes: an anonymous caller, another tenant, a user without the role, or input from a file, a queue, or a model |
| Input | What that actor controls, and where it enters |
| Control | The check meant to stop it, or the place where one is missing |
| Boundary | What the actor crosses: a tenant, a role, a process, the network, or a privilege level |
| Impact | What the actor gets: data, an action, code execution, or another account |
| Proof | What shows it: the path from input to sink, a failing test, or the line the control misses |

A note that misses a part is a **hardening note**, never a finding. That includes a missing best practice with no path to impact, a gap another layer already blocks, and a weakness only a trusted actor can reach. List hardening notes after the findings, with no severity, so they never compete with a real one.

## Severity

Rank by the impact the proof shows, never by the impact the bug class could have.

| Severity | The impact shown |
| --- | --- |
| Critical | An actor with no credentials gets code execution, the whole data store, or another person's account |
| High | A control is defeated completely for some actor: authorization bypassed, another tenant's data read or changed, a secret exposed |
| Medium | A control is weakened, but the attack needs a condition the actor does not control, or it reaches limited data |
| Low | A real weakness with a small impact, or one that needs another bug first |

A severity never rises for attention or for a famous bug class. When the impact depends on a fact the proof lacks, use the third outcome below.

## Three outcomes

- **Confirmed:** every part is shown, so it gets a severity.
- **Needs validation:** the deciding fact is outside the repository, such as a proxy's rule, a cloud permission, or a deployed header. Name that one fact, say who owns it, and give the check that settles it. It gets no severity until then.
- **Refuted:** the `file:line` that blocks the path, a check that already runs, or a test that shows the path is safe. A refuted finding stays in its own list, with the evidence, so a person can restore it.

## Search the siblings

After a Critical or High finding, find the root cause, then search every sibling path for it before you report. Siblings are other handlers of the same resource, its batch, export, import, and admin paths, older versions of an endpoint, retries, and error paths. Report each sibling as its own finding, or say that you checked it and where.

## Stay inside the repository

Review the code, its tests, and its configuration. Never send review traffic to a deployed or shared service, and never use a real account or real data. When a proof needs a running system, write the test the verifier would run, or mark the finding "needs validation".

## Say what you covered

End the report with what you read and what you skipped: the paths, the commits, and the kinds of check. Never call a change or a system "secure" or "clean". Say instead which classes of issue you checked, on which paths, and that you found none there.
