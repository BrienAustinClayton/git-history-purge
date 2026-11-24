"""Layout of the work folder: the downloaded, rewritten and rehearsal copies, the secret files and the reports."""

import os
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path


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
