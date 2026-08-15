from __future__ import annotations

import subprocess


def test_repository_does_not_track_appledouble_metadata() -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )

    tracked_metadata = [
        path for path in result.stdout.splitlines() if path.startswith("._") or "/._" in path
    ]
    assert tracked_metadata == []
