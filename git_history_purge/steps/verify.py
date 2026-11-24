"""Step 4, verify: prove the rewritten copy is clean and complete. Never changes the remote."""

import json

from git_history_purge.console import fail, info, say
from git_history_purge.detection.sources import run_gitleaks
from git_history_purge.git import commit_count, require_tools
from git_history_purge.safety import check_history_is_clean
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace


def step_verify(settings: Settings, workspace: Workspace) -> None:
    require_tools("git")
    if not workspace.cleaned.is_dir():
        fail("run the rewrite step first")

    say("Checking the rewritten copy")
    check_history_is_clean(settings, workspace, workspace.cleaned, "rewritten-copy")
    info(f"commits before / after: {commit_count(workspace.original)} / {commit_count(workspace.cleaned)} (empty commits may disappear)")

    if settings.full_checks:
        require_tools("gitleaks")
        say("Re-running gitleaks on the rewritten copy")
        findings_after = run_gitleaks(workspace.cleaned, workspace.gitleaks_after)
        findings_before = json.loads(workspace.gitleaks_before.read_text(encoding="utf-8") or "[]")
        info(f"gitleaks findings before / after: {len(findings_before)} / {len(findings_after)} (what is left should be values still on the reference branch)")
