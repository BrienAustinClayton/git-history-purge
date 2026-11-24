"""Writes the find reports. They hold key names, files and value lengths only, never the values."""

from git_history_purge.detection.ledger import SecretLedger
from git_history_purge.workspace import Workspace, write_lines


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
