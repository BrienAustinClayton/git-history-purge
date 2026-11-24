"""Command-line interface: parses the options and runs the chosen step or combined run."""

import argparse
import os
import sys

from git_history_purge import __version__
from git_history_purge.console import StepFailed
from git_history_purge.defaults import (
    DEFAULT_CONFIG_FILE_PATTERN,
    DEFAULT_GITLEAKS_IGNORED_FILES,
    DEFAULT_REPLACEMENT,
    DEFAULT_SECRET_KEY_PATTERN,
    DEFAULT_VALIDATION_KEY_PATTERN,
)
from git_history_purge.settings import settings_from_options, with_reference_branch
from git_history_purge.steps import COMBINED_STEPS, STEPS
from git_history_purge.workspace import Workspace


def build_parser() -> argparse.ArgumentParser:
    step_help = "\n".join(f"  {name:<9} {description}" for name, (_, description) in STEPS.items())
    combined_help = "\n".join(f"  {name:<9} {' -> '.join(steps)}" for name, steps in COMBINED_STEPS.items())
    parser = argparse.ArgumentParser(
        prog="git-history-purge",
        description="Remove secrets from the whole git history of a repository and replace the history on its remote.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"steps:\n{step_help}\n{combined_help}\n\nexample:\n  git-history-purge test --repo-url https://github.com/org/repo.git\n  python3 -m git_history_purge test --repo-url https://github.com/org/repo.git",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("step", choices=[*STEPS, *COMBINED_STEPS])
    parser.add_argument("--repo-url", required=True, help="remote to clean: HTTPS, SSH or a local path")
    parser.add_argument("--reference-branch", default="", help="branch whose CURRENT files must stay identical; values on it are kept (default: the remote's default branch)")
    parser.add_argument("--replacement-text", default=DEFAULT_REPLACEMENT, help="text that replaces each secret; {timestamp} is filled in")
    parser.add_argument("--timezone-offset", default="+00:00", help="timezone of {timestamp}, e.g. +05:30 (default: +00:00)")
    parser.add_argument("--timezone-label", default="UTC", help="label after {timestamp}, e.g. IST (default: UTC)")
    parser.add_argument("--remove-path", action="append", default=[], help="glob deleted from every commit, e.g. 'dist/*' or 'node_modules/*' (repeatable)")
    parser.add_argument("--extra-secret-pattern", action="append", default=[], help="regex searched in every diff, e.g. 'sk_live_[A-Za-z0-9]{20,}' (repeatable)")
    parser.add_argument("--extra-literals-file", default="", help="file with one extra value to remove per line")
    parser.add_argument("--min-secret-length", type=int, default=8, help="shorter values are skipped (default: 8)")
    parser.add_argument("--secret-key-pattern", default=DEFAULT_SECRET_KEY_PATTERN, help="regex for config keys that hold secrets")
    parser.add_argument("--config-file-pattern", default=DEFAULT_CONFIG_FILE_PATTERN, help="regex for config files read in every old version")
    parser.add_argument("--gitleaks-ignored-files", default=DEFAULT_GITLEAKS_IGNORED_FILES, help="regex for files whose gitleaks hits are ignored")
    parser.add_argument("--drop-ref-prefix", action="append", default=[], help="read-only refs dropped after download (default: refs/pull/)")
    parser.add_argument("--validation-file", default="", help="optional: file listing validated env keys; rewrite stops if a live secret key is missing from it")
    parser.add_argument("--validation-key-pattern", default=DEFAULT_VALIDATION_KEY_PATTERN, help="regex capturing key names in --validation-file (default: every UPPER_CASE name)")
    parser.add_argument("--validation-config-dir", default="", help="folder whose config files hold the live keys for --validation-file")
    parser.add_argument("--allow-unvalidated-keys", action="store_true", help="continue although live secret keys are not in --validation-file")
    parser.add_argument("--full", action="store_true", help="verify: also re-run gitleaks on the rewritten copy (slow)")
    parser.add_argument("--work-dir", default="", help="work folder (default: ./purge-work/<repo name>)")
    return parser


def main() -> int:
    os.umask(0o077)
    sys.stdout.reconfigure(line_buffering=True)
    options = build_parser().parse_args()
    step_names = COMBINED_STEPS.get(options.step, [options.step])
    try:
        settings = settings_from_options(options)
        workspace = Workspace(settings.work_dir)
        print(f"Remote: {settings.repo_url}   Work folder: {workspace.root}")
        for step_name in step_names:
            print(f"\n######## {step_name}")
            if step_name != "fetch":
                settings = with_reference_branch(settings, workspace)
            STEPS[step_name][0](settings, workspace)
    except StepFailed as stop:
        print(f"\n  [STOP] {stop}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n  [STOP] interrupted. Nothing was pushed unless the push step said so.", file=sys.stderr)
        return 130
    print(f"\nFinished: {options.step}.")
    return 0
