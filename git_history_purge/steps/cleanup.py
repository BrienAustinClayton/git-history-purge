"""Step 7, cleanup: delete the work folder, which still holds the original secrets."""

from git_history_purge.console import ok, require_typed_word
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace, remove_tree


def step_cleanup(settings: Settings, workspace: Workspace) -> None:
    require_typed_word(f"This deletes {workspace.root} (it holds the original secrets).", "DELETE")
    remove_tree(workspace.root)
    ok("work folder deleted")
