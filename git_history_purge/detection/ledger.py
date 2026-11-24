"""SecretLedger collects every secret value found, with its source, key and the files it appeared in."""

from collections import defaultdict
from dataclasses import dataclass, field


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
