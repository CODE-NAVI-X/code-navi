from pathlib import Path

from kernel.adapters.jsonl_session import save_session
from kernel.core import Event
from kernel.trace.__main__ import main


def event(seq: int, event_type: str, payload: dict) -> Event:
    return Event(
        f"event-{seq}",
        "run-1",
        seq,
        f"2026-07-14T00:00:{seq:02d}Z",
        event_type,
        payload,
    )


def old_s5_error_and_interrupt_log() -> tuple[Event, ...]:
    return (
        event(0, "run_started", {}),
        event(
            1,
            "error",
            {
                "source": "kernel",
                "classification": "retryable",
                "message": "recoverable note",
                "attempt": None,
            },
        ),
        event(2, "interrupted", {}),
        event(
            3,
            "run_finished",
            {"status": "interrupted", "reason": "interrupted"},
        ),
    )


def test_cli_renders_old_s5_error_and_interrupt_log(tmp_path: Path, capsys) -> None:
    path = tmp_path / "old.jsonl"
    save_session(path, old_s5_error_and_interrupt_log())

    assert main([str(path)]) == 0
    output = capsys.readouterr().out
    assert "0001 error source=kernel classification=retryable" in output
    assert "0002 interrupted" in output
    assert "0003 run_finished status=interrupted reason=interrupted" in output


def test_cli_verbose_prints_full_payload(tmp_path: Path, capsys) -> None:
    path = tmp_path / "verbose.jsonl"
    save_session(path, old_s5_error_and_interrupt_log())

    assert main([str(path), "--verbose"]) == 0
    output = capsys.readouterr().out
    assert '"classification": "retryable"' in output
    assert '"message": "recoverable note"' in output


def test_cli_structurally_diffs_two_logs(tmp_path: Path, capsys) -> None:
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    save_session(left, old_s5_error_and_interrupt_log())
    changed = list(old_s5_error_and_interrupt_log())
    changed[1] = event(
        1,
        "error",
        {
            "source": "kernel",
            "classification": "retryable",
            "message": "changed",
            "attempt": None,
        },
    )
    save_session(right, changed)

    assert main(["--diff", str(left), str(right)]) == 1
    output = capsys.readouterr().out
    assert "/1/payload/message" in output
    assert 'left="recoverable note"' in output
    assert 'right="changed"' in output
