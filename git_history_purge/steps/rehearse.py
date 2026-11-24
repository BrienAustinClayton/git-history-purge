"""Step 5, rehearse: run the real push code against a local stand-in, clone it fresh and check again. Unlocks the push step."""

from git_history_purge.console import fail, ok, say
from git_history_purge.git import branch_and_tag_refs, mirror_clone, require_tools
from git_history_purge.pushing import push_cleaned_history
from git_history_purge.safety import (
    check_history_is_clean,
    require_remote_matches_cleaned_copy,
    require_remote_unchanged_since_fetch,
)
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace, remove_tree, write_lines


def step_rehearse(settings: Settings, workspace: Workspace) -> None:
    require_tools("git")
    if not workspace.cleaned.is_dir():
        fail("run the rewrite and verify steps first")
    rehearsal_remote = str(workspace.rehearsal_remote)
    workspace.rehearsal_passed.unlink(missing_ok=True)

    say("Creating a local stand-in for the remote, exactly as it was at fetch time")
    remove_tree(workspace.rehearsal_remote)
    remove_tree(workspace.rehearsal_clone)
    mirror_clone(workspace.original, workspace.rehearsal_remote, copy_objects=False)

    say("Running the real push sequence against the local stand-in")
    require_remote_unchanged_since_fetch(workspace, rehearsal_remote)
    push_cleaned_history(settings, workspace, rehearsal_remote)
    require_remote_matches_cleaned_copy(workspace, rehearsal_remote)

    say("Cloning the local stand-in fresh, like a teammate would after the real push")
    mirror_clone(workspace.rehearsal_remote, workspace.rehearsal_clone)
    check_history_is_clean(settings, workspace, workspace.rehearsal_clone, "rehearsal-fresh-clone")

    write_lines(workspace.rehearsal_passed, branch_and_tag_refs(workspace.cleaned))
    remove_tree(workspace.rehearsal_remote)
    remove_tree(workspace.rehearsal_clone)
    ok("rehearsal passed; the push step is now unlocked for this rewritten copy")
