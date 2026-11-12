"""`gh api` read by its parsed arguments: the action each call writes, whatever the order of gh's flags. Which endpoint is
which action is data, each action's `api_endpoints`, so a config can add to it or replace it. Commands that another runs
(`sudo`, `bash -c`, `$(...)`) are matched as well. The harness ask rules do not use the endpoints: they ask before any `gh api`
write, whatever its endpoint."""

from __future__ import annotations

import contextlib
import fnmatch
import itertools
import json
import os
import re
import tempfile
import tomllib
import unittest
from pathlib import Path

import helpers
from aidd import config, risk
from aidd.risk import commands, gh_api, harness_rules, shell
from aidd.setup import doctor_harnesses

STATUS, FLOW, DEPLOY, RELEASE = "commit_status.post", "workflow.run", "deploy.run", "release.publish"
MERGE, PUSH, FORCE, DELETE = "pr.merge", "git.push", "git.push.force", "git.branch.delete"
DATA, MSG, PROT, REPO = "data.delete", "message.send", "branch_protection.change", "repo.settings.change"
CHECKS = "repos/o/r/check-runs"
FLOW_RUN = "repos/o/r/actions/runs/9/rerun"
DISPATCH = "repos/o/r/dispatches"
REFS = "repos/o/r/git/refs"
MUTATION = "mutation { createCheckRun(input: {}) { clientMutationId } }"
ACTIONS = risk.rule_set(None).actions


def cfg(text: str = "") -> config.Config:
    return config.load_text('aidd_version: "1.0.0"\nprofile: solo\n' + text)


def lowered(*, ask: tuple[str, ...] = ()) -> str:
    """A config that lowers every built-in action with `api_endpoints` to `report`, except those in `ask`, and a push to the
    default and a shared branch with it, so the harnesses have no `gh api` write to ask for."""
    names = [a for a, spec in risk.builtin()["actions"].items() if spec.get("api_endpoints") and a != "git.push"]
    rules = "".join(f"    - {{action: {a}, level: {'ask' if a in ask else 'report'}}}\n" for a in names)
    return "risks:\n  rules:\n" + rules + "    - {action: git.push, branch: default, level: report}\n    - {action: git.push, branch: shared, level: report}\n"


@contextlib.contextmanager
def _in_a_repo():
    """`aidd risk` runs from a repository's root, and a source package (the sdist) has none: run in a fresh one."""
    with tempfile.TemporaryDirectory() as d:
        helpers.git(d, "init", "-q", "-b", "main")
        with contextlib.chdir(d):
            yield


class ParsedCalls(unittest.TestCase):
    """The parser alone: the actions of one call, each flag order and form."""

    def test_each_write_form_and_each_read(self):
        cases = [
            # The method, in every form gh reads, before or after the endpoint.
            (f"gh api -X POST {CHECKS}", [STATUS]),
            (f"gh api {CHECKS} -X POST", [STATUS]),
            (f"gh api {CHECKS} -XPOST", [STATUS]),
            (f"gh api {CHECKS} -X=POST", [STATUS]),
            (f"gh api {CHECKS} --method POST", [STATUS]),
            (f"gh api {CHECKS} --method=POST", [STATUS]),
            (f"gh api {CHECKS} -X post", [STATUS]),  # gh sends the method as typed, so a case slip is still a write
            (f"gh api {CHECKS} -iXPATCH", [STATUS]),  # a short flag in a run of them
            (f"gh api {CHECKS} -X GET -X PATCH", [STATUS]),  # the last method wins
            (f"gh api {CHECKS} -X DELETE", []),  # a method the entry does not name
            (f"gh api {CHECKS} --method '$M'", [STATUS]),  # a method aidd cannot read is no read
            (f"gh api {CHECKS} -X POST -H 'Accept: application/json' --silent", [STATUS]),
            ("gh api repos/o/r/statuses/abc -X POST", [STATUS]),
            ("gh api repos/o/r/statuses/abc --method=POST -f state=success", [STATUS]),
            ("/usr/bin/gh api -X POST repos/o/r/statuses/abc", []),  # `shell.wrapped` hands over a program by its path as `gh`
            ("GH_TOKEN=x gh api -X POST repos/o/r/statuses/abc", [STATUS]),
            ("A=1 B=2 gh api -X POST repos/o/r/statuses/abc", [STATUS]),  # each setting before the program
            ("gh api /repos/o/r/statuses/abc?x=1 -X POST", [STATUS]),
            ("gh api https://api.github.com/repos/o/r/statuses/abc -XPOST", [STATUS]),
            (f"gh api -- {CHECKS} -f x=1", []),  # after `--` all is positional, so no flag is read
            # A field or an input implies POST, whichever flag, whichever place.
            (f"gh api {CHECKS} -f name=x", [STATUS]),
            (f"gh api {CHECKS} -fname=x", [STATUS]),
            (f"gh api {CHECKS} -F name=x", [STATUS]),
            (f"gh api {CHECKS} --field name=x", [STATUS]),
            (f"gh api {CHECKS} --field=name=x", [STATUS]),
            (f"gh api {CHECKS} --raw-field name=x", [STATUS]),
            (f"gh api {CHECKS} --input body.json", [STATUS]),
            (f"gh api {CHECKS} --input=body.json", [STATUS]),
            (f"gh api -f name=x -H 'A: b' {CHECKS}", [STATUS]),
            (f"gh api --raw-field name=x {CHECKS}", [STATUS]),
            # The endpoints the data names.
            (f"gh api {FLOW_RUN} -X POST", [FLOW]),
            (f"gh api {FLOW_RUN}-failed-jobs --method=POST", [FLOW]),
            ("gh api -X POST repos/o/r/actions/jobs/7/rerun", [FLOW]),
            ("gh api -X POST repos/o/r/check-suites/3/rerequest", [FLOW]),  # a re-run, as `gh run rerun` is
            (f"gh api {DISPATCH} -f event_type=build", [FLOW]),
            ("gh api repos/o/r/actions/workflows/ci.yml/dispatches -XPOST", [FLOW]),
            ("gh api -X PUT repos/o/r/pulls/5/merge -f merge_method=squash", [MERGE]),
            ("gh api repos/o/r/pulls/5/merge --method=PUT", [MERGE]),
            ("gh api repos/o/r/releases -f tag_name=v1", [RELEASE]),
            ("gh api -XPOST repos/o/r/releases", [RELEASE]),
            ("gh api -X PATCH repos/o/r/releases/7 -F draft=false", [RELEASE]),  # a draft goes public
            ("gh api -X PATCH repos/o/r/releases/7 -F draft=true", []),
            ("gh api -X DELETE repos/o/r/releases/7", [DATA]),
            ("gh api -X DELETE repos/o/r/releases/7/reactions/1", []),  # not the release
            ("gh api -X DELETE repos/o/r/releases/assets/3", [DATA]),  # as `gh release delete-asset` is
            ("gh api -X DELETE repos/o/r/releases/assets/3/reactions/1", []),
            # An endpoint built from expansions with some text of its own matches by that text.
            ('gh api -X DELETE "repos/$SLUG"', [DATA]),
            ('gh api -X DELETE "repos/${SLUG}"', [DATA]),
            ('gh api -X DELETE "repos/$O/$R"', [DATA]),
            ('gh api -X DELETE "repos/$O/$R/issues/1"', []),
            ("gh api -X DELETE repos/$O/$R/issues", []),
            ("gh api -X PUT repos/$O/$R/pulls/$N/merge", [MERGE]),
            ('gh api -X DELETE "repos/$SLUG/releases/7"', [DATA]),
            ("gh api -X PATCH repos/o/r/releases/assets/3 --input a.json", []),
            ("gh api -X PATCH repos/o/r/releases/7 -F draft=`echo false`", [RELEASE]),
            ("gh api -X PATCH repos/o/r/releases/7 -F draft=@d.txt", [RELEASE]),
            ('gh api -X PATCH repos/o/r/releases/7 -F draft="$(cat d)"', [RELEASE]),
            ("gh api -X PATCH repos/o/r/issues/comments/9 -f body=x", [MSG]),  # an edit sends what `gh pr comment --edit-last` does
            ("gh api -X PATCH repos/o/r/pulls/comments/9 -f body=x", [MSG]),
            ("gh api repos/o/r/issues/comments/9", []),
            ("gh api graphql -f query='mutation { updateIssueComment(input: {}) { x } }'", [STATUS, MSG]),
            ("gh api -X POST repos/o/r/actions/runs/9/pending_deployments -F state=approved", [DEPLOY]),
            # A dispatch that names a deploy or a release, in any case, is that too.
            (f"gh api {DISPATCH} -f event_type=Deploy", [FLOW, DEPLOY]),
            (f"gh api {DISPATCH} -f event_type=dEPLOY", [FLOW, DEPLOY]),
            (f"gh api {DISPATCH} -f event_type=RelEase", [FLOW, RELEASE]),
            (f"gh api {DISPATCH} -XPOST -f event_type=PubLish", [FLOW, RELEASE]),
            ("gh api repos/o/r/actions/workflows/Deploy.yml/dispatches -f ref=main", [FLOW, DEPLOY]),
            # Each glob of release.publish and deploy.run is held by a case: one deleted from the data fails here.
            ("gh api repos/o/r/actions/workflows/release.yml/dispatches -f ref=main", [FLOW, RELEASE]),
            ("gh api repos/o/r/actions/workflows/publish.yml/dispatches -f ref=main", [FLOW, RELEASE]),
            (f"gh api {DISPATCH} -f event_type=release", [FLOW, RELEASE]),
            (f"gh api {DISPATCH} -f event_type=publish", [FLOW, RELEASE]),
            ("gh api repos/o/r/actions/workflows/deploy.yml/dispatches -f ref=main", [FLOW, DEPLOY]),
            (f"gh api {DISPATCH} -f event_type=deploy", [FLOW, DEPLOY]),
            # A dispatch whose target aidd cannot read may be either; an `@` inside a value is no file.
            ("gh api repos/o/r/actions/workflows/$WF/dispatches -f ref=main", [FLOW, DEPLOY, RELEASE]),
            ('gh api repos/o/r/actions/workflows/"$WF"/dispatches -X POST', [FLOW, DEPLOY, RELEASE]),
            (f"gh api {DISPATCH} -f event_type=$TYPE", [FLOW, DEPLOY, RELEASE]),
            (f"gh api {DISPATCH} --input body.json", [FLOW, DEPLOY, RELEASE]),
            (f"gh api {DISPATCH} -F payload=@body.json", [FLOW, DEPLOY, RELEASE]),
            (f"gh api {DISPATCH} -f event_type=build -f 'inputs[email]=a@b.c'", [FLOW]),
            (f"gh api {DISPATCH} -f event_type=a@b", [FLOW]),
            ("gh api -X PATCH repos/o/r/releases/7 --input publish.json", [RELEASE]),  # the body may publish it
            ("gh api -X PATCH repos/o/r/releases/7 -F draft=$D", [RELEASE]),
            ("gh api -X PATCH repos/o/r/releases/7 -f draft=true", []),
            # What `gh repo delete` and `gh release delete` do, and the comments and reviews `gh pr comment` and `gh pr review` send.
            ("gh api -X DELETE repos/o/r", [DATA]),
            ("gh api repos/o/r -X DELETE -f x=y", [DATA]),
            ("gh api --method=DELETE /repos/o/r", [DATA]),
            ("gh api -XDELETE https://api.github.com/repos/o/r", [DATA]),
            ("gh api -X DELETE repos/{owner}/{repo}", [DATA]),
            ("gh api -X DELETE repos/$OWNER/$REPO", [DATA]),
            ("gh api -X DELETE repos/o/r/issues/comments/1", []),  # not the repository: it keeps its own level
            ("gh api -X DELETE repos/o/r/issues/1", []),
            ("gh api -X DELETE repos/o/r/branches/main", []),
            ("gh api -X DELETE repos/o", []),
            ("gh api repos/o/r", []),
            ("gh api graphql -f query='mutation { deleteRepository(input: {}) { clientMutationId } }'", [STATUS, DATA]),
            ("gh api graphql -f query='mutation { r: deleteRepository (input: {}) { x } }'", [STATUS, DATA]),
            ("gh api repos/o/r/issues/5/comments -f body=hi", [MSG]),
            ("gh api -X POST repos/o/r/pulls/5/comments -f body=hi", [MSG]),
            ("gh api -X POST repos/o/r/commits/abc/comments -f body=hi", [MSG]),
            ("gh api repos/o/r/issues/5/comments", []),
            ("gh api -X POST repos/o/r/pulls/5/reviews -f event=APPROVE", [MSG]),
            ("gh api repos/o/r/pulls/5/reviews -f body=x -f event=REQUEST_CHANGES", [MSG]),
            ("gh api -X POST repos/o/r/pulls/5/reviews/9/events -f event=APPROVE", [MSG]),
            ("gh api repos/o/r/pulls/5/reviews", []),
            ("gh api graphql -f query='mutation { addComment(input: {}) { clientMutationId } }'", [STATUS, MSG]),
            ("gh api graphql -f query='mutation { addPullRequestReview(input: {}) { clientMutationId } }'", [STATUS, MSG]),
            # Branch protection and rulesets: removing or changing one asks.
            ("gh api -X DELETE repos/o/r/branches/main/protection", [PROT]),
            ("gh api -X PUT repos/o/r/branches/main/protection -F enforce_admins=false", [PROT]),
            ("gh api repos/o/r/branches/main/protection --method=PATCH -f x=y", [PROT]),
            ("gh api -X DELETE repos/o/r/branches/main/protection/required_pull_request_reviews", [PROT]),
            ("gh api -X DELETE repos/o/r/rulesets/5", [PROT]),
            ("gh api -X PUT repos/o/r/rulesets/5 --input rules.json", [PROT]),
            ("gh api -X PATCH orgs/o/rulesets/5 -f enforcement=disabled", [PROT]),
            ("gh api repos/o/r/branches/main/protection", []),
            ("gh api repos/o/r/rulesets", []),
            ("gh api repos/o/r/rulesets/5 -X GET", []),
            ("gh api graphql -f query='mutation { deleteBranchProtectionRule(input: {}) { clientMutationId } }'", [STATUS, PROT]),
            ("gh api graphql -f query='mutation { updateBranchProtectionRule(input: {}) { x } }'", [STATUS, PROT]),
            ("gh api graphql -f query='mutation { createRepositoryRuleset(input: {}) { x } }'", [STATUS, PROT]),
            ("gh api graphql -f query='mutation { deleteRepositoryRuleset(input: {}) { x } }'", [STATUS, PROT]),
            # A repository's settings: visibility, name, default branch, archive state. Your own profile is no repository.
            ("gh api -X PATCH repos/o/r -f private=false", [REPO]),
            ("gh api repos/o/r --method=PATCH -F archived=true", [REPO]),
            ("gh api -XPATCH repos/o/r --input settings.json", [REPO]),
            ("gh api -X PATCH repos/o/r -f query=@q.graphql", [REPO]),
            ("gh api -X PATCH https://api.github.com/repos/o/r -f name=new", [REPO]),
            ("gh api -X PATCH /repos/o/r/ -f default_branch=dev", [REPO]),
            ("gh api -X PATCH repos/{owner}/{repo} -f visibility=public", [REPO]),
            ('gh api -X PATCH "repos/$SLUG" -f private=false', [REPO]),
            ("gh api -X PATCH repos/o/r/issues/5 -f state=closed", []),
            ("gh api -X PATCH repos/o/r/branches/main -f a=b", []),
            ("gh api -X POST repos/o/r/transfer -f new_owner=x", [REPO]),  # a transfer is harder to undo than a rename
            ("gh api repos/o/r/transfer -f new_owner=x", [REPO]),
            ("gh api --method=POST repos/o/r/transfer --input t.json", [REPO]),
            ('gh api -X POST "repos/$SLUG/transfer" -f new_owner=x', [REPO]),
            ("gh api -X POST repos/o/r/transfer/", [REPO]),
            ("gh api repos/o/r/transfer", []),
            ("gh api -X GET repos/o/r/transfer", []),
            ("gh api -X POST repos/o/r/transfers -f a=b", []),
            ("gh api -X POST repos/o/r/issues/5/transfer -f a=b", []),
            ("gh api -X PATCH user -f name=Ada", []),  # only the person's own profile
            ("gh api -X PATCH user/emails -f a=b", []),
            ("gh api -X PUT repos/o/r -f private=false", []),  # the API has no PUT on a repository
            ("gh api repos/o/r", []),
            ("gh api -X GET repos/o/r -f per_page=1", []),
            ("gh api graphql -f query='mutation { updateRepository(input: {}) { clientMutationId } }'", [STATUS, REPO]),
            ("gh api graphql -f query='mutation { r: updateRepository (input: {}) { x } }'", [STATUS, REPO]),
            ("gh api graphql -f query='mutation { archiveRepository(input: {}) { x } }'", [STATUS, REPO]),
            ("gh api graphql -f query='mutation { unarchiveRepository(input: {}) { x } }'", [STATUS, REPO]),
            ("gh api graphql -f query='mutation { updateRepositoryRuleset(input: {}) { x } }'", [STATUS, PROT]),  # a ruleset, not a repository
            ('gh api graphql -f query=\'query { repository(owner: "o", name: "r") { isArchived } }\'', []),
            # Git's refs: a branch moves, a forced move is forced, a ref is deleted, a file or a merge lands on a branch.
            (f"gh api -X PATCH {REFS}/heads/main -f sha=abc", [PUSH]),
            (f"gh api {REFS}/heads/main --method=PATCH -F force=false", [PUSH]),
            (f"gh api -X PATCH {REFS}/heads/main -f sha=abc -F force=true", [PUSH, FORCE]),
            (f"gh api {REFS}/heads/main -XPATCH -f force=true -f sha=abc", [PUSH, FORCE]),
            (f"gh api -X PATCH {REFS}/heads/main --input body.json", [PUSH, FORCE]),  # the body may force it
            (f"gh api {REFS} -f ref=refs/heads/x -f sha=abc", [PUSH]),
            (f"gh api -X POST {REFS}", [PUSH]),
            (f"gh api -X DELETE {REFS}/heads/x", [DELETE]),
            (f"gh api {REFS}/tags/v1 --method DELETE", [DELETE]),
            (f"gh api {REFS}/heads/x -X $M", [PUSH, DELETE]),  # a method aidd cannot read may be any
            (f"gh api {REFS}/heads/main", []),
            (f"gh api -X PUT {REFS}/heads/main", []),  # the API has no PUT on a ref
            ("gh api -X POST repos/o/r/git/ref/heads/main", []),  # the singular `ref` is a read path
            ("gh api -X PUT repos/o/r/contents/a.txt -f message=m -f content=eA==", [PUSH]),
            ("gh api repos/o/r/contents/a.txt --method=DELETE -f message=m -f sha=abc", [PUSH]),
            ("gh api repos/o/r/contents/a.txt", []),
            ("gh api repos/o/r/merges -f base=main -f head=feat", [PUSH]),
            ("gh api repos/o/r/merges", []),
            # GraphQL: a mutation, or a query aidd cannot read, writes; a query in the command reads.
            ('gh api graphql -f query="mutation { x }"', [STATUS]),
            ('gh api -f query="mutation { x }" graphql', [STATUS]),
            ("gh api graphql --field query='mutation($id: ID!) { x }'", [STATUS]),
            (f"gh api graphql -f query='{MUTATION}'", [STATUS]),
            ("gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'", [STATUS, MERGE]),
            ("gh api graphql -f query='mutation { updateRef(input: {}) { clientMutationId } }'", [STATUS, PUSH]),
            ("gh api https://api.github.com/graphql -f query='mutation { x }'", [STATUS]),
            ("gh api graphql -X GET -f query='mutation { x }'", [STATUS]),  # the query decides, not the method
            # A query the shell builds in part is unreadable, whatever its text shows; GraphQL's own `$id` in single quotes is text.
            ('gh api graphql -f query="$OP { mergePullRequest(input: {}) { x } }"', [STATUS, MERGE]),
            ('gh api graphql -f query="${Q:-}"', [STATUS]),
            ('gh api graphql -f query="$Q$R"', [STATUS]),
            ("gh api graphql -f query=$'\\x6dutation { x }'", [STATUS]),
            ('gh api graphql -f query="query { $FIELD }"', [STATUS]),
            ('gh api graphql -f query="{ viewer { login } } $(cat more.graphql)"', [STATUS]),
            ("gh api graphql -f query='query($id: ID!) { node(id: $id) { id } }' -f id=$ID", []),  # the variable is another field's
            ("gh api graphql -f query='query($id: ID!) { node(id: $id) { id } }' -F id=1", []),
            ('gh api graphql -f query="query(\\$id: ID!) { node(id: \\$id) { id } }" -F id=1', []),  # escaped, so GraphQL's own
            # A query from a file, standard input, or a variable is never read: it is unreadable, so a write.
            ("gh api graphql -f query=@q.graphql", [STATUS]),
            ("gh api graphql -F query=@q.graphql", [STATUS]),
            ("gh api graphql --raw-field query=@q.graphql", [STATUS]),
            ("gh api graphql -F query=@-", [STATUS]),
            ("gh api graphql --input q.json", [STATUS]),
            ("gh api --input=q.json graphql", [STATUS]),
            ("gh api graphql --input -", [STATUS]),
            ("gh api graphql -f query=$QUERY", [STATUS]),
            ("gh api graphql -f query=${QUERY}", [STATUS]),
            ('gh api graphql -f query="$(cat q.graphql)"', [STATUS]),
            ("gh api graphql -f query=`cat q.graphql`", [STATUS]),
            ("gh api graphql -f query='query($owner: String!) { repository(owner: $owner) { id } }' -f owner=o", []),
            ("gh api graphql -f query='{ viewer { login } }'", []),
            ("gh api graphql -f owner=o", []),  # no query: nothing to run
            ("gh api graphql", []),
            # Reads: a GET or HEAD that sends nothing, and a write to an endpoint no action names.
            (f"gh api {CHECKS}", []),
            ("gh api repos/o/r/commits/abc/check-runs", []),
            ("gh api repos/o/r/commits/abc/statuses", []),
            ("gh api repos/o/r/commits/abc/status", []),
            ("gh api repos/o/r/releases", []),
            ("gh api repos/o/r/releases/latest", []),
            ("gh api repos/o/r/pulls/5/merge", []),
            (f"gh api {CHECKS} -X GET", []),
            (f"gh api {CHECKS} --method=get", []),
            (f"gh api {CHECKS} -XHEAD", []),
            (f"gh api {CHECKS} -X GET -f per_page=1", []),  # explicit GET: gh sends the fields as a query string
            (f"gh api {CHECKS} --paginate --jq '.check_runs[].name'", []),
            (f"gh api {CHECKS} -H 'Accept: application/json' -q .total_count", []),
            (f"gh api {DISPATCH} -X GET", []),
            ("gh api user", []),
            ("gh api user -f name=x", []),
            ("gh api repos/o/r/issues -f title=x -X POST", []),
            ("gh api repos/o/r/pulls/1 --method PATCH -f state=closed", []),
            # Not a `gh api` call at all.
            (f"gh pr view {CHECKS}", []),
            (f"echo gh api {CHECKS} -X POST", []),
            ("gh", []),
            ("", []),
            ("gh api 'repos/o/r/statuses/abc -X POST", [STATUS]),  # an open quote: split on spaces
        ]
        for command, want in cases:
            with self.subTest(command=command):
                self.assertEqual(sorted(gh_api.gh_api_actions(ACTIONS, command)), sorted(want))

    def test_an_endpoint_the_shell_builds_whole_matches_every_entry_its_method_allows(self):
        put = {PUSH, MERGE, PROT, FLOW, DEPLOY, RELEASE}
        delete = {DELETE, PUSH, DATA, PROT, FLOW, DEPLOY, RELEASE}
        post = {PUSH, STATUS, MSG, FLOW, DEPLOY, RELEASE, REPO}
        cases = [
            ('gh api -X PUT "$EP"', put),
            ("gh api -X PUT ${EP}", put),
            ("gh api -X PUT $(echo x)", put),
            ('gh api -X PUT "`echo x`"', put),
            ("gh api --method=PUT $EP -f a=b", put),
            ('gh api -X PUT "$A$B"', put),
            ('gh api -X PUT "${A}/${B}"', put),
            ('gh api -X PUT "$A/$B"', put),
            ('gh api -X PUT "${EP:-x}"', put),
            ('gh api -X DELETE "${EP:-x}"', delete),
            ('gh api "$A$B" -f a=b', post),
            ('gh api "$A/$B"', set()),
            ('gh api -X DELETE "$EP"', delete),
            ('gh api "$EP" -f a=b', post),
            (
                'gh api -X $M "$EP"',
                {a for a, spec in ACTIONS.items() if any(not gh_api.entry_parts(e)[1].startswith("graphql#") for e in spec.get("api_endpoints", []))},
            ),
            # A read stays quiet, and an endpoint with a variable inside still matches by its text.
            ('gh api -X GET "$EP"', set()),
            ('gh api "$EP"', set()),
            ('gh api "$EP" -X HEAD', set()),
            ("gh api -X PUT repos/$O/$R/pulls/1/merge", {MERGE}),
            ("gh api -X PUT repos/$O/$R/issues/1", set()),
            ("gh api repos/$O/$R/issues/1", set()),
        ]
        for command, want in cases:
            with self.subTest(command=command):
                got = set(gh_api.gh_api_actions(ACTIONS, command))
                self.assertEqual(got, want)

    def test_a_query_file_is_never_opened(self):
        """A named pipe blocks a reader for good, so a test that returns shows no file was opened."""
        if not hasattr(os, "mkfifo"):
            self.skipTest("no named pipes here")
        with tempfile.TemporaryDirectory() as tmp:
            os.mkfifo(Path(tmp, "q.graphql"))
            os.symlink("/dev/zero", Path(tmp, "link.graphql"))
            for name in ("q.graphql", "link.graphql", "."):
                with self.subTest(name=name):
                    self.assertEqual(risk.command_level(risk.rule_set(None), f"gh api graphql -F query=@{name}", cwd=tmp)["level"], "ask")

    def test_no_data_no_action(self):
        self.assertEqual(gh_api.gh_api_actions({"x.y": {"commands": ["gh api*"]}}, f"gh api -X POST {CHECKS}"), [])

    def test_the_ref_a_call_moves(self):
        cases = [
            (f"gh api -X PATCH {REFS}/heads/main -f sha=a", ("branch", "main")),
            (f"gh api -X PATCH {REFS}/heads/feat/x -f sha=a", ("branch", "feat/x")),
            (f"gh api {REFS} -f ref=refs/heads/feat -f sha=a", ("branch", "feat")),
            (f"gh api {REFS} -f ref=refs/tags/v1 -f sha=a", ("tag", "v1")),
            (f"gh api -X PATCH {REFS}/tags/v1 -f sha=a", ("tag", "v1")),
            (f"gh api -X PATCH {REFS}/heads/$B -f sha=a", ("default", "")),  # a ref aidd cannot read may be the default
            (f"gh api -X PATCH {REFS}/heads/{{branch}} -f sha=a", ("default", "")),  # gh's current branch
            (f"gh api -X PATCH {REFS} -f sha=a", ("default", "")),
            ("gh api -X PUT repos/o/r/contents/a.txt -f branch=feat -f message=m", ("branch", "feat")),
            ("gh api -X PUT repos/o/r/contents/a.txt -f message=m", ("default", "")),  # no branch: the default one
            ("gh api repos/o/r/merges -f base=feat -f head=x", ("branch", "feat")),
            # The call as typed: a quoted value that holds a ref is no endpoint.
            (f"gh api -X PATCH -f 'x=y git/refs/heads/feature' {REFS}/heads/main", ("branch", "main")),
            ("gh api user", ("default", "")),
        ]
        for command, want in cases:
            with self.subTest(command=command):
                self.assertEqual(gh_api.ref_target(command), want)
        self.assertIsNone(gh_api.ref_target("git push origin main"))


class Wrapped(unittest.TestCase):
    """A command another runs, through `env`, `sudo`, a shell's `-c`, a group, a loop, a substitution, or a prefix such as
    `timeout`, is matched as the inner command."""

    def actions(self, line: str) -> list[str]:
        return sorted({a["action"] for a in risk.command_level(risk.rule_set(None), line)["actions"]})

    def test_a_wrapper_reads_the_inner_command(self):
        call = f"gh api {CHECKS} -XPOST"  # a form the patterns miss, so only the parser asks
        merge = "gh api -X PUT repos/o/r/pulls/1/merge"
        cases = [
            (f"env {call}", [STATUS]),
            (f"env FOO=1 BAR=2 {call}", [STATUS]),
            (f"env -i FOO=1 {call}", [STATUS]),
            (f"env -u HOME {call}", [STATUS]),
            (f"env -S '{call}'", [STATUS]),
            (f"env -- {call}", [STATUS]),
            (f"/usr/bin/env {call}", [STATUS]),
            (f"sudo {call}", [STATUS]),
            (f"sudo -u root {call}", [STATUS]),
            (f"sudo -nu root {call}", [STATUS]),
            (f"sudo -nuroot {call}", [STATUS]),
            (f"sudo -E -H -u root --preserve-env {call}", [STATUS]),
            (f"sudo --user=root {call}", [STATUS]),
            (f"sudo -- {call}", [STATUS]),
            (f"FOO=1 sudo env BAR=2 {call}", [STATUS]),
            (f"bash -c '{call}'", [STATUS]),
            (f'sh -c "{call}"', [STATUS]),
            (f"zsh -lc '{call}'", [STATUS]),
            (f"bash -e -c '{call}' arg0", [STATUS]),
            (f"sudo bash -c '{call}'", [STATUS]),
            (f"env sh -c 'make && {call}'", [STATUS]),
            (f"bash -c \"sh -c '{call}'\"", [STATUS]),
            (f"make && sudo {call}", [STATUS]),
            ("sudo gh api graphql -f query=$Q", [STATUS]),
            ('sudo gh api graphql -f "query=$OP { x }" -f "n=it\'s$Y"', [STATUS]),
            ('sudo gh api graphql -f "query=it\'s$Q"', [STATUS]),
            ('env sh -c \'gh api graphql -f "query=a\\"b$Q"\'', [STATUS]),
            ("sudo gh api graphql -f query='query($id: ID!) { node(id: $id) { id } }' -F id=1", []),
            ("bash -c 'gh api repos/o/r/dispatches -f event_type=RelEase'", [FLOW, RELEASE]),
            ("env gh api -X PATCH repos/o/r/git/refs/heads/x -f sha=a", [PUSH]),
            # The commands the patterns name, run through a wrapper.
            ("bash -c 'git push --force origin main'", [PUSH, FORCE]),
            ("sudo git push --force origin main", [PUSH, FORCE]),
            ("sudo -nu root git push --force origin main", [PUSH, FORCE]),
            ("env FOO=1 git push --force origin main", [PUSH, FORCE]),
            ("(git push --force origin main)", [PUSH, FORCE]),
            ("{ git push --force origin main; }", [PUSH, FORCE]),
            ("npm test && (cd x && git push --force origin main)", [PUSH, FORCE]),
            ("sudo rm -rf build", ["data.delete"]),
            # Groups, keywords, and loops.
            (f"({merge})", [MERGE]),
            (f"( {merge} )", [MERGE]),
            (f"for n in 1 2; do {merge}; done", [MERGE]),
            (f"while true; do {merge}; done", [MERGE]),
            (f"if {merge}; then echo ok; fi", [MERGE]),
            (f"if true; then {merge}; else echo no; fi", [MERGE]),
            (f"! {merge}", [MERGE]),
            # Substitutions, outside single quotes.
            (f"echo $({merge})", [MERGE]),
            (f'echo "$({merge})"', [MERGE]),
            (f"echo `{merge}`", [MERGE]),
            (f"echo $(echo $({merge}))", [MERGE]),
            (f"echo $({merge} | cat)", [MERGE]),
            (f"echo '$({merge})'", []),
            (f"echo '{merge}'", []),
            (f"echo \\$({merge})", []),
            # Prefixes that run the rest.
            (f"time {merge}", [MERGE]),
            (f"time -p {merge}", [MERGE]),
            (f"command {merge}", [MERGE]),
            (f"exec {merge}", [MERGE]),
            (f"nohup {merge}", [MERGE]),
            (f"timeout 30 {merge}", [MERGE]),
            (f"timeout -s KILL -k 5 30 {merge}", [MERGE]),
            (f"timeout --signal=KILL 30 {merge}", [MERGE]),
            (f"eval '{merge}'", [MERGE]),
            (f"eval {merge}", [MERGE]),
            (f'eval "echo hi; {merge}"', [MERGE]),
            (f"echo 1 | xargs {merge}", [MERGE]),
            (f"echo 1 | xargs -n1 -P 4 {merge}", [MERGE]),
            ("echo 1 | xargs -I{} gh api -X PUT repos/o/r/pulls/{}/merge", [MERGE]),
            (f"time sudo -nu root timeout 30 nohup bash -c '{merge}'", [MERGE]),
            # The wrappers an agent uses by habit: their options, in a run, with a value, or after the command word.
            (f"nice {merge}", [MERGE]),
            (f"nice -n 5 {merge}", [MERGE]),
            (f"nice -5 {merge}", [MERGE]),
            (f"nice --adjustment=5 {merge}", [MERGE]),
            (f"/usr/bin/time -o out.txt {merge}", [MERGE]),
            (f"/usr/bin/time -p -f %e {merge}", [MERGE]),
            (f"exec -a name {merge}", [MERGE]),
            (f"command -p {merge}", [MERGE]),
            (f"env --split-string='{merge}'", [MERGE]),
            (f"env -S'{merge}'", [MERGE]),
            (f"env -S '{merge} -f a=b' ls", [MERGE]),
            (f"env -u HOME -S '{merge}'", [MERGE]),
            (f"sudo -nu root -E env X=1 timeout 30 nice -n 3 {merge}", [MERGE]),
            (f"bash -c -- '{merge}'", [MERGE]),
            (f"bash -c -e '{merge}'", [MERGE]),
            (f"bash -lc '{merge}'", [MERGE]),
            (f"sh -ec '{merge}'", [MERGE]),
            (f"bash -o pipefail -c '{merge}'", [MERGE]),
            (f"bash --norc --noprofile -c '{merge}'", [MERGE]),
            (f"bash --rcfile x.sh -c '{merge}'", [MERGE]),
            (f"zsh -c '{merge}' arg0 arg1", [MERGE]),
            (f"echo hi |& {merge}", [MERGE]),
            (f"{merge} &", [MERGE]),
            (f"sleep 1 & {merge}", [MERGE]),
            (f"{merge} 2>&1", [MERGE]),
            (f"{merge} &>/dev/null", [MERGE]),
            (f"{merge} >&2", [MERGE]),
            (f"{merge} 2>&1 | cat", [MERGE]),
            ("gh api -X PUT \\\n  repos/o/r/pulls/1/merge", [MERGE]),
            ("gh api -X PUT repos/o/r/pulls/1/merge \\\n  -f merge_method=squash", [MERGE]),
            ("git push \\\n --force origin main", [PUSH, FORCE]),
            ("bash -c 'git push --force origin main' &", [PUSH, FORCE]),
            # What it does not read, said in SECURITY.md: another wrapper, another shell, a pipe into a shell, or a here-string.
            (f"doas {merge}", []),
            (f"su -c '{merge}'", []),
            (f"fish -c '{merge}'", []),
            (f"ksh -c '{merge}'", []),
            (f"busybox sh -c '{merge}'", []),
            (f"bash <<< '{merge}'", []),
            (f"echo '{merge}' | sh", []),
            (f"diff <({merge}) b", []),
            # A program by its path is read by its name, wrapped or not.
            ("./bin/gh pr merge 12", [MERGE]),
            ("/usr/local/bin/gh pr merge 12", [MERGE]),
            ("~/bin/gh pr merge 12", [MERGE]),
            ("/opt/homebrew/bin/git push --force origin main", [PUSH, FORCE]),
            ("/usr/bin/git push --force origin main", [PUSH, FORCE]),
            ("/usr/bin/terraform apply", ["infra.apply"]),
            ("/usr/bin/npx prisma migrate reset", [DATA]),
            ("FOO=1 ./bin/gh pr merge 12", [MERGE]),
            ("sudo ./bin/gh pr merge 12", [MERGE]),
            ("bash -c './bin/gh pr merge 12'", [MERGE]),
            ("make && /usr/bin/terraform apply", ["infra.apply"]),
            ("/usr/local/bin/gh api -X PUT repos/o/r/pulls/1/merge", [MERGE]),
            ("./bin/gh pr view 12", []),
            ("./bin/gh api repos/o/r/pulls", []),
            ("echo ./bin/gh pr merge 12", []),
            ("ls /usr/bin/gh", []),
            ("./manage.py migrate", ["migration.run.local"]),  # a runner form that names a path still matches as typed
            # A wrapped read, a wrapper with no call inside, and a shell with no script stay `allow`.
            (f"env gh api {CHECKS}", []),
            (f"sudo -u root gh api {CHECKS} -X GET", []),
            (f"bash -c 'gh api {CHECKS}'", []),
            ("env FOO=1", []),
            ("sudo ls", []),
            ("sudo", []),
            ("time", []),
            ("timeout", []),
            ("timeout 30", []),
            ("xargs", []),
            ("bash script.sh", []),
            ("bash -c", []),
            ("(", []),
            ("echo done)", []),
            (f"echo '{call}'", []),
            ("echo 'git push --force'", []),
            ("bash -c 'git status'", []),
        ]
        for line, want in cases:
            with self.subTest(line=line):
                got = self.actions(line)
                if FORCE in want:
                    self.assertTrue({PUSH, FORCE} <= set(got), got)
                else:
                    self.assertEqual(got, sorted(want))

    def test_a_program_by_its_path_lists_each_action_once(self):
        for line in (
            "./bin/gh pr merge 12",
            "/usr/local/bin/gh api -X PUT repos/o/r/pulls/1/merge",
            "/usr/bin/gh api -X PUT repos/o/r/pulls/1/merge -f merge_method=squash",
            "/opt/homebrew/bin/git push --force origin main",
            "sudo /usr/bin/gh api -X PUT repos/o/r/pulls/1/merge",
            "FOO=1 /usr/bin/terraform apply",
        ):
            with self.subTest(line=line):
                found = [(a["action"], a["branch"]) for a in risk.command_level(risk.rule_set(None), line)["actions"]]
                self.assertEqual(len(found), len(set(found)), found)
        merge = risk.command_level(risk.rule_set(None), "/usr/bin/gh api -X PUT repos/o/r/pulls/1/merge")["actions"]
        self.assertEqual([a["action"] for a in merge], [MERGE])

    def test_a_wrapper_nests_only_so_deep(self):
        line = f"gh api {CHECKS} -XPOST"
        for _ in range(5):
            line = f"sudo {line}"
        self.assertEqual(self.actions(line), [STATUS])
        self.assertEqual(self.actions(f"sudo {line}"), [])  # a sixth level is left to the ruleset

    def test_a_pattern_matches_a_command_run_inside_another(self):
        """`sudo git push --force` asks, as `git push --force` does; and a command no wrapper holds lists nothing."""
        level = risk.command_level(risk.rule_set(None), "sudo git push --force origin x")
        self.assertEqual(level["level"], "ask")
        self.assertIn(FORCE, [a["action"] for a in level["actions"]])
        self.assertEqual(shell.wrapped("git push --force origin x"), [])
        self.assertEqual(commands.split("a && b | c; d"), ["a", "b", "c", "d"])


class CommandLevels(unittest.TestCase):
    """The parser through `aidd risk --command`: forms the globs miss now ask, and nothing asks less."""

    def levels(self, line: str, rs: risk.RuleSet | None = None) -> tuple[str, list[str]]:
        answer = risk.command_level(rs or risk.rule_set(None), line)
        return answer["level"], [a["action"] for a in answer["actions"]]

    def test_a_form_the_globs_miss_asks_and_names_its_action(self):
        cases = [
            (f"gh api {CHECKS} -XPOST", "ask", [STATUS]),
            (f"gh api {CHECKS} -X=POST", "ask", [STATUS]),
            (f"gh api {CHECKS} --method=POST", "ask", [STATUS]),
            (f"gh api {CHECKS} --method POST --silent", "ask", [STATUS]),
            (f"gh api {CHECKS} -H 'Accept: application/json' -X POST", "ask", [STATUS]),
            ("gh api graphql -f query=$QUERY", "ask", [STATUS]),
            ('gh api graphql -f query="$(cat q.graphql)"', "ask", [STATUS]),
            (f"gh api {DISPATCH} -f event_type=RelEase", "ask", [FLOW, RELEASE]),
            (f"gh api {DISPATCH} -f event_type=dEploy", "ask", [FLOW, DEPLOY]),
            ("gh api repos/o/r/actions/workflows/$WF/dispatches -f ref=main", "ask", [FLOW, DEPLOY, RELEASE]),
            (f"gh api {DISPATCH} --input body.json", "ask", [FLOW, DEPLOY, RELEASE]),
            ("make && gh api repos/o/r/check-runs -XPOST", "ask", [STATUS]),
            ("gh api -X PUT repos/o/r/pulls/5/merge", "ask", [MERGE]),
            ("gh api repos/o/r/releases -f tag_name=v1", "ask", [RELEASE]),
            ("gh api -X PATCH repos/o/r/releases/7 -F draft=false", "ask", [RELEASE]),
            ("gh api -X POST repos/o/r/actions/jobs/7/rerun", "report", [FLOW]),
            ("gh api -X POST repos/o/r/check-suites/3/rerequest", "report", [FLOW]),
            ("gh api -X POST repos/o/r/actions/runs/9/pending_deployments -F state=approved", "ask", [DEPLOY]),
            (f"gh api -X DELETE {REFS}/heads/x", "ask", [DELETE]),
            (f"gh api -X PATCH {REFS}/heads/x -f sha=abc", "ask", [PUSH]),
            (f"gh api -X PATCH {REFS}/heads/x -f sha=abc -F force=true", "ask", [PUSH, FORCE]),
            ("gh api -X PUT repos/o/r/contents/a.txt -f message=m", "ask", [PUSH]),
            ("gh api repos/o/r/merges -f base=main -f head=x", "ask", [PUSH]),
        ]
        for line, level, actions in cases:
            with self.subTest(line=line):
                got_level, got = self.levels(line)
                self.assertEqual(got_level, level)
                self.assertEqual(sorted(got), sorted(actions))

    def test_a_form_the_globs_catch_keeps_its_level_and_lists_each_action_once(self):
        cases = [
            (f"gh api {CHECKS} -f name=x -f head_sha=abc", "ask", [STATUS]),
            (f"gh api -f name=x {CHECKS}", "ask", [STATUS]),
            (f"gh api -XPOST {CHECKS}", "ask", [STATUS]),
            ("gh api repos/o/r/statuses/abc -f state=success", "ask", [STATUS]),
            ("gh api graphql -F query=@q.graphql", "ask", [STATUS]),
            ('gh api graphql -f query="mutation { x }"', "ask", [STATUS]),
            (f"gh api {DISPATCH} -f event_type=release", "ask", [FLOW, RELEASE]),
            ("gh api repos/o/r/actions/runs/9/rerun -X POST", "report", [FLOW]),
        ]
        for line, level, actions in cases:
            with self.subTest(line=line):
                got_level, got = self.levels(line)
                self.assertEqual(got_level, level)
                self.assertEqual(sorted(got), sorted(actions))

    def test_a_read_stays_allow(self):
        for line in (
            "gh api repos/o/r/commits/abc/check-runs",
            "gh api repos/o/r/commits/abc/statuses",
            f"gh api {CHECKS} -X GET",
            'gh api graphql -f query="query { viewer { login } }"',
            "gh api user -f name=x",
            "gh api repos/o/r/issues -X POST -f title=x",
            "gh api repos/o/r/releases",
            "gh api repos/o/r/contents/a.txt",
            f"gh api {REFS}/heads/main",
            "env gh api repos/o/r/pulls/5/merge",
            "sudo -n ls",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.levels(line), ("allow", []))

    def test_a_ref_moves_the_branch_the_push_rules_read(self):
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            rs = risk.rule_set(None)
            cases = [
                (f"gh api -X PATCH {REFS}/heads/main -f sha=a", "default"),
                (f"gh api -X PATCH {REFS}/heads/feat -f sha=a", "shared"),
                (f"gh api -X PATCH {REFS}/heads/feat/x -f sha=a", "shared"),
                (f"gh api {REFS} -f ref=refs/heads/main -f sha=a", "default"),
                (f"gh api {REFS} -f ref=refs/heads/feat -f sha=a", "shared"),
                (f"gh api {REFS} -f ref=refs/tags/v1 -f sha=a", "shared"),
                (f"gh api -X PATCH {REFS}/tags/v1 -f sha=a", "shared"),
                (f"gh api -X PATCH {REFS}/heads/$B -f sha=a", "default"),  # a ref aidd cannot read may be the default
                (f"gh api -X PATCH {REFS}/heads/{{branch}} -f sha=a", "default"),  # gh's current branch
                (f"gh api -X PATCH {REFS} -f sha=a", "default"),
                (f"env gh api -X PATCH {REFS}/heads/main -f sha=a", "default"),
                ("gh api -X PUT repos/o/r/contents/a.txt -f message=m", "default"),
                ("gh api -X PUT repos/o/r/contents/a.txt -f branch=feat -f message=m", "shared"),
                ("gh api repos/o/r/merges -f base=feat -f head=x", "shared"),
                # The call as typed: a quoted value that holds a ref is no endpoint.
                (f"gh api -X PATCH -f 'x=y git/refs/heads/feature' {REFS}/heads/main -f sha=a", "default"),
            ]
            for line, want in cases:
                with self.subTest(line=line):
                    answer = risk.command_level(rs, line, cwd=d)
                    self.assertEqual([(a["action"], a["branch"], a["level"]) for a in answer["actions"]], [(PUSH, want, "ask")])

    def test_a_ref_an_environment_names_deploys_there(self):
        """A ref move through the API reaches the environments a push does, so a lowered `git.push` never lowers it."""
        text = (
            "environments:\n"
            '  - {name: production, branches: [prod], tags: ["v*"]}\n'
            "risks:\n  rules:\n    - {action: git.push, branch: shared, level: report}\n    - {action: deploy.run, environment: production, level: ask}\n"
        )
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(d, "tag", "v1")
            rs = risk.rule_set(cfg(text))
            cases = [
                (f"gh api -X PATCH {REFS}/heads/prod -f sha=a", "git push origin prod"),
                (f"gh api {REFS} -f ref=refs/heads/prod -f sha=a", "git push origin prod"),
                (f"gh api {REFS} -f ref=refs/tags/v1 -f sha=a", "git push origin v1"),
                (f"gh api -X PATCH {REFS}/heads/feat -f sha=a", "git push origin feat"),
            ]
            for api, push in cases:
                with self.subTest(api=api):
                    a, p = risk.command_level(rs, api, cwd=d), risk.command_level(rs, push, cwd=d)
                    shape = lambda answer: sorted((x["action"], x["environment"], x["level"]) for x in answer["actions"] if x["action"] != "git.push")  # noqa: E731
                    self.assertEqual(shape(a), shape(p))
                    self.assertEqual(a["level"], p["level"])
            self.assertEqual(risk.command_level(rs, cases[0][0], cwd=d)["level"], "ask")
            self.assertEqual(risk.command_level(rs, cases[3][0], cwd=d)["level"], "report")

    def test_a_call_the_harnesses_ask_for_and_aidd_reads_as_lower_says_so(self):
        note = harness_rules.api_write_note()
        cases = [
            ("gh api -X GET repos/o/r/pulls -f per_page=100", "allow", [note]),
            ("gh api -X GET repos/o/r/pulls", "allow", [note]),
            ("gh api graphql -f query='query { viewer { login } }'", "allow", [note]),
            ("gh api user -f name=x", "allow", [note]),
            ("gh api -X DELETE repos/o/r/issues/comments/1", "allow", [note]),
            ('gh api -X "DELETE" user/keys/1', "allow", [note]),
            ("gh api -X POST repos/o/r/actions/jobs/7/rerun", "report", [note]),
            ("gh api -X GET repos/o/r/pulls -f a=b && gh api -X PUT repos/o/r/pulls/5/merge", "ask", [note]),
            # No note when the line asks in aidd, or no harness pattern matches the call as typed.
            ("gh api -X PUT repos/o/r/pulls/5/merge", "ask", []),
            ("gh api -X DELETE repos/o/r", "ask", []),
            ("gh api -X PUT repos/o/r/pulls/5/merge && gh api repos/o/r/pulls", "ask", []),
            ("gh api repos/o/r/pulls", "allow", []),
            ("gh api -H 'X-GitHub-Api-Version: 1' repos/o/r/pulls", "allow", []),
            ("sudo gh api -X GET repos/o/r/pulls -f a=b", "allow", []),
            ("git status", "allow", []),
        ]
        rs = risk.rule_set(None)
        for line, level, notes in cases:
            with self.subTest(line=line):
                answer = risk.command_level(rs, line)
                self.assertEqual((answer["level"], risk.command_notes(rs, answer)), (level, notes))

    def test_no_note_when_a_config_lowers_what_the_harnesses_would_ask(self):
        line = "gh api -X GET repos/o/r/pulls -f per_page=100"
        for text, notes in (("", [harness_rules.api_write_note()]), (lowered(), [])):
            with self.subTest(config=text):
                rs = risk.rule_set(cfg(text))
                self.assertEqual(risk.command_notes(rs, risk.command_level(rs, line)), notes)

    def test_the_command_answer_prints_the_note(self):
        with _in_a_repo():
            self._command_answer_prints_the_note()

    def _command_answer_prints_the_note(self):
        code, out = helpers.run_cli("risk", "--command", "gh api -X GET repos/o/r/pulls -f per_page=100")
        self.assertEqual(code, 0)
        self.assertIn("level: allow", out)
        self.assertIn(f"note: {harness_rules.api_write_note()}", out)
        code, out = helpers.run_cli("risk", "--command", "gh api -X GET repos/o/r/pulls -f per_page=100", "--json")
        notes = json.loads(out)["notes"]
        self.assertEqual(notes[0], harness_rules.api_write_note())
        self.assertEqual(len(notes), 2, "and a note that no action matched, since this call reads as no action")
        for line in ("gh api repos/o/r/pulls", "gh api -X PUT repos/o/r/pulls/5/merge"):
            code, out = helpers.run_cli("risk", "--command", line)
            self.assertNotIn(harness_rules.api_write_note(), out, line)

    def test_the_gh_repo_commands_that_change_a_repository_ask(self):
        cases = [
            ("gh repo edit o/r --visibility public", "ask", [REPO]),
            ("gh repo edit --default-branch dev", "ask", [REPO]),
            ("gh repo archive o/r --yes", "ask", [REPO]),
            ("gh repo unarchive o/r --yes", "ask", [REPO]),
            ("gh repo rename new-name", "ask", [REPO]),
            ("./bin/gh repo edit o/r --visibility private", "ask", [REPO]),
            ("sudo gh repo archive o/r", "ask", [REPO]),
            ("gh api -X POST repos/o/r/transfer -f new_owner=x", "ask", [REPO]),
            ("gh repo delete o/r --yes", "ask", [DATA]),  # a delete is data.delete, not a setting
            ("gh repo view o/r", "allow", []),
            ("gh repo list o", "allow", []),
            ("gh repo clone o/r", "allow", []),
            ("gh repo set-default o/r", "allow", []),
            ("gh api -X PATCH repos/o/r -f private=false", "ask", [REPO]),
            ("gh api -X PATCH user -f name=Ada", "allow", []),
        ]
        for line, level, actions in cases:
            with self.subTest(line=line):
                got_level, got = self.levels(line)
                self.assertEqual((got_level, sorted(got)), (level, sorted(actions)))

    def test_a_git_push_keeps_its_branch(self):
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(d, "switch", "-qc", "feat")
            answer = risk.command_level(risk.rule_set(None), "git push", cwd=d)
            self.assertEqual([(a["action"], a["branch"], a["level"]) for a in answer["actions"]], [(PUSH, "own", "allow")])


class EndpointData(unittest.TestCase):
    """`api_endpoints` is data: a config adds an action's or replaces it, and a parent's lock holds."""

    def test_a_config_adds_an_action_with_its_endpoints(self):
        rs = risk.rule_set(
            cfg("risks:\n  actions:\n    issue.close: {api_endpoints: ['PATCH */issues/*']}\n  rules:\n    - {action: issue.close, level: ask}\n")
        )
        self.assertEqual(risk.command_level(rs, "gh api -X PATCH repos/o/r/issues/4 -f state=closed")["level"], "ask")
        self.assertEqual(risk.command_level(rs, "gh api repos/o/r/issues/4")["level"], "allow")
        self.assertEqual(risk.command_level(rs, "gh api -X POST repos/o/r/issues/4")["level"], "allow")  # not the method it names

    def test_a_config_replaces_the_endpoints_of_a_built_in_action(self):
        rs = risk.rule_set(cfg("risks:\n  actions:\n    pr.merge: {commands: ['gh pr merge*'], api_endpoints: ['*/merge-queue/*']}\n"))
        self.assertEqual(rs.actions["pr.merge"]["api_endpoints"], ["*/merge-queue/*"])
        self.assertEqual(risk.command_level(rs, "gh api -X PUT repos/o/r/pulls/5/merge")["level"], "allow")
        self.assertEqual(risk.command_level(rs, "gh api -X PUT repos/o/r/merge-queue/5")["level"], "ask")

    def test_a_config_cannot_remove_what_a_parent_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "preset.yaml").write_text(
                'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: commit_status.post, level: ask, locked: true}\n'
            )
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(
                'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: preset.yaml}]\nrisks:\n'
                "  actions:\n    commit_status.post: {description: x, api_endpoints: ['nothing/matches/this']}\n"
            )
            c = config.load_file(config.CONFIG_PATH, tmp)
            rs = risk.rule_set(c)
            self.assertIn("POST|PATCH *check-runs*", rs.actions["commit_status.post"]["api_endpoints"])
            self.assertTrue(any("commit_status.post" in w and "ignored" in w for w in c.warnings), c.warnings)
            self.assertEqual(risk.command_level(rs, f"gh api {CHECKS} -XPOST")["level"], "ask")

    def test_a_method_prefix_is_checked(self):
        """A first word of letters that is no list of write methods is a slip, not a glob."""
        cases = {
            "PATCH */issues/*": True,
            "POST|PUT|PATCH|DELETE */issues/*": True,
            "*/issues/*": True,
            "*dispatches* --input*": True,
            "graphql#mutation *x*": True,
            "PUSH */issues/*": False,
            "patch */issues/*": False,
            "GET */issues/*": False,
            "POST|GET */issues/*": False,
            "POST|| */issues/*": False,
            "POST  */issues/*": False,
            "": False,
        }
        for entry, ok in cases.items():
            with self.subTest(entry=entry):
                try:
                    cfg(f"risks:\n  actions:\n    issue.close: {{api_endpoints: [{json.dumps(entry)}]}}\n")
                    loaded = True
                except Exception:  # noqa: BLE001  # the load error names the schema's reason
                    loaded = False
                self.assertEqual(loaded, ok)

    def test_the_list_shows_the_endpoints(self):
        with _in_a_repo():
            self._list_shows_the_endpoints()

    def _list_shows_the_endpoints(self):
        built_in = {k: v["api_endpoints"] for k, v in risk.builtin()["actions"].items() if v.get("api_endpoints")}
        self.assertTrue(built_in)
        code, out = helpers.run_cli("risk", "--list", "--json")
        self.assertEqual((code, json.loads(out)["api_endpoints"]), (0, built_in))
        code, out = helpers.run_cli("risk", "--list")
        self.assertEqual(code, 0)
        for action, entries in built_in.items():
            self.assertIn(f"gh api endpoints, {action}: {', '.join(entries)}\n", out)


class Splitting(unittest.TestCase):
    def test_a_command_line_splits_at_each_separator(self):
        cases = [
            ("a && b || c; d | e |& f & g\nh", ["a", "b", "c", "d", "e", "f", "g", "h"]),
            ("make 2>&1 | tee x", ["make 2>&1", "tee x"]),
            ("cmd &> out", ["cmd &> out"]),
            ("cmd &>> out", ["cmd &>> out"]),
            ("cmd >& out", ["cmd >& out"]),
            ("cmd <&3", ["cmd <&3"]),
            ("cmd 2>&1 && next", ["cmd 2>&1", "next"]),
            ("a & b", ["a", "b"]),
            ("a &", ["a"]),
            ("& a", ["a"]),
            ("echo 'a & b | c; d'", ["echo 'a & b | c; d'"]),
            ('echo "a & b | c; d"', ['echo "a & b | c; d"']),
            ("echo a\\\nb", ["echo ab"]),  # a backslash before a new line joins the two lines
            ('echo "a\\\nb"', ['echo "ab"']),
            ("echo 'a\\\nb'", ["echo 'a\\\nb'"]),  # in single quotes it is text
            ("git push \\\n  --force", ["git push   --force"]),
            ("a \\; b", ["a \\; b"]),
        ]
        for line, want in cases:
            with self.subTest(line=line):
                self.assertEqual(shell.split(line), want)


class Words(unittest.TestCase):
    def test_which_words_the_shell_expands(self):
        cases = [
            ("gh api graphql -f query=$Q", [("gh", 0), ("api", 0), ("graphql", 0), ("-f", 0), ("query=$Q", 1)]),
            ('gh api -f "q=$Q"', [("gh", 0), ("api", 0), ("-f", 0), ("q=$Q", 1)]),
            ("gh api -f 'q=$Q'", [("gh", 0), ("api", 0), ("-f", 0), ("q=$Q", 0)]),
            ('gh api -f "q=\\$Q"', [("gh", 0), ("api", 0), ("-f", 0), ("q=$Q", 0)]),
            ("gh api -f q=\\$Q", [("gh", 0), ("api", 0), ("-f", 0), ("q=$Q", 0)]),
            ("gh api -f q=`x`", [("gh", 0), ("api", 0), ("-f", 0), ("q=`x`", 1)]),
            ("gh api -f q=$'a'", [("gh", 0), ("api", 0), ("-f", 0), ("q=$a", 1)]),
            ("gh api -f 'a b' \"c d\"", [("gh", 0), ("api", 0), ("-f", 0), ("a b", 0), ("c d", 0)]),
            ("A=1 B=2 gh api", [("gh", 0), ("api", 0)]),
            ("gh api 'x y", [("gh", 0), ("api", 0), ("'x", 0), ("y", 0)]),  # a quote that never closes: split at spaces
            ('gh "" x', [("gh", 0), ("", 0), ("x", 0)]),
        ]
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual([(str(w), int(w.expands)) for w in shell.tokens(text)], want)


class DoctorNote(unittest.TestCase):
    def notes(self, harness: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            key = next(k for k, h in config.HARNESSES.items() if h.ask_rules == harness)
            return [text for level, text in doctor_harnesses.harness_checks(Path(tmp), [key]) if level == "note"]

    def test_a_leading_words_format_says_what_it_does_not_hold(self):
        for harness in ("codex", "qwen"):
            with self.subTest(harness=harness):
                notes = self.notes(harness)
                api = [n for n in notes if "`gh api`" in n]
                self.assertEqual(len(api), 1, notes)  # one line, apart from the list of what is held in part
                self.assertFalse([n for n in notes if "its own rules hold" in n and "gh api" in n], notes)

    def test_a_glob_format_holds_them_and_says_nothing(self):
        self.assertFalse([n for n in self.notes("claude-code") if "gh api" in n])


class HarnessAskRules(unittest.TestCase):
    """The harness ask rules ask before any `gh api` call that may write, whatever its endpoint, with one small set: a
    harness matches command text, and the text cannot tell an endpoint's write from its read. `aidd risk --command` reads
    the same call exactly. A leading-words format cannot hold a `*` inside a command, so it leaves them to the skill."""

    # One call for each way the text shows a write: a method flag in its common spellings, a field or an input, GraphQL.
    ASK = (
        "gh api -X PUT repos/o/r/pulls/5/merge",
        "gh api -XPUT repos/o/r/pulls/5/merge",
        "gh api -iXPUT repos/o/r/pulls/5/merge",
        "gh api -iX PUT repos/o/r/pulls/5/merge",
        "gh api -iX=PUT repos/o/r/pulls/5/merge",
        "gh api -X  PUT repos/o/r/pulls/5/merge",
        'gh api -X "PUT" repos/o/r/pulls/5/merge',
        "gh api -X 'DELETE' repos/o/r",
        'gh api -X"PUT" repos/o/r/pulls/5/merge',
        "gh api -X'DELETE' repos/o/r/branches/main/protection",
        "gh api -X post repos/o/r/releases",
        "gh api -X Put repos/o/r/pulls/5/merge",  # any explicit method asks, in any case or quoting
        'gh api -X P"U"T repos/o/r/pulls/5/merge',
        "gh api -X $'PUT' repos/o/r/pulls/5/merge",
        "gh api -iF draft=false repos/o/r/releases/7",
        "gh api -if x=1 repos/o/r/releases",
        "gh api --method=patch repos/o/r/releases/7",
        "gh api repos/o/r/pulls/5/merge -X  PUT",
        'gh api repos/o/r -X "DELETE"',
        'gh api -H "Accept: x" -X "PUT" repos/o/r/pulls/5/merge',
        "gh api -X POST repos/o/r/releases",
        "gh api -X PATCH repos/o/r/git/refs/heads/main",
        "gh api -XDELETE repos/o/r/git/refs/heads/x",
        "gh api repos/o/r/pulls/5/merge --method=PUT",
        "gh api --method PATCH repos/o/r/issues/comments/9",
        'gh api --method "DELETE" repos/o/r/releases/7',
        "gh api -X $M repos/o/r/releases",
        "gh api --method=$M repos/o/r/releases",
        "gh api repos/o/r/releases -f tag_name=v1",
        "gh api repos/o/r/releases -fname=x",
        "gh api -f ref=refs/heads/x repos/o/r/git/refs",
        "gh api repos/o/r/git/refs -F force=true",
        "gh api repos/o/r/issues/5/comments --field body=hi",
        "gh api repos/o/r/releases --raw-field tag_name=v1",
        "gh api --input body.json repos/o/r/git/refs",
        "gh api repos/o/r/dispatches --input=body.json",
        "gh api repos/o/r/statuses/abc -f state=success",
        "gh api graphql -f query='mutation { x }'",
        "gh api graphql",
        "gh api -H 'Accept: x' graphql -F query=@q.graphql",
        "gh api https://api.github.com/graphql --input q.json",
    )
    # A read the text shows no write for.
    ALLOW = (
        "gh api repos/o/r/pulls",
        "gh api repos/o/r/pulls/5/merge",
        "gh api repos/o/r/git/refs/heads/main",
        "gh api repos/o/r/git/matching-refs/heads/f",
        "gh api repos/o/r/releases",
        "gh api repos/my-fork/r/releases",  # a `-f` inside a name is no flag
        "gh api repos/o/r/contents/a.txt",
        "gh api repos/o/r/contents/docs/INPUT.md",  # the letters of a method inside a file name
        "gh api repos/o/r/contents/docs/XPUT.md",
        "gh api repos/o/r/releases/tags/XPOST",
        'gh api -H "X-GitHub-Api-Version: 2022-11-28" repos/o/r/pulls',  # an `X` that is no method flag
        "gh api repos/o/r/pulls -q .X",
        "gh api repos/o/r/pulls --jq '.[].X'",
        "gh api --paginate repos/o/r/pulls --jq '.[].title'",
        "gh api -H 'Accept: application/vnd.github+json' repos/o/r/pulls",
        "gh api repos/o/r/commits/abc/check-runs",
        "gh api repos/o/r/commits/abc/statuses",
        "gh api repos/o/r/statuses/abc",  # GitHub serves no GET on it, and no flag shows a write
        "gh api repos/o/r/branches/main/protection",
        "gh api user",
    )
    # What the harness asks for and `aidd risk` reads, exactly, as a lower level: it asks more, never less.
    MORE = (
        "gh api -X GET repos/o/r/pulls",
        "gh api --method GET repos/o/r/pulls",
        "gh api -iX GET repos/o/r/pulls",
        "gh api -X GET repos/o/r/pulls -f per_page=100",
        "gh api repos/o/r/pulls --method GET --field per_page=100",
        "gh api graphql -f query='query { viewer { login } }'",
        "gh api user -f name=x",
        "gh api -X POST repos/o/r/issues -f title=x",
        "gh api -X GET repos/o/r/contents/docs/INPUT.md",  # the letters of a method after `-X`
        "gh api repos/o/r/dispatches -f event_type=build",
        "gh api -X POST repos/o/r/actions/jobs/7/rerun",
    )

    @classmethod
    def written(cls, rs: risk.RuleSet | None = None) -> dict:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            patterns = risk.harness_patterns(rs or risk.rule_set(None), "main")
            for fmt in risk.FORMATS:
                risk.apply_harness_rules(root, fmt, patterns)
            read = lambda rel: json.loads((root / rel).read_text())  # noqa: E731
            bash = lambda e: e[len("Bash(") : -1]  # noqa: E731
            return {
                "claude-code": [bash(e) for e in read(".claude/settings.json")["permissions"]["ask"]],
                "opencode": [r["resource"] for r in read("opencode.json")["permissions"] if r["effect"] == "ask"],
                "grok": [bash(e) for e in tomllib.loads((root / ".grok/config.toml").read_text())["permission"]["ask"]],
                "vscode": [k[1:-1] for k, v in read(".vscode/settings.json")["chat.tools.terminal.autoApprove"].items() if v is False],
                "codex": (root / ".codex/rules/aidd.rules").read_text(),
                "qwen": [bash(e) for e in read(".qwen/settings.json")["permissions"]["ask"]],
            }

    @classmethod
    def askers(cls, rs: risk.RuleSet | None = None) -> dict:
        w = cls.written(rs)
        return {
            "claude-code": lambda c: any(fnmatch.fnmatchcase(c, p) for p in w["claude-code"]),
            "opencode": lambda c: any(fnmatch.fnmatchcase(c, p) for p in w["opencode"]),
            "grok": lambda c: any(fnmatch.fnmatchcase(c, p) for p in w["grok"]),
            "vscode": lambda c: any(re.search(r, c) for r in w["vscode"]),
        }

    def test_each_format_asks_for_each_write_form_and_not_for_a_read(self):
        asks = self.askers()
        for command in self.ASK + self.MORE + self.ALLOW:
            for fmt, ask in asks.items():
                with self.subTest(command=command, harness=fmt):
                    self.assertEqual(ask(command), command not in self.ALLOW)

    def test_every_form_aidd_risk_asks_for_is_asked_in_each_format(self):
        """The harnesses ask for more than `aidd risk` and never less, over each endpoint, method spelling, and body."""
        asks = self.askers()
        rs = risk.rule_set(None)
        endpoints = [
            "repos/o/r/pulls/5/merge",
            "repos/o/r/releases",
            "repos/o/r/releases/7",
            "repos/o/r/git/refs/heads/main",
            "repos/o/r/git/refs",
            "repos/o/r",
            "repos/o/r/issues/5/comments",
            "repos/o/r/branches/main/protection",
            "repos/o/r/rulesets/5",
            "repos/o/r/actions/workflows/ci.yml/dispatches",
            "repos/o/r/check-runs",
            "repos/o/r/contents/a.txt",
            "repos/o/r/merges",
            "graphql",
            "repos/o/r/statuses/abc",
            "repos/o/r/transfer",
            "repos/o/r/actions/workflows/release.yml/dispatches",
        ]
        methods = ["", "-X POST", "--method=PATCH", "-X DELETE", "-iXPUT", "--method 'PUT'", "-X $M", "-X Put", '-X P"U"T']
        bodies = ["", "-f a=b", "--input b.json", "-iF draft=false", "-if x=1", "-f query='mutation { x }'"]
        checked = 0
        for ep, m, b in itertools.product(endpoints, methods, bodies):
            for order in itertools.permutations([ep, m, b]):
                line = "gh api " + " ".join(x for x in order if x)
                if risk.command_level(rs, line)["level"] != "ask":
                    continue
                checked += 1
                for fmt, ask in asks.items():
                    self.assertTrue(ask(line), (fmt, line))
        self.assertGreater(checked, 500)

    def test_the_set_is_small_and_the_same_in_every_format(self):
        patterns = harness_rules.api_write_patterns()
        self.assertEqual((len(patterns), len(set(patterns))), (12, 12))
        self.assertTrue(all(p.startswith("gh api") for p in patterns))
        self.assertEqual(patterns[:3], ["gh api* -X*", "gh api* -iX*", "gh api*--method*"])  # no method is listed
        self.assertFalse([p for p in patterns if "PUT" in p or "pulls" in p or "?" in p])  # nothing per method or endpoint
        w = self.written()
        for fmt in ("claude-code", "opencode", "grok"):
            with self.subTest(fmt=fmt):
                self.assertTrue(set(patterns) <= set(w[fmt]))
        self.assertTrue({harness_rules.glob_regex(p) for p in patterns} <= set(w["vscode"]))

    def test_an_action_pattern_the_set_does_not_hold_stays(self):
        """A `gh api` pattern of a config's action stays unless the set's patterns match its text, so a harness asks for more
        than `aidd risk`, never less. The built-in actions keep none: `api_endpoints` owns what they ask for."""
        text = (
            "risks:\n  actions:\n    secret.read: {commands: ['gh api *secrets*', 'gh api -X Delete*', 'gh api repos/*/actions/secrets* -f*']}\n"
            "  rules:\n    - {action: secret.read, level: ask}\n"
        )
        rs = risk.rule_set(cfg(text))
        patterns = risk.harness_patterns(rs, "main")
        self.assertIn("gh api *secrets*", patterns)  # shows no write flag, so the set cannot hold it
        self.assertNotIn("gh api -X Delete*", patterns)  # held by `gh api* -X*`
        self.assertNotIn("gh api repos/*/actions/secrets* -f*", patterns)  # held by `gh api* -f*`
        builtin = [p for p in risk.harness_patterns(risk.rule_set(None), "main") if p.startswith("gh api")]
        self.assertEqual(sorted(builtin), sorted(harness_rules.api_write_patterns()))
        for fmt, ask in self.askers(rs).items():
            for command in ("gh api repos/o/r/actions/secrets/X", "gh api -X Delete repos/o/r/actions/secrets/X"):
                with self.subTest(fmt=fmt, command=command):
                    self.assertTrue(ask(command))

    def test_the_generated_table_names_the_harnesses_that_hold_the_set(self):
        from aidd.docsgen import ask_holds

        names = harness_rules.api_harness_names()
        row = next(r for r in ask_holds.ask_holds_table().splitlines() if r.startswith("| `branch_protection.change`"))
        self.assertIn(names, row)
        self.assertIn(harness_rules.api_write_patterns()[0], row)
        self.assertTrue(all(label not in names for label in ("Codex", "Qwen Code")))

    def test_a_leading_words_format_asks_only_at_a_flag_first_write(self):
        """A leading-words format asks at `gh api` and a write flag or `graphql`, Codex's rule, and
        leaves an endpoint-first write to the skill, so the set stays in `unwritten`."""
        flags = ["-X", "--method", "-f", "-F", "--field", "--raw-field", "--input", "graphql"]
        w = self.written()
        self.assertEqual(
            [line for line in w["codex"].splitlines() if '"gh", "api"' in line],
            [f'prefix_rule(pattern = {json.dumps(["gh", "api", flags])}, decision = "prompt")'],
        )
        self.assertEqual([e for e in w["qwen"] if e.startswith("gh api")], [e for f in flags for e in (f"gh api {f}", f"gh api {f} *")])
        patterns = risk.harness_patterns(risk.rule_set(None), "main")
        for fmt in ("codex", "qwen"):
            with self.subTest(fmt=fmt):
                self.assertTrue(all(p in risk.unwritten(fmt, patterns) for p in harness_rules.api_write_patterns()))

    def test_the_set_comes_only_while_an_action_with_endpoints_asks(self):
        def api(text: str) -> list[str]:
            return [p for p in risk.harness_patterns(risk.rule_set(cfg(text)), "main") if p.startswith("gh api")]

        self.assertFalse(api(lowered()))
        self.assertEqual(sorted(api(lowered(ask=("pr.merge",)))), sorted(harness_rules.api_write_patterns()))
        self.assertTrue(api(lowered() + "    - {action: git.push, branch: shared, level: ask}\n"))

    def test_a_pattern_is_a_regular_expression_that_means_the_same(self):
        regex = harness_rules.glob_regex("gh api* -X*")
        for text, want in [
            ("gh api -XPUT repos/o/r", True),
            ("gh api repos/o/r -X GET", True),
            ("gh api repos/o/r/contents/XPUT.md", False),
            ('gh api -H "X-GitHub-Api-Version: 1" repos/o/r', False),
        ]:
            with self.subTest(text=text):
                self.assertEqual(re.search(regex, text) is not None, want)
        self.assertIn("\\?", harness_rules.glob_regex("a?b"))  # a command keeps its `?`


if __name__ == "__main__":
    unittest.main()
