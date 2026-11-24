"""Turns command-line options into one immutable Settings object shared by every step."""

import argparse
import re
from dataclasses import dataclass, replace
from datetime import timedelta, timezone
from pathlib import Path

from git_history_purge.console import fail
from git_history_purge.git import default_branch
from git_history_purge.workspace import Workspace


@dataclass(frozen=True)
class Settings:
    repo_url: str
    reference_branch: str
    dropped_ref_prefixes: list[str]
    replacement_template: str
    replacement_timezone: timezone
    replacement_timezone_label: str
    min_secret_length: int
    secret_key_pattern: re.Pattern[str]
    config_file_pattern: re.Pattern[str]
    gitleaks_ignored_files: re.Pattern[str]
    extra_secret_patterns: list[re.Pattern[bytes]]
    extra_literals_file: Path | None
    removed_paths: list[str]
    validation_file: str
    validation_key_pattern: re.Pattern[str] | None
    validation_config_dir: str
    allow_unvalidated_keys: bool
    full_checks: bool
    work_dir: Path


def parse_utc_offset(offset_text: str) -> timezone:
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", offset_text)
    if match is None:
        fail(f"--timezone-offset must look like +05:30 or -08:00, got '{offset_text}'")
    sign = 1 if match.group(1) == "+" else -1
    return timezone(sign * timedelta(hours=int(match.group(2)), minutes=int(match.group(3))))


def repo_name_from_url(repo_url: str) -> str:
    last_part = re.split(r"[/\\:]", repo_url.rstrip("/\\"))[-1]
    return re.sub(r"\.git$", "", last_part) or "repo"


def settings_from_options(options: argparse.Namespace) -> Settings:
    has_validation_file = options.validation_file != ""
    return Settings(
        repo_url=options.repo_url,
        reference_branch=options.reference_branch,
        dropped_ref_prefixes=options.drop_ref_prefix or ["refs/pull/"],
        replacement_template=options.replacement_text,
        replacement_timezone=parse_utc_offset(options.timezone_offset),
        replacement_timezone_label=options.timezone_label,
        min_secret_length=options.min_secret_length,
        secret_key_pattern=re.compile(options.secret_key_pattern),
        config_file_pattern=re.compile(options.config_file_pattern),
        gitleaks_ignored_files=re.compile(options.gitleaks_ignored_files),
        extra_secret_patterns=[re.compile(pattern.encode()) for pattern in options.extra_secret_pattern],
        extra_literals_file=Path(options.extra_literals_file) if options.extra_literals_file else None,
        removed_paths=options.remove_path,
        validation_file=options.validation_file,
        validation_key_pattern=re.compile(options.validation_key_pattern, re.MULTILINE) if has_validation_file else None,
        validation_config_dir=options.validation_config_dir,
        allow_unvalidated_keys=options.allow_unvalidated_keys,
        full_checks=options.full,
        work_dir=Path(options.work_dir or Path("purge-work") / repo_name_from_url(options.repo_url)).resolve(),
    )


def with_reference_branch(settings: Settings, workspace: Workspace) -> Settings:
    if settings.reference_branch != "" or not workspace.original.is_dir():
        return settings
    return replace(settings, reference_branch=default_branch(workspace.original))
