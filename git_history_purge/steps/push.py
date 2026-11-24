"""Step 6, push: force-push the rewritten history to the real remote, only after a passed rehearsal and a typed PUSH."""

from git_history_purge.console import fail, require_typed_word, say
from git_history_purge.defaults import DEFAULT_AFTER_PUSH_CHECKLIST, DEFAULT_BEFORE_PUSH_CHECKLIST
from git_history_purge.git import branch_and_tag_refs, remote_refs_with_prefixes, require_tools
from git_history_purge.pushing import push_cleaned_history
from git_history_purge.safety import require_remote_matches_cleaned_copy, require_remote_unchanged_since_fetch
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace, read_lines


def step_push(settings: Settings, workspace: Workspace) -> None:
    require_tools("git")
    rehearsed_this_copy = (
        workspace.rehearsal_passed.is_file()
        and read_lines(workspace.rehearsal_passed) == branch_and_tag_refs(workspace.cleaned)
    )
    if not rehearsed_this_copy:
        fail("this rewritten copy has not passed the rehearse step. Run test (or rehearse) first.")
    fetched_from = workspace.fetched_from.read_text(encoding="utf-8")
    if fetched_from != settings.repo_url:
        fail(f"history was fetched from {fetched_from} but you are pushing to {settings.repo_url}. Fetch from the push target.")

    say(f"Making sure nobody pushed to {settings.repo_url} since the fetch step")
    require_remote_unchanged_since_fetch(workspace, settings.repo_url)

    read_only_refs = remote_refs_with_prefixes(settings.repo_url, settings.dropped_ref_prefixes)
    if read_only_refs:
        print(f"\nWARNING: {len(read_only_refs)} read-only refs on the remote cannot be rewritten and keep OLD history (with secrets) reachable:")
        print("\n".join(f"  {ref}" for ref in read_only_refs))
        print("Complete or abandon those pull requests first, or accept it (the secrets get rotated anyway).")
    print(f"\nAbout to FORCE-PUSH the rewritten history to:\n  {settings.repo_url}")
    print("Every branch and tag gets new commit ids; everyone must delete their clone and re-clone.")
    print("Confirm every item first:")
    print("\n".join(f"  - {item}" for item in DEFAULT_BEFORE_PUSH_CHECKLIST))
    require_typed_word("", "PUSH")

    push_cleaned_history(settings, workspace, settings.repo_url)
    require_remote_matches_cleaned_copy(workspace, settings.repo_url)
    print(f"\nDONE. History on {settings.repo_url} is clean.\nNow:")
    print("\n".join(f"  {number}. {item}" for number, item in enumerate(DEFAULT_AFTER_PUSH_CHECKLIST, start=1)))
