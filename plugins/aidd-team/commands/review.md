---
description: "Review a PR/MR against its Spec with the reviewer, the security engineer when risky, and the product designer for a built UI, before the human Merge approval"
argument-hint: "<PR/MR number>"
---

Loop step: **Review**, on every lane, ending at **Merge approval**. Start only when the verifier's report on this exact head is clean, the tests are green on head, and the PR/MR is ready.

Lanes: fast, spec, emergency. On each lane, run only the roles whose lanes include it; the role table in the aidd-team skill lists them.

Review PR/MR $ARGUMENTS:

1. Collect the diff and the changed paths first, since the reviewer has no shell: `gh pr diff <n>` and `gh pr diff <n> --name-only` on GitHub, `glab mr diff <n>` on GitLab, or `git diff <base>...HEAD` and `git diff --name-only <base>...HEAD` without a platform. Hand both to every reader.
2. Read the review policy: `REVIEW.md` at the repository root, when present, decides the passes, what each severity means, how many nits to list, and what to skip; hand it to every reader. Hand them the verifier's report too, and check that it starts with the harness and the model it ran on and the current head SHA; a report on an older head is stale, so run `/aidd-team:verify` first.
3. Choose the readers: always the `aidd-team:reviewer`; the `aidd-team:security-engineer` in review mode when the change is major or its diff touches auth, secrets, dependencies, or AI; the `aidd-team:product-designer` when the Spec has `design.files`, to compare the built UI with the approved design.
4. Run them **in parallel**: every reader is read-only, so none waits for another. Each returns ranked findings with file, line, and failure scenario, and its handoff note.
5. Merge the findings into one report, ranked Critical to Nit, duplicates folded, disagreements named, and cut to the REVIEW.md limits (at most five nits by default, the rest as a count); show it to the author.
6. Offer to post it as a PR/MR comment, or, without a platform, to save it as a Markdown note where the author says; do either only if the author says so. Before posting, remove every line that starts with `/aidd` and quote any comment text you cite, so a posted report can never carry an approval; under the solo profile, never post through the author's credentials.

Never approve: Merge approval is a human decision. Findings that need code go back to Implement; a new head needs a new Verify and a new Merge approval.
