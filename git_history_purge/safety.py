"""Checks that guard the push: no secret left, no branch or tag lost, current files unchanged, remote untouched since fetch."""

from pathlib import Path

from git_history_purge.console import fail, info, ok
from git_history_purge.git import (
    branch_and_tag_refs,
    count_values_still_present,
    files_changed_between,
    ref_names,
    remote_branch_and_tag_refs,
)
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace, read_lines, write_lines


def check_history_is_clean(settings: Settings, workspace: Workspace, repo: Path, label: str) -> None:
    failures = []

    def check(passed: bool, message: str) -> None:
        if passed:
            ok(message)
            return
        print(f"  [FAIL] {message}", flush=True)
        failures.append(message)

    values_left = count_values_still_present(repo, read_lines(workspace.values_file))
    check(values_left == 0, f"secret values still in {label}: {values_left} (must be 0)")

    names_before = ref_names(read_lines(workspace.refs_at_fetch))
    names_after = ref_names(branch_and_tag_refs(repo))
    write_lines(workspace.reports / f"refs-missing-in-{label}.txt", sorted(names_before - names_after))
    check(names_before == names_after, f"branches + tags before / after: {len(names_before)} / {len(names_after)} (must be the same names)")

    changed = files_changed_between(workspace.original, repo, settings.reference_branch)
    write_lines(workspace.reports / f"files-changed-on-{settings.reference_branch}-in-{label}.txt", changed)
    check(not changed, f"current files on {settings.reference_branch} changed in {label}: {len(changed)} (must be 0)")

    if failures:
        fail(f"{len(failures)} check(s) failed on {label}. Do NOT push. Reports: {workspace.reports}")


def require_remote_unchanged_since_fetch(workspace: Workspace, target: str) -> None:
    refs_now = set(remote_branch_and_tag_refs(target))
    refs_at_fetch = set(read_lines(workspace.refs_at_fetch))
    rewritten_refs = set(branch_and_tag_refs(workspace.cleaned))
    unexpected_refs = sorted(refs_now - refs_at_fetch - rewritten_refs)
    deleted_names = sorted(ref_names(refs_at_fetch) - ref_names(refs_now))
    already_pushed = refs_now & rewritten_refs - refs_at_fetch

    if unexpected_refs or deleted_names:
        print("\n".join(f"  changed: {line}" for line in unexpected_refs[:20]))
        print("\n".join(f"  deleted: {name}" for name in deleted_names[:20]))
        fail("the remote changed since the fetch step (someone pushed). Start again from fetch. Nothing was pushed.")
    if already_pushed:
        info(f"{len(already_pushed)} branches/tags already point at the rewritten history (resuming an interrupted push)")
    ok("nobody else pushed since the fetch step")


def require_remote_matches_cleaned_copy(workspace: Workspace, target: str) -> None:
    if remote_branch_and_tag_refs(target) != branch_and_tag_refs(workspace.cleaned):
        fail(f"after the push, {target} does not match the rewritten copy. Compare with: git ls-remote {target}")
    ok("every branch and tag on the remote now points at the rewritten history")
