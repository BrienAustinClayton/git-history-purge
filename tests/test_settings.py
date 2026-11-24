from datetime import timedelta

import pytest

from git_history_purge.console import StepFailed
from git_history_purge.settings import parse_utc_offset, repo_name_from_url


@pytest.mark.parametrize(
    "offset_text, expected",
    [
        ("+05:30", timedelta(hours=5, minutes=30)),
        ("-08:00", timedelta(hours=-8)),
        ("+00:00", timedelta(0)),
    ],
)
def test_parse_utc_offset_accepts_valid_offsets(offset_text: str, expected: timedelta) -> None:
    assert parse_utc_offset(offset_text).utcoffset(None) == expected


@pytest.mark.parametrize("offset_text", ["", "05:30", "+5:30", "+0530", "UTC", "+05:30:00"])
def test_parse_utc_offset_rejects_invalid_offsets(offset_text: str) -> None:
    with pytest.raises(StepFailed):
        parse_utc_offset(offset_text)


@pytest.mark.parametrize(
    "repo_url, expected",
    [
        ("https://github.com/acme/widgets.git", "widgets"),
        ("https://github.com/acme/widgets", "widgets"),
        ("git@github.com:acme/widgets.git", "widgets"),
        ("/srv/git/widgets.git", "widgets"),
        ("/srv/git/widgets.git/", "widgets"),
        ("C:\\repos\\widgets.git", "widgets"),
        ("C:\\repos\\widgets\\", "widgets"),
        ("", "repo"),
    ],
)
def test_repo_name_from_url(repo_url: str, expected: str) -> None:
    assert repo_name_from_url(repo_url) == expected
