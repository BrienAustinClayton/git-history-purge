"""Step 2, find: collect every secret value in history and write the replacement list and reports. Never changes the remote."""

from datetime import datetime

from git_history_purge.console import fail, info, ok, say
from git_history_purge.detection.ledger import SecretLedger
from git_history_purge.detection.reference_branch import keep_values_still_on_reference_branch, live_keys_outside_validation
from git_history_purge.detection.reports import write_find_reports
from git_history_purge.detection.sources import (
    collect_extra_literals,
    collect_from_config_files,
    collect_from_extra_patterns,
    collect_from_gitleaks,
    run_gitleaks,
)
from git_history_purge.git import require_tools
from git_history_purge.settings import Settings
from git_history_purge.workspace import Workspace, write_lines


def step_find(settings: Settings, workspace: Workspace) -> None:
    require_tools("git", "gitleaks")
    if not workspace.original.is_dir():
        fail("run the fetch step first")
    ledger = SecretLedger()

    say("Scanning every commit with gitleaks (a few minutes on a big repo)")
    findings = run_gitleaks(workspace.original, workspace.gitleaks_before)
    collect_from_gitleaks(ledger, findings, settings)
    ok(f"gitleaks findings: {len(findings)}")

    say("Reading every old version of config files (.env, .properties, config YAML, ...)")
    ok(f"config file versions read: {collect_from_config_files(ledger, workspace.original, settings)}")

    say("Searching history for extra patterns and adding extra literals")
    ok(f"extra pattern matches: {collect_from_extra_patterns(ledger, workspace.original, settings.extra_secret_patterns)}")
    ok(f"extra literals: {collect_extra_literals(ledger, settings.extra_literals_file)}")

    say(f"Keeping values still present on {settings.reference_branch} (replacing them would break the apps)")
    kept = keep_values_still_on_reference_branch(ledger, workspace.original, settings.reference_branch)
    ok(f"kept: {len(kept)}")

    values = ledger.values_longest_first()
    if not values:
        fail("no secret values found, nothing to clean")
    now = datetime.now(settings.replacement_timezone)
    replacement = settings.replacement_template.replace("{timestamp}", f"{now:%Y-%m-%d %H:%M} {settings.replacement_timezone_label}")
    write_lines(workspace.values_file, values)
    write_lines(workspace.replacements_file, [f"literal:{value}==>{replacement}" for value in values])
    workspace.replacement_text_file.write_text(replacement, encoding="utf-8")

    unvalidated = live_keys_outside_validation(ledger, workspace.original, settings)
    write_find_reports(ledger, workspace, kept, unvalidated)

    ok(f"secret keys found: {len(ledger.secret_keys())}")
    ok(f"distinct values to remove: {len(values)}")
    ok(f"replacement text: {replacement}")
    ok(f"reports (key names and lengths only, no values): {workspace.reports}")
    if unvalidated:
        info(f"{len(unvalidated)} secret key(s) still live but not in {settings.validation_file}: {', '.join(unvalidated)}")
        info("the rewrite step refuses until they are validated, or you pass --allow-unvalidated-keys")
