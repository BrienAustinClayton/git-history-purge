"""Thin wrappers around the git command line: cloning, listing refs, reading blobs, comparing copies."""

import re
import shutil
import subprocess
from pathlib import Path

from git_history_purge.console import fail
from git_history_purge.defaults import MINIMUM_GIT_VERSION


def run_git(*args: str, repo: Path | None = None, input_bytes: bytes | None = None) -> bytes:
    repo_args = ["-C", str(repo)] if repo is not None else []
    completed = subprocess.run(["git", *repo_args, *args], input=input_bytes, capture_output=True)
    if completed.returncode != 0:
        fail(f"'git {' '.join(args)}' failed:\n{completed.stderr.decode('utf-8', 'replace').strip()}")
    return completed.stdout


def git_text(*args: str, repo: Path | None = None) -> str:
    return run_git(*args, repo=repo).decode("utf-8", "replace")


def require_tools(*tools: str) -> None:
    for tool in tools:
        if tool == "git-filter-repo":
            is_installed = subprocess.run(["git", "filter-repo", "--version"], capture_output=True).returncode == 0
        else:
            is_installed = shutil.which(tool) is not None
        if not is_installed:
            fail(f"{tool} is not installed (see the Install section of the README)")
    if "git" in tools:
        version_text = git_text("--version")
        match = re.search(r"(\d+)\.(\d+)", version_text)
        version = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
        if version < MINIMUM_GIT_VERSION:
            fail(f"git {MINIMUM_GIT_VERSION[0]}.{MINIMUM_GIT_VERSION[1]}+ is needed (reftable refs), found: {version_text.strip()}")


def mirror_clone(source: str | Path, destination: Path, copy_objects: bool = True) -> None:
    local_flags = ["--no-local"] if copy_objects else []
    run_git("clone", "--quiet", "--mirror", "--ref-format=reftable", *local_flags, str(source), str(destination))


def delete_refs_with_prefix(repo: Path, prefix: str) -> int:
    refs = git_text("for-each-ref", "--format=%(refname)", prefix, repo=repo).split()
    if refs:
        run_git("update-ref", "--stdin", repo=repo, input_bytes="".join(f"delete {ref}\n" for ref in refs).encode())
    return len(refs)


def branch_and_tag_refs(repo: Path) -> list[str]:
    output = git_text("for-each-ref", "--format=%(objectname)%09%(refname)", "refs/heads/", "refs/tags/", repo=repo)
    return sorted(output.splitlines())


def remote_branch_and_tag_refs(remote_url: str) -> list[str]:
    output = git_text("ls-remote", remote_url, "refs/heads/*", "refs/tags/*")
    return sorted(line for line in output.splitlines() if not line.endswith("^{}"))


def remote_refs_with_prefixes(remote_url: str, prefixes: list[str]) -> list[str]:
    output = git_text("ls-remote", remote_url, *(f"{prefix}*" for prefix in prefixes))
    return sorted(line.split("\t", 1)[1] for line in output.splitlines())


def ref_names(refs: list[str] | set[str]) -> set[str]:
    return {line.split("\t", 1)[1] for line in refs}


def commit_count(repo: Path) -> int:
    return int(git_text("rev-list", "--all", "--count", repo=repo).strip())


def branch_exists(repo: Path, branch: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], capture_output=True
    )
    return completed.returncode == 0


def default_branch(repo: Path) -> str:
    return git_text("symbolic-ref", "--short", "HEAD", repo=repo).strip()


def branch_commit(repo: Path, branch: str) -> str:
    return git_text("rev-parse", f"refs/heads/{branch}", repo=repo).strip()


def files_changed_between(before_repo: Path, after_repo: Path, branch: str) -> list[str]:
    before = set(git_text("ls-tree", "-r", f"refs/heads/{branch}", repo=before_repo).splitlines())
    after = set(git_text("ls-tree", "-r", f"refs/heads/{branch}", repo=after_repo).splitlines())
    return sorted({line.split("\t", 1)[1] for line in before ^ after})


def count_values_still_present(repo: Path, values: list[str]) -> int:
    history = run_git("cat-file", "--batch-all-objects", "--batch", repo=repo)
    return sum(1 for value in values if value.encode() in history)


def read_blobs(repo: Path, object_names: list[str]) -> dict[str, bytes]:
    output = run_git("cat-file", "--batch", repo=repo, input_bytes="\n".join(object_names).encode() + b"\n")
    contents = {}
    cursor = 0
    for object_name in object_names:
        header_end = output.index(b"\n", cursor)
        header = output[cursor:header_end].decode().split(" ")
        if header[-1] == "missing":
            cursor = header_end + 1
            continue
        body_start = header_end + 1
        body_end = body_start + int(header[2])
        if header[1] == "blob":
            contents[object_name] = output[body_start:body_end]
        cursor = body_end + 1
    return contents
