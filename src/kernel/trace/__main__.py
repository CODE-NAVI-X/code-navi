"""Command-line trace renderer for strict kernel JSONL sessions."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from kernel.adapters.jsonl_session import SessionFormatError, load_session
from kernel.core.types import Event, Message
from kernel.providers.replay import first_structural_difference


def render_event(event: Event, *, verbose: bool = False) -> str:
    summary = _summary(event)
    line = f"{event.seq:04d} {event.type}"
    if summary:
        line += f" {summary}"
    if not verbose:
        return line
    payload = json.dumps(event.payload, ensure_ascii=False, indent=2)
    return f"{line}\n{payload}"


def render_trace(events: Sequence[Event], *, verbose: bool = False) -> str:
    return "\n".join(render_event(event, verbose=verbose) for event in events)


def _summary(event: Event) -> str:
    payload = event.payload
    if event.type == "message_added":
        message = Message.from_json(payload["message"])
        return f"role={message.role} blocks={len(message.content)}"
    if event.type == "provider_called":
        return (
            f"attempt={payload['attempt']} messages={len(payload['messages'])} "
            f"tools={len(payload['tools'])}"
        )
    if event.type == "provider_returned":
        response = payload["response"]
        return (
            f"attempt={payload['attempt']} request_seq={payload['request_seq']} "
            f"finish_reason={response.get('finish_reason')!r}"
        )
    if event.type == "tool_called":
        call = payload["tool_call"]
        return f"name={call['name']} id={call['id']}"
    if event.type == "tool_returned":
        result = payload["tool_result"]
        return f"name={result['name']} id={result['tool_call_id']}"
    if event.type == "budget_updated":
        return (
            f"steps={payload['used_steps']}/{payload['max_steps']} "
            f"tools={payload['used_tool_calls']}/{payload['max_tool_calls']}"
        )
    if event.type == "context_compressed":
        return (
            f"source_seq={payload['start_seq']}..{payload['end_seq']} "
            f"sources={len(payload['source_event_ids'])}"
        )
    if event.type == "error":
        return (
            f"source={payload['source']} classification={payload['classification']} "
            f"message={payload['message']!r}"
        )
    if event.type == "run_finished":
        return f"status={payload['status']} reason={payload['reason']}"
    return ""


def diff_traces(left: Sequence[Event], right: Sequence[Event]) -> str | None:
    expected = [event.to_json() for event in left]
    actual = [event.to_json() for event in right]
    difference = first_structural_difference(expected, actual)
    if difference is None:
        return None
    path, left_value, right_value = difference
    return (
        f"difference at {path}: left="
        f"{json.dumps(left_value, ensure_ascii=False, default=str)} right="
        f"{json.dumps(right_value, ensure_ascii=False, default=str)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kernel.trace")
    parser.add_argument("session", nargs="?", type=Path)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--diff", nargs=2, metavar=("LEFT", "RIGHT"), type=Path)
    args = parser.parse_args(argv)
    if args.diff is not None and args.session is not None:
        parser.error("session and --diff are mutually exclusive")
    if args.diff is None and args.session is None:
        parser.error("provide a session path or --diff LEFT RIGHT")
    try:
        if args.diff is not None:
            left = load_session(args.diff[0])
            right = load_session(args.diff[1])
            difference = diff_traces(left, right)
            if difference is None:
                print("traces are structurally identical")
                return 0
            print(difference)
            return 1
        print(render_trace(load_session(args.session), verbose=args.verbose))
        return 0
    except (OSError, SessionFormatError) as exc:
        print(f"trace error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
