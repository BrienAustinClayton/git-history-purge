import re
import subprocess
import sys
from pathlib import Path

import pytest

from git_history_purge import __version__
from git_history_purge.defaults import DEFAULT_CONFIG_FILE_PATTERN, DEFAULT_GITLEAKS_IGNORED_FILES

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.production",
        "apps/api/.env.local",
        "prod.env",
        "settings.properties",
        "conf/app.ini",
        "deploy/app.cfg",
        "server.conf",
        "infra/prod.tfvars",
        "config/application.yml",
        "docker-compose.yaml",
        "helm/values.yaml",
        "credentials.yml",
    ],
)
def test_config_file_pattern_matches_secret_bearing_files(path: str) -> None:
    assert re.search(DEFAULT_CONFIG_FILE_PATTERN, path) is not None


@pytest.mark.parametrize(
    "path",
    ["README.md", "src/main.py", "package.json", "docs/environment.md", "data.yml", "envfile.txt"],
)
def test_config_file_pattern_ignores_ordinary_files(path: str) -> None:
    assert re.search(DEFAULT_CONFIG_FILE_PATTERN, path) is None


@pytest.mark.parametrize(
    "path",
    [
        "pnpm-lock.yaml",
        "apps/web/package-lock.json",
        "deep/nested/dir/yarn.lock",
        "bun.lockb",
        "Cargo.lock",
        "services/api/go.sum",
        "poetry.lock",
        "mobile/ios/Podfile.lock",
    ],
)
def test_gitleaks_ignored_files_match_nested_lock_files(path: str) -> None:
    assert re.search(DEFAULT_GITLEAKS_IGNORED_FILES, path) is not None


@pytest.mark.parametrize("path", ["my-pnpm-lock.yaml", "yarn.lock.bak", "src/lock.py", "go.summary"])
def test_gitleaks_ignored_files_do_not_match_lookalikes(path: str) -> None:
    assert re.search(DEFAULT_GITLEAKS_IGNORED_FILES, path) is None


def test_version_flag_prints_program_name_and_version() -> None:
    result = subprocess.run([sys.executable, "-m", "git_history_purge", "--version"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == f"git-history-purge {__version__}"
