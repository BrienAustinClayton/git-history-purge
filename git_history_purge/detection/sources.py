"""The places secrets are collected from: gitleaks, every old version of config files, extra patterns and extra literals."""

import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from git_history_purge.console import fail
from git_history_purge.detection.ledger import SecretLedger
from git_history_purge.detection.rules import (
    ASSIGNMENT_PATTERN,
    GITLEAKS_KEY_PATTERN,
    INCLUDED,
    LOCAL_HOSTS,
    URL_PASSWORD_PATTERN,
    classify_value,
    strip_quotes_and_comment,
)
from git_history_purge.git import git_text, read_blobs
from git_history_purge.settings import Settings


def collect_from_config_files(ledger: SecretLedger, repo: Path, settings: Settings) -> int:
    paths_by_blob = defaultdict(set)
    for line in git_text("rev-list", "--all", "--objects", repo=repo).splitlines():
        object_name, _, path = line.partition(" ")
        if path != "" and settings.config_file_pattern.search(path):
            paths_by_blob[object_name].add(path)
    contents_by_blob = read_blobs(repo, sorted(paths_by_blob))

    def consider(key: str, value: str, source: str) -> None:
        decision = classify_value(value, settings.min_secret_length)
        if decision == INCLUDED:
            ledger.add_value(value, source, key)
            return
        ledger.record_skip(key, decision)

    for blob, content in contents_by_blob.items():
        for line in content.decode("utf-8", "replace").splitlines():
            assignment = ASSIGNMENT_PATTERN.match(line)
            if assignment is None:
                continue
            key, value = assignment.group(1), strip_quotes_and_comment(assignment.group(2))
            if settings.secret_key_pattern.search(key) is None:
                ledger.keys_not_treated_as_secret.add(key)
                continue
            ledger.files_by_key[key].update(paths_by_blob[blob])
            consider(key, value, f"key:{key}")
            url_password = URL_PASSWORD_PATTERN.match(value)
            is_remote_url_with_password = url_password is not None and url_password.group(2) not in LOCAL_HOSTS
            if is_remote_url_with_password:
                consider(key, url_password.group(1), f"key:{key}:url-password")
    return len(contents_by_blob)


def run_gitleaks(repo: Path, report_path: Path) -> list[dict]:
    subprocess.run(
        [
            "gitleaks", "git", str(repo), "--log-opts=--all", "--report-format", "json",
            "--report-path", str(report_path), "--exit-code", "0", "--no-banner", "--log-level", "error",
        ],
        check=True,
    )
    return json.loads(report_path.read_text(encoding="utf-8") or "[]")


def collect_from_gitleaks(ledger: SecretLedger, findings: list[dict], settings: Settings) -> None:
    for finding in findings:
        file_path = finding.get("File", "")
        rule = finding.get("RuleID", "")
        secret = finding.get("Secret", "")
        key_match = GITLEAKS_KEY_PATTERN.search(finding.get("Match", ""))
        candidate_key = key_match.group(1) if key_match else ""
        is_real_key = candidate_key != "" and candidate_key not in secret and secret not in candidate_key
        key = candidate_key if is_real_key else ""

        if settings.gitleaks_ignored_files.search(file_path):
            ledger.gitleaks_rows.add((rule, file_path, key, "ignored file"))
            continue
        decision = classify_value(secret, settings.min_secret_length)
        ledger.gitleaks_rows.add((rule, file_path, key, decision))
        if decision != INCLUDED:
            continue
        ledger.add_value(secret, f"gitleaks:{rule}", key)
        if key != "":
            ledger.files_by_key[key].add(file_path)
        if key == "":
            ledger.gitleaks_findings_without_key.add(f"{rule}\t{file_path}")


def collect_from_extra_patterns(ledger: SecretLedger, repo: Path, patterns: list[re.Pattern[bytes]]) -> int:
    if not patterns:
        return 0
    found = set()
    history = subprocess.Popen(["git", "-C", str(repo), "log", "--all", "-p", "--no-color"], stdout=subprocess.PIPE)
    for line in history.stdout:
        for pattern in patterns:
            found.update(match.decode("utf-8", "replace") for match in pattern.findall(line))
    history.wait()
    for value in found:
        ledger.add_value(value, "extra-pattern")
    return len(found)


def collect_extra_literals(ledger: SecretLedger, literals_file: Path | None) -> int:
    if literals_file is None:
        return 0
    if not literals_file.is_file():
        fail(f"--extra-literals-file {literals_file} does not exist")
    literals = {line.strip() for line in literals_file.read_text(encoding="utf-8").splitlines() if line.strip()}
    for literal in literals:
        ledger.add_value(literal, "extra-literals-file")
    return len(literals)
