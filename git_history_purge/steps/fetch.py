"""Step 1, fetch: download every branch and tag into the work folder. Never changes the remote."""

from git_history_purge.console import fail, ok, say
from git_history_purge.git import (
    branch_and_tag_refs,
    branch_exists,
    commit_count,
    default_branch,
    delete_refs_with_prefix,
    mirror_clone,
    require_tools,
)
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace, remove_tree, write_lines


def step_fetch(settings: Settings, workspace: Workspace) -> None:
    require_tools("git")
    workspace.create_private_folders()

    say(f"Downloading every branch and tag from {settings.repo_url}")
    remove_tree(workspace.original)
    mirror_clone(settings.repo_url, workspace.original)
    reference_branch = settings.reference_branch or default_branch(workspace.original)
    ok(f"reference branch: {reference_branch}" + ("" if settings.reference_branch else " (the remote's default branch)"))
    for prefix in settings.dropped_ref_prefixes:
        ok(f"dropped {delete_refs_with_prefix(workspace.original, prefix)} read-only {prefix}* refs (they cannot be pushed back)")
    if not branch_exists(workspace.original, reference_branch):
        fail(f"branch {reference_branch} not found in {settings.repo_url}")

    workspace.fetched_from.write_text(settings.repo_url, encoding="utf-8")
    refs = branch_and_tag_refs(workspace.original)
    write_lines(workspace.refs_at_fetch, refs)
    ok(f"branches + tags downloaded: {len(refs)}")
    ok(f"commits downloaded: {commit_count(workspace.original)}")
