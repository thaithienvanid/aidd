"""`aidd hook <event>`: the commands an agent harness runs. Its own module, so a hook that runs on every tool call
(`post-tool`) imports none of the maintainers' commands (docs generation, evals) and starts in the time Python takes."""

from __future__ import annotations

from aidd.kernel import git


def cmd_hook(args) -> int:
    from aidd import guard

    if args.event == "pre-tool":
        return guard.pre_tool_hook()
    if args.event == "post-tool":
        return guard.post_tool_hook()
    from aidd.cli.commands import typed_decisions

    with git.system_only():  # the session hooks read git as the guard does
        # The prompt hook records what the person typed when it is a decision (`approve SPEC-1`), in this process.
        return guard.run_session_hook(args.event, on_prompt=typed_decisions.record)
