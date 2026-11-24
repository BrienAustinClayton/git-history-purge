import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REMOVED_VALUES = ["Sup3rS3cretPassw0rd", "JavaAppSecret99887766", "Rem0tePassw0rdXyz"]
KEPT_VALUE = "keepThisValue123456"


def git_version_is_supported() -> bool:
    if shutil.which("git") is None:
        return False
    output = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
    match = re.search(r"(\d+)\.(\d+)", output)
    return match is not None and (int(match.group(1)), int(match.group(2))) >= (2, 45)


def filter_repo_is_installed() -> bool:
    if shutil.which("git") is None:
        return False
    return subprocess.run(["git", "filter-repo", "--version"], capture_output=True).returncode == 0


tools_are_missing = shutil.which("gitleaks") is None or not filter_repo_is_installed() or not git_version_is_supported()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(tools_are_missing, reason="needs gitleaks, git-filter-repo and git 2.45+"),
]


def run_git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout


def write_file(repo: Path, relative_path: str, content: str) -> None:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def build_remote_with_leaked_secrets(base: Path) -> Path:
    source = base / "src"
    source.mkdir()
    run_git(source, "init", "-q", "-b", "main")
    run_git(source, "config", "user.email", "t@example.com")
    run_git(source, "config", "user.name", "t")
    write_file(
        source,
        ".env",
        "DB_PASSWORD=Sup3rS3cretPassw0rd\nAPI_KEY=abcdEFGH12345678xyz\nDATABASE_URL=postgres://app:Rem0tePassw0rdXyz@db.example.com/app\n",
    )
    write_file(source, "config/application.yml", "spring:\n  DATASOURCE_PASSWORD: JavaAppSecret99887766\n")
    write_file(source, "prod.properties", "STRIPE_SECRET_KEY=Str1peTestOnlyValue0042\n")
    write_file(source, "keep.env", f"PUBLIC_API_KEY={KEPT_VALUE}\n")
    write_file(source, "README.md", "hello\n")
    run_git(source, "add", "-A")
    run_git(source, "commit", "-q", "-m", "init")
    run_git(source, "checkout", "-q", "-b", "feature")
    write_file(source, "README.md", "hello\nx\n")
    run_git(source, "commit", "-qam", "feat")
    run_git(source, "tag", "v1")
    run_git(source, "checkout", "-q", "main")
    run_git(source, "rm", "-q", ".env", "config/application.yml", "prod.properties")
    run_git(source, "commit", "-q", "-m", "remove secrets")
    remote = base / "remote.git"
    run_git(base, "clone", "-q", "--mirror", "--ref-format=reftable", str(source), str(remote))
    return remote


def test_combined_test_run_removes_secrets_and_keeps_allowed_values(tmp_path: Path) -> None:
    remote = build_remote_with_leaked_secrets(tmp_path)
    work_dir = tmp_path / "work"

    result = subprocess.run(
        [sys.executable, "-m", "git_history_purge", "test", "--repo-url", str(remote), "--work-dir", str(work_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "kept: 1" in result.stdout
    assert "distinct values to remove: 6" in result.stdout
    assert "rehearsal passed" in result.stdout

    cleaned_history = run_git(work_dir / "3-cleaned.git", "log", "--all", "-p")
    for removed_value in REMOVED_VALUES:
        assert removed_value not in cleaned_history
    assert KEPT_VALUE in cleaned_history
