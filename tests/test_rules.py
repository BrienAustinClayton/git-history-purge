import pytest

from git_history_purge.detection.rules import INCLUDED, classify_value, strip_quotes_and_comment


@pytest.mark.parametrize(
    "raw_value, expected",
    [
        ('"quoted value"', "quoted value"),
        ("'single quoted'", "single quoted"),
        ("plain # trailing comment", "plain"),
        ("  spaced  ", "spaced"),
        ('"keeps # inside quotes"', "keeps # inside quotes"),
        ("no#space", "no#space"),
    ],
)
def test_strip_quotes_and_comment(raw_value: str, expected: str) -> None:
    assert strip_quotes_and_comment(raw_value) == expected


@pytest.mark.parametrize(
    "value, min_length, expected",
    [
        ("Sup3rS3cretPassw0rd", 8, INCLUDED),
        ("abc123", 8, "skipped: shorter than minimum length"),
        ("<your-password-here>", 8, "skipped: placeholder"),
        ("${DB_PASSWORD_VALUE}", 8, "skipped: placeholder"),
        ("{{ secret_value }}", 8, "skipped: placeholder"),
        ("replace_your_key_now", 8, "skipped: placeholder"),
        ("changeme-please", 8, "skipped: placeholder"),
        ("postgres", 8, "skipped: common word"),
        ("localhost", 8, "skipped: common word"),
        ("lowercaseword", 8, "skipped: common word"),
        ("abc==>def12345", 8, "skipped: cannot be a replace-text literal"),
        ("line1Value\nline2Value", 8, "skipped: cannot be a replace-text literal"),
        ("postgres://app:Passw0rdXyz12@localhost/app", 8, "skipped: local development URL"),
        ("postgres://app:Rem0tePassw0rdXyz@db.example.com/app", 8, INCLUDED),
    ],
)
def test_classify_value_decision(value: str, min_length: int, expected: str) -> None:
    assert classify_value(value, min_length) == expected
