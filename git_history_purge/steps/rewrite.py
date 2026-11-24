"""Step 3, rewrite: replace every secret in a fresh copy of the history with git-filter-repo. Never changes the remote."""

from git_history_purge.console import fail, ok, say
from git_history_purge.git import mirror_clone, require_tools, run_git
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace, read_lines, remove_tree


def step_rewrite(settings: Settings, workspace: Workspace) -> None:
    require_tools("git", "git-filter-repo")
    has_replacements = workspace.replacements_file.is_file() and workspace.replacements_file.stat().st_size > 0
    unvalidated = read_lines(workspace.unvalidated_live_keys) if workspace.unvalidated_live_keys.is_file() else []
    if not has_replacements:
        fail("run the find step first")
    if unvalidated and not settings.allow_unvalidated_keys:
        fail(f"secret keys still live but not validated: {', '.join(unvalidated)}. Validate them, or pass --allow-unvalidated-keys")

    say("Making a fresh copy to rewrite (the download stays untouched for comparison)")
    remove_tree(workspace.cleaned)
    mirror_clone(workspace.original, workspace.cleaned)

    say("Rewriting history (file contents and commit messages)")
    removed_path_args = [arg for path in settings.removed_paths for arg in ("--path-glob", path)]
    invert_args = ["--invert-paths"] if removed_path_args else []
    run_git(
        "filter-repo", "--force", "--quiet",
        "--replace-text", str(workspace.replacements_file),
        "--replace-message", str(workspace.replacements_file),
        *removed_path_args, *invert_args,
        repo=workspace.cleaned,
    )
    ok(f"rewritten copy: {workspace.cleaned}")
    ok(f"replacement text: {workspace.replacement_text_file.read_text(encoding='utf-8')}")
    if settings.removed_paths:
        ok(f"paths removed from every commit: {', '.join(settings.removed_paths)}")
