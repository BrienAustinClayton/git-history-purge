"""The push sequence: reference branch first with --force-with-lease, then all branches, then all tags. Resumable."""

import subprocess

from git_history_purge.console import fail, ok, say
from git_history_purge.git import branch_commit, remote_branch_and_tag_refs
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace


def push_or_stop(workspace: Workspace, target: str, refspecs: list[str], force_flag: str, refused_message: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(workspace.cleaned), "push", "--quiet", force_flag, target, *refspecs], capture_output=True
    )
    if completed.returncode != 0:
        fail(f"{refused_message}\n{completed.stderr.decode('utf-8', 'replace').strip()}")


def push_cleaned_history(settings: Settings, workspace: Workspace, target: str) -> None:
    branch = settings.reference_branch
    branch_at_fetch = branch_commit(workspace.original, branch)
    rewritten_branch_line = f"{branch_commit(workspace.cleaned, branch)}\trefs/heads/{branch}"

    say(f"1/3 Pushing {branch} first (if this is refused, nothing else is pushed)")
    if rewritten_branch_line in remote_branch_and_tag_refs(target):
        ok(f"{branch} was already pushed")
    else:
        push_or_stop(
            workspace, target, [f"refs/heads/{branch}:refs/heads/{branch}"],
            f"--force-with-lease=refs/heads/{branch}:{branch_at_fetch}",
            f"{branch} was refused (check WHICH account pushed in the error below, and its force-push/bypass permission). Nothing was pushed.",
        )
        ok(f"{branch} pushed")

    say("2/3 Pushing all other branches")
    push_or_stop(
        workspace, target, ["refs/heads/*:refs/heads/*"], "--force",
        f"some branches were refused. {branch} is pushed. Fix the cause and run the push step again; it resumes.",
    )
    ok("branches pushed")

    say("3/3 Pushing all tags")
    push_or_stop(
        workspace, target, ["refs/tags/*:refs/tags/*"], "--force",
        "some tags were refused. Branches are pushed. Fix the cause and run the push step again; it resumes.",
    )
    ok("tags pushed")
