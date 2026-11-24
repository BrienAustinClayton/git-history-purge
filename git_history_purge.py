"""
git_history_purge.py - remove secrets from the WHOLE git history of a repository and replace the history on its remote.

One file, no config needed. Runs on Windows, macOS and Linux.

Needs: Python 3.11+, git 2.45+, git-filter-repo, gitleaks 8.19+
  macOS:   brew install git git-filter-repo gitleaks
  Windows: install git (git-scm.com), then: pip install git-filter-repo ; winget install gitleaks
  Linux:   distro git, pip install git-filter-repo, gitleaks release binary

Usage (always the same --repo-url and options for every step of one purge):
  python git_history_purge.py test    --repo-url <url>      # safe dry run: fetch, find, rewrite, verify, rehearse
  python git_history_purge.py push    --repo-url <url>      # the one real change (asks you to type PUSH)
  python git_history_purge.py all     --repo-url <url>      # test + push in one go
  python git_history_purge.py cleanup --repo-url <url>      # delete the work folder (it holds the original secrets)

Try it on a local copy first:
  git clone --mirror --ref-format=reftable <url> local-copy.git
  python git_history_purge.py all --repo-url local-copy.git
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("Python 3.11 or newer is needed (python --version)")

MINIMUM_GIT_VERSION = (2, 45)
DEFAULT_SECRET_KEY_PATTERN = (
    r"(SECRET(_KEY)?$|PASSWORD|PASSWD|(^|_)TOKEN($|_)|API_KEY|APIKEY|PRIVATE_KEY|ACCESS_KEY"
    r"|KEY_ID|CLIENT_ID|DSN$|DATABASE_URL|_KEY$|[a-z](Key|Token|Secret)$)"
)
DEFAULT_CONFIG_FILE_PATTERN = r"(^|/)(\.env[^/]*|[^/]*-config\.ya?ml)$"
DEFAULT_GITLEAKS_IGNORED_FILES = r"(pnpm-lock\.yaml|package-lock\.json|yarn\.lock)$"
DEFAULT_REPLACEMENT = "[SECRET REMOVED FROM GIT {timestamp}]"
DEFAULT_BEFORE_PUSH_CHECKLIST = [
    "Every secret the apps still need lives in a secrets manager (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault, ...) and the apps read it from there",
    "CI/CD pipelines that deploy on push or tag are DISABLED",
    "The team was told to stop pushing",
    "Open pull requests are completed or abandoned",
    "The account you push with may force-push to every branch, including protected ones",
]
DEFAULT_AFTER_PUSH_CHECKLIST = [
    "Re-enable the pipelines",
    "Everyone deletes their old clone and re-clones (never pull or push from an old clone)",
    "Rotate every removed secret",
    "Run the cleanup step",
]

ASSIGNMENT_PATTERN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*?)\s*$")
URL_PASSWORD_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^:/@\s]+:([^@\s]+)@([^/:?\s]+)")
GITLEAKS_KEY_PATTERN = re.compile(r"^\s*(?:export\s+)?[\"']?([A-Za-z_][A-Za-z0-9_]{1,60})[\"']?\s*[:=]")
ENV_STYLE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "postgres", "db", "host.docker.internal"}
COMMON_NON_SECRET_VALUES = {
    "postgres", "postgresql", "password", "localhost", "changeme", "development",
    "production", "undefined", "null", "true", "false", "secret", "example",
}
PLACEHOLDER_PATTERNS = [
    re.compile(r"^<.*>$"),
    re.compile(r"^\$\{.*\}$"),
    re.compile(r"^\$\(.*\)$"),
    re.compile(r"^\{\{.*\}\}$"),
    re.compile(r"(your[_-]|xxxx|change[_-]?me|placeholder|REMOVED AT|\*\*\*REMOVED|SECRET REMOVED)", re.IGNORECASE),
]
INCLUDED = "included"


class StepFailed(Exception):
    pass


def say(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def ok(message: str) -> None:
    print(f"  [ok]   {message}", flush=True)


def info(message: str) -> None:
    print(f"  [info] {message}", flush=True)


def fail(message: str) -> None:
    raise StepFailed(message)


def require_typed_word(prompt: str, word: str) -> None:
    answer = input(f"{prompt} Type {word} to continue: ").strip()
    if answer != word:
        fail("not confirmed. Nothing was changed.")


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


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def original(self) -> Path:
        return self.root / "1-original.git"

    @property
    def cleaned(self) -> Path:
        return self.root / "3-cleaned.git"

    @property
    def rehearsal_remote(self) -> Path:
        return self.root / "5-rehearsal-remote.git"

    @property
    def rehearsal_clone(self) -> Path:
        return self.root / "5-rehearsal-fresh-clone.git"

    @property
    def secrets(self) -> Path:
        return self.root / "secrets"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def gitleaks_before(self) -> Path:
        return self.secrets / "gitleaks-before.json"

    @property
    def gitleaks_after(self) -> Path:
        return self.secrets / "gitleaks-after.json"

    @property
    def values_file(self) -> Path:
        return self.secrets / "values.txt"

    @property
    def replacements_file(self) -> Path:
        return self.secrets / "replacements.txt"

    @property
    def replacement_text_file(self) -> Path:
        return self.secrets / "replacement-text.txt"

    @property
    def refs_at_fetch(self) -> Path:
        return self.reports / "refs-at-fetch.txt"

    @property
    def fetched_from(self) -> Path:
        return self.reports / "fetched-from.txt"

    @property
    def unvalidated_live_keys(self) -> Path:
        return self.reports / "live-keys-outside-validation.txt"

    @property
    def rehearsal_passed(self) -> Path:
        return self.reports / "rehearsal-passed-for-refs.txt"

    def create_private_folders(self) -> None:
        for folder in (self.root, self.secrets, self.reports):
            folder.mkdir(parents=True, exist_ok=True)
            os.chmod(folder, 0o700)


def make_writable_and_retry(function, path, _error) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


def remove_tree(path: Path) -> None:
    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=make_writable_and_retry)
        return
    shutil.rmtree(path, onerror=make_writable_and_retry)


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")


def read_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").split("\n") if line != ""]


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
            fail(f"{tool} is not installed (see the top of this file)")
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


def with_reference_branch(settings: Settings, workspace: Workspace) -> Settings:
    if settings.reference_branch != "" or not workspace.original.is_dir():
        return settings
    return replace(settings, reference_branch=default_branch(workspace.original))


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


@dataclass
class SecretLedger:
    sources_by_value: dict[str, set[str]] = field(default_factory=dict)
    values_by_key: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    files_by_key: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    skip_counts_by_key: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    keys_not_treated_as_secret: set[str] = field(default_factory=set)
    gitleaks_rows: set[tuple[str, str, str, str]] = field(default_factory=set)
    gitleaks_findings_without_key: set[str] = field(default_factory=set)

    def add_value(self, value: str, source: str, key: str = "") -> None:
        self.sources_by_value.setdefault(value, set()).add(source)
        if key != "":
            self.values_by_key[key].add(value)

    def record_skip(self, key: str, reason: str) -> None:
        self.skip_counts_by_key[key][reason] += 1

    def remove_values(self, values: set[str]) -> dict[str, set[str]]:
        return {value: self.sources_by_value.pop(value) for value in values}

    def secret_keys(self) -> list[str]:
        return sorted(set(self.values_by_key) | set(self.files_by_key) | set(self.skip_counts_by_key))

    def values_longest_first(self) -> list[str]:
        return sorted(self.sources_by_value, key=lambda value: (-len(value), value))


def strip_quotes_and_comment(raw_value: str) -> str:
    is_quoted = len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in "\"'"
    if is_quoted:
        return raw_value[1:-1]
    return raw_value.split(" #", 1)[0].strip()


def classify_value(value: str, min_length: int) -> str:
    url_match = URL_PASSWORD_PATTERN.match(value)
    is_too_short = len(value) < min_length
    is_placeholder = any(pattern.search(value) for pattern in PLACEHOLDER_PATTERNS)
    is_common_word = value.lower() in COMMON_NON_SECRET_VALUES
    is_plain_lowercase_word = value.isalpha() and value.islower() and len(value) < 16
    cannot_be_replace_text_literal = "==>" in value or "\n" in value or "\r" in value
    is_local_url = url_match is not None and url_match.group(2) in LOCAL_HOSTS

    if is_too_short:
        return "skipped: shorter than minimum length"
    if is_placeholder:
        return "skipped: placeholder"
    if is_common_word or is_plain_lowercase_word:
        return "skipped: common word"
    if cannot_be_replace_text_literal:
        return "skipped: cannot be a replace-text literal"
    if is_local_url:
        return "skipped: local development URL"
    return INCLUDED


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


def keep_values_still_on_reference_branch(ledger: SecretLedger, repo: Path, branch: str) -> dict[str, set[str]]:
    paths = git_text("ls-tree", "-r", "--name-only", f"refs/heads/{branch}", repo=repo).splitlines()
    current_contents = b"\n".join(read_blobs(repo, [f"refs/heads/{branch}:{path}" for path in paths]).values())
    still_used = {value for value in ledger.sources_by_value if value.encode() in current_contents}
    return ledger.remove_values(still_used)


def live_keys_outside_validation(ledger: SecretLedger, repo: Path, settings: Settings) -> list[str]:
    if settings.validation_key_pattern is None:
        return []
    branch_ref = f"refs/heads/{settings.reference_branch}"
    validated_keys = set(settings.validation_key_pattern.findall(git_text("show", f"{branch_ref}:{settings.validation_file}", repo=repo)))
    paths = git_text("ls-tree", "-r", "--name-only", branch_ref, repo=repo).splitlines()
    config_paths = [
        path for path in paths
        if path.startswith(settings.validation_config_dir) and settings.config_file_pattern.search(path)
    ]
    contents = read_blobs(repo, [f"{branch_ref}:{path}" for path in config_paths]).values()
    lines = [line for content in contents for line in content.decode("utf-8", "replace").splitlines()]
    live_keys = {match.group(1) for match in map(ASSIGNMENT_PATTERN.match, lines) if match is not None}
    return [
        key for key in ledger.secret_keys()
        if ENV_STYLE_KEY_PATTERN.match(key) and key in live_keys and key not in validated_keys
    ]


def write_find_reports(ledger: SecretLedger, workspace: Workspace, kept: dict[str, set[str]], unvalidated: list[str]) -> None:
    reports = workspace.reports
    key_rows = ["key\tvalues_to_remove\tskipped\tfiles"]
    for key in ledger.secret_keys():
        skipped = "; ".join(f"{reason} x{count}" for reason, count in sorted(ledger.skip_counts_by_key[key].items()))
        key_rows.append(f"{key}\t{len(ledger.values_by_key[key])}\t{skipped}\t{', '.join(sorted(ledger.files_by_key[key]))}")
    write_lines(reports / "secret-keys.tsv", key_rows)
    write_lines(reports / "gitleaks-findings.tsv", ["rule\tfile\tkey\tdecision", *map("\t".join, sorted(ledger.gitleaks_rows))])
    write_lines(reports / "gitleaks-findings-without-key.tsv", sorted(ledger.gitleaks_findings_without_key))
    write_lines(reports / "keys-not-treated-as-secret.txt", sorted(ledger.keys_not_treated_as_secret))
    write_lines(
        reports / "kept-values-still-on-reference-branch.txt",
        [f"length={len(value)}\tsources={','.join(sorted(sources))}" for value, sources in kept.items()],
    )
    write_lines(workspace.unvalidated_live_keys, unvalidated)


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


def push_or_stop(workspace: Workspace, target: str, refspecs: list[str], force_flag: str, refused_message: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(workspace.cleaned), "push", "--quiet", force_flag, target, *refspecs], capture_output=True
    )
    if completed.returncode != 0:
        fail(f"{refused_message}\n{completed.stderr.decode('utf-8', 'replace').strip()}")


def push_cleaned_history(settings: Settings, workspace: Workspace, target: str) -> None:
    branch = settings.reference_branch
    branch_at_fetch = branch_commit(workspace.original, branch)
    rewritten_branch_line = f"{branch_commit(workspace.cleaned, branch)}\trefs/heads/{branch}"

    say(f"1/3 Pushing {branch} first (if this is refused, nothing else is pushed)")
    if rewritten_branch_line in remote_branch_and_tag_refs(target):
        ok(f"{branch} was already pushed")
    else:
        push_or_stop(
            workspace, target, [f"refs/heads/{branch}:refs/heads/{branch}"],
            f"--force-with-lease=refs/heads/{branch}:{branch_at_fetch}",
            f"{branch} was refused (check WHICH account pushed in the error below, and its force-push/bypass permission). Nothing was pushed.",
        )
        ok(f"{branch} pushed")

    say("2/3 Pushing all other branches")
    push_or_stop(
        workspace, target, ["refs/heads/*:refs/heads/*"], "--force",
        f"some branches were refused. {branch} is pushed. Fix the cause and run the push step again; it resumes.",
    )
    ok("branches pushed")

    say("3/3 Pushing all tags")
    push_or_stop(
        workspace, target, ["refs/tags/*:refs/tags/*"], "--force",
        "some tags were refused. Branches are pushed. Fix the cause and run the push step again; it resumes.",
    )
    ok("tags pushed")


def require_remote_matches_cleaned_copy(workspace: Workspace, target: str) -> None:
    if remote_branch_and_tag_refs(target) != branch_and_tag_refs(workspace.cleaned):
        fail(f"after the push, {target} does not match the rewritten copy. Compare with: git ls-remote {target}")
    ok("every branch and tag on the remote now points at the rewritten history")


def step_fetch(settings: Settings, workspace: Workspace) -> None:
    require_tools("git")
    workspace.create_private_folders()

    say(f"Downloading every branch and tag from {settings.repo_url}")
    remove_tree(workspace.original)
    mirror_clone(settings.repo_url, workspace.original)
    reference_branch = settings.reference_branch or default_branch(workspace.original)
    ok(f"reference branch: {reference_branch}" + ("" if settings.reference_branch else " (the remote's default branch)"))
    for prefix in settings.dropped_ref_prefixes:
        ok(f"dropped {delete_refs_with_prefix(workspace.original, prefix)} read-only {prefix}* refs (they cannot be pushed back)")
    if not branch_exists(workspace.original, reference_branch):
        fail(f"branch {reference_branch} not found in {settings.repo_url}")

    workspace.fetched_from.write_text(settings.repo_url, encoding="utf-8")
    refs = branch_and_tag_refs(workspace.original)
    write_lines(workspace.refs_at_fetch, refs)
    ok(f"branches + tags downloaded: {len(refs)}")
    ok(f"commits downloaded: {commit_count(workspace.original)}")


def step_find(settings: Settings, workspace: Workspace) -> None:
    require_tools("git", "gitleaks")
    if not workspace.original.is_dir():
        fail("run the fetch step first")
    ledger = SecretLedger()

    say("Scanning every commit with gitleaks (a few minutes on a big repo)")
    findings = run_gitleaks(workspace.original, workspace.gitleaks_before)
    collect_from_gitleaks(ledger, findings, settings)
    ok(f"gitleaks findings: {len(findings)}")

    say("Reading every old version of config files (.env, *-config.yml, ...)")
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


def step_rewrite(settings: Settings, workspace: Workspace) -> None:
    require_tools("git", "git-filter-repo")
    has_replacements = workspace.replacements_file.is_file() and workspace.replacements_file.stat().st_size > 0
    unvalidated = read_lines(workspace.unvalidated_live_keys) if workspace.unvalidated_live_keys.is_file() else []
    if not has_replacements:
        fail("run the find step first")
    if unvalidated and not settings.allow_unvalidated_keys:
        fail(f"secret keys still live but not validated: {', '.join(unvalidated)}. Validate them, or pass --allow-unvalidated-keys")

    say("Making a fresh copy to rewrite (the download stays untouched for comparison)")
    remove_tree(workspace.cleaned)
    mirror_clone(workspace.original, workspace.cleaned)

    say("Rewriting history (file contents and commit messages)")
    removed_path_args = [arg for path in settings.removed_paths for arg in ("--path-glob", path)]
    invert_args = ["--invert-paths"] if removed_path_args else []
    run_git(
        "filter-repo", "--force", "--quiet",
        "--replace-text", str(workspace.replacements_file),
        "--replace-message", str(workspace.replacements_file),
        *removed_path_args, *invert_args,
        repo=workspace.cleaned,
    )
    ok(f"rewritten copy: {workspace.cleaned}")
    ok(f"replacement text: {workspace.replacement_text_file.read_text(encoding='utf-8')}")
    if settings.removed_paths:
        ok(f"paths removed from every commit: {', '.join(settings.removed_paths)}")


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


def step_rehearse(settings: Settings, workspace: Workspace) -> None:
    require_tools("git")
    if not workspace.cleaned.is_dir():
        fail("run the rewrite and verify steps first")
    rehearsal_remote = str(workspace.rehearsal_remote)
    workspace.rehearsal_passed.unlink(missing_ok=True)

    say("Creating a local stand-in for the remote, exactly as it was at fetch time")
    remove_tree(workspace.rehearsal_remote)
    remove_tree(workspace.rehearsal_clone)
    mirror_clone(workspace.original, workspace.rehearsal_remote, copy_objects=False)

    say("Running the real push sequence against the local stand-in")
    require_remote_unchanged_since_fetch(workspace, rehearsal_remote)
    push_cleaned_history(settings, workspace, rehearsal_remote)
    require_remote_matches_cleaned_copy(workspace, rehearsal_remote)

    say("Cloning the local stand-in fresh, like a teammate would after the real push")
    mirror_clone(workspace.rehearsal_remote, workspace.rehearsal_clone)
    check_history_is_clean(settings, workspace, workspace.rehearsal_clone, "rehearsal-fresh-clone")

    write_lines(workspace.rehearsal_passed, branch_and_tag_refs(workspace.cleaned))
    remove_tree(workspace.rehearsal_remote)
    remove_tree(workspace.rehearsal_clone)
    ok("rehearsal passed; the push step is now unlocked for this rewritten copy")


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


def step_cleanup(settings: Settings, workspace: Workspace) -> None:
    require_typed_word(f"This deletes {workspace.root} (it holds the original secrets).", "DELETE")
    remove_tree(workspace.root)
    ok("work folder deleted")


STEPS = {
    "fetch": (step_fetch, "Download every branch and tag into the work folder"),
    "find": (step_find, "Find every secret value in history (gitleaks + old config files + extra patterns)"),
    "rewrite": (step_rewrite, "Rewrite a copy of the history: every secret becomes the replacement text"),
    "verify": (step_verify, "Check the copy: 0 secrets left, no branch/tag lost, reference branch files unchanged"),
    "rehearse": (step_rehearse, "Push to a LOCAL stand-in with the real push code, re-clone it and check again"),
    "push": (step_push, "FORCE-PUSH to the real remote (only after a passed rehearsal; asks you to type PUSH)"),
    "cleanup": (step_cleanup, "Delete the work folder (asks you to type DELETE)"),
}
COMBINED_STEPS = {
    "test": ["fetch", "find", "rewrite", "verify", "rehearse"],
    "all": ["fetch", "find", "rewrite", "verify", "rehearse", "push"],
}


def build_parser() -> argparse.ArgumentParser:
    step_help = "\n".join(f"  {name:<9} {description}" for name, (_, description) in STEPS.items())
    combined_help = "\n".join(f"  {name:<9} {' -> '.join(steps)}" for name, steps in COMBINED_STEPS.items())
    parser = argparse.ArgumentParser(
        description="Remove secrets from the whole git history of a repository and replace the history on its remote.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"steps:\n{step_help}\n{combined_help}\n\nexample:\n  python git_history_purge.py test --repo-url https://github.com/org/repo.git",
    )
    parser.add_argument("step", choices=[*STEPS, *COMBINED_STEPS])
    parser.add_argument("--repo-url", required=True, help="remote to clean: HTTPS, SSH or a local path")
    parser.add_argument("--reference-branch", default="", help="branch whose CURRENT files must stay identical; values on it are kept (default: the remote's default branch)")
    parser.add_argument("--replacement-text", default=DEFAULT_REPLACEMENT, help="text that replaces each secret; {timestamp} is filled in")
    parser.add_argument("--timezone-offset", default="+00:00", help="timezone of {timestamp}, e.g. +05:30 (default: +00:00)")
    parser.add_argument("--timezone-label", default="UTC", help="label after {timestamp}, e.g. IST (default: UTC)")
    parser.add_argument("--remove-path", action="append", default=[], help="glob deleted from every commit, e.g. 'apps/*/.next/*' (repeatable)")
    parser.add_argument("--extra-secret-pattern", action="append", default=[], help="regex searched in every diff, e.g. 'sntry[su]_[A-Za-z0-9_=+/-]{20,}' (repeatable)")
    parser.add_argument("--extra-literals-file", default="", help="file with one extra value to remove per line")
    parser.add_argument("--min-secret-length", type=int, default=8, help="shorter values are skipped (default: 8)")
    parser.add_argument("--secret-key-pattern", default=DEFAULT_SECRET_KEY_PATTERN, help="regex for config keys that hold secrets")
    parser.add_argument("--config-file-pattern", default=DEFAULT_CONFIG_FILE_PATTERN, help="regex for config files read in every old version")
    parser.add_argument("--gitleaks-ignored-files", default=DEFAULT_GITLEAKS_IGNORED_FILES, help="regex for files whose gitleaks hits are ignored")
    parser.add_argument("--drop-ref-prefix", action="append", default=[], help="read-only refs dropped after download (default: refs/pull/)")
    parser.add_argument("--validation-file", default="", help="optional: file listing validated env keys; rewrite stops if a live secret key is missing from it")
    parser.add_argument("--validation-key-pattern", default=r"^\s+([A-Z0-9_]+)!?:", help="regex capturing key names in --validation-file")
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


if __name__ == "__main__":
    sys.exit(main())
