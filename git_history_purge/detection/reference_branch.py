"""Rules tied to the reference branch: values still in today's code are kept, and live keys must be validated."""

from pathlib import Path

from git_history_purge.detection.ledger import SecretLedger
from git_history_purge.detection.rules import ASSIGNMENT_PATTERN, ENV_STYLE_KEY_PATTERN
from git_history_purge.git import git_text, read_blobs
from git_history_purge.settings import Settings


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
