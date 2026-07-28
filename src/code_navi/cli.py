"""Command-line host for the Code Navi learning assistant."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from code_navi.application import QuestionResult, QuestionService
from code_navi.context import (
    ContextBuilder,
    ContextError,
    ContextSlice,
    ConversationTurn,
    discover_project_root,
)
from code_navi.providers import (
    ProviderConfigurationError,
    ProviderSettings,
    create_provider,
)
from kernel.core import RunStatus

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_INCOMPLETE = 4
EXIT_RUNTIME = 5
EXIT_INTERRUPTED = 130


@dataclass(slots=True)
class BranchState:
    """In-memory follow-up branch for one interactive shell session."""

    title: str
    turns: list[ConversationTurn] = field(default_factory=list)


class InteractiveShell:
    """Small focus-based shell equivalent to the GUI question sidebar."""

    def __init__(
        self,
        service: QuestionService,
        *,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
    ) -> None:
        self.service = service
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.last_answer: str | None = None
        self.last_context: ContextSlice | None = None
        self.branch: BranchState | None = None

    @property
    def project_name(self) -> str:
        return self.service.context_builder.project_root.name

    def run(self) -> int:
        """Read commands until EOF or an explicit exit command."""
        self._write("Code Navi CLI。输入问题，或使用 /help 查看交互命令。\n")
        while True:
            self._write(self._prompt(), end="")
            self.stdout.flush()
            line = self.stdin.readline()
            if line == "":
                self._write("\n", end="")
                return EXIT_OK
            value = line.strip()
            if not value:
                continue
            try:
                should_continue = self._handle(value)
            except ContextError as exc:
                self._error(f"上下文错误：{exc}")
                continue
            if not should_continue:
                return EXIT_OK

    def _handle(self, value: str) -> bool:
        command, _, argument = value.partition(" ")
        if command in {"/exit", "/quit"}:
            return False
        if command == "/help":
            self._show_help()
            return True
        if command == "/context":
            self._show_context()
            return True
        if command == "/back":
            if self.branch is None:
                self._error("当前不在问题分支中。")
            else:
                self.branch = None
                self._write("已返回主任务。\n")
            return True
        if command == "/branch":
            if self.branch is not None:
                self._error("请先使用 /back 返回主任务，再打开新的问题分支。")
                return True
            question = argument.strip()
            if not question:
                self._error("用法：/branch <需要连续追问的问题>")
                return True
            self.branch = BranchState(self._branch_title(question))
            seeded_question = f"@last {question}" if self.last_answer else question
            self._answer(seeded_question, persist_in_branch=True)
            return True
        if command.startswith("/"):
            self._error(f"未知命令：{command}。使用 /help 查看帮助。")
            return True

        question = value[1:].strip() if value.startswith("?") else value
        if not question:
            self._error("问题不能为空。")
            return True
        self._answer(question, persist_in_branch=self.branch is not None)
        return True

    def _answer(self, question: str, *, persist_in_branch: bool) -> None:
        history = () if self.branch is None else tuple(self.branch.turns)
        result = self.service.ask(
            question,
            last_answer=self.last_answer,
            branch_history=history,
        )
        self.last_context = result.context
        self._write(f"上下文：{result.context.receipt}\n\n")
        if result.output_text:
            self._write(result.output_text.rstrip() + "\n\n")
        else:
            self._error(_runtime_error_message(result))
        self.last_answer = result.output_text or self.last_answer
        if persist_in_branch and self.branch is not None and result.output_text:
            self.branch.turns.append(ConversationTurn(result.question, result.output_text))

    def _show_context(self) -> None:
        context = self.last_context or self.service.context_builder.preview()
        self._write(f"项目：{context.project_name}\n")
        self._write(f"根目录：{context.project_root}\n")
        if context.task.title:
            self._write(f"任务：{context.task.title}\n")
        if context.task.goal:
            self._write(f"目标：{context.task.goal}\n")
        if context.task.current_milestone:
            self._write(f"当前里程碑：{context.task.current_milestone}\n")
        if self.branch is not None:
            self._write(f"问题分支：{self.branch.title}\n")
        self._write("上下文来源：" + (", ".join(context.sources) or "项目标识") + "\n\n")

    def _show_help(self) -> None:
        self._write(
            """
直接输入问题       使用当前项目上下文回答
? <问题>           一次性快速提问，回答后保持在主任务
/branch <问题>     打开可连续追问的临时问题分支
/back              关闭问题分支并返回主任务
/context           查看当前自动携带的上下文
/help              显示帮助
/exit              退出

问题中可使用 @last 引用上一条回答，或使用 @path:起始行-结束行附加文件片段。
""".lstrip()
        )

    def _prompt(self) -> str:
        focus = self.project_name
        if self.branch is not None:
            focus += f" › {self.branch.title}"
        return f"[{focus}] > "

    @staticmethod
    def _branch_title(question: str) -> str:
        compact = " ".join(question.split())
        return compact if len(compact) <= 24 else compact[:23] + "…"

    def _write(self, value: str, *, end: str = "") -> None:
        self.stdout.write(value + end)

    def _error(self, value: str) -> None:
        self.stderr.write(value.rstrip() + "\n")


def build_parser() -> argparse.ArgumentParser:
    """Create the public CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="code-navi",
        description="Context-aware code learning assistant",
    )
    subparsers = parser.add_subparsers(dest="command")

    ask = subparsers.add_parser("ask", help="answer one project-aware question")
    _add_common_options(ask)
    ask.add_argument("question", nargs="?", help="question; stdin is used when omitted")
    ask.add_argument(
        "--attach",
        action="append",
        default=[],
        metavar="PATH[:START-END]",
        help="attach a UTF-8 project file or line range",
    )
    ask.add_argument("--format", choices=("text", "json"), default="text")

    shell = subparsers.add_parser("shell", help="start the interactive question shell")
    _add_common_options(shell)
    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", help="project directory; defaults to automatic discovery")
    parser.add_argument(
        "--no-project-context",
        action="store_true",
        help="do not attach task metadata or README content",
    )
    parser.add_argument("--events-dir", help="Event JSONL directory; defaults to var/runs")
    parser.add_argument("--session-id", help="explicit safe session identifier")
    parser.add_argument("--provider", choices=("mock", "openai"))
    parser.add_argument("--model", help="model name for the online provider")
    parser.add_argument("--mock-response", help=argparse.SUPPRESS)
    parser.add_argument(
        "--context-chars",
        type=int,
        default=16_000,
        help="maximum characters of attached reference context",
    )
    parser.add_argument("--debug", action="store_true", help="show full error tracebacks")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a stable process exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        arguments = ["shell"]
    parser = build_parser()
    args = parser.parse_args(arguments)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        service = _create_service(args)
        if args.command == "shell":
            return InteractiveShell(
                service,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
            ).run()
        question = args.question
        if question is None:
            question = sys.stdin.read()
        if not question.strip():
            raise ContextError("question must not be empty")
        result = service.ask(question, attachments=tuple(args.attach))
        return _emit_one_shot(result, args.format)
    except KeyboardInterrupt:
        sys.stderr.write("interrupted\n")
        return EXIT_INTERRUPTED
    except ContextError as exc:
        sys.stderr.write(f"input error: {exc}\n")
        return EXIT_USAGE
    except ProviderConfigurationError as exc:
        sys.stderr.write(f"configuration error: {exc}\n")
        return EXIT_CONFIG
    except Exception as exc:
        if args.debug:
            traceback.print_exc()
        else:
            sys.stderr.write(f"runtime error: {exc}\n")
        return EXIT_RUNTIME


def _create_service(args: argparse.Namespace) -> QuestionService:
    root = discover_project_root(args.project)
    events_dir = Path(args.events_dir) if args.events_dir else Path("var") / "runs"
    if not events_dir.is_absolute():
        events_dir = root / events_dir
    builder = ContextBuilder(
        root,
        include_project_context=not args.no_project_context,
        max_context_chars=args.context_chars,
    )
    settings = ProviderSettings.resolve(
        name=args.provider,
        model=args.model,
        mock_response=args.mock_response,
    )
    return QuestionService(
        create_provider(settings),
        builder,
        events_dir=events_dir,
        session_id=args.session_id,
    )


def _emit_one_shot(result: QuestionResult, output_format: str) -> int:
    status = result.runtime.run_result.status
    if output_format == "json":
        payload = {
            "schema_version": 1,
            "agent": result.runtime.agent_name,
            "run_id": result.runtime.run_id,
            "session_id": result.runtime.session_id,
            "status": status.value,
            "question": result.question,
            "context": {
                "project": result.context.project_name,
                "sources": list(result.context.sources),
            },
            "output": result.output_text or None,
            "event_log": result.runtime.event_log_path,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    else:
        sys.stderr.write(f"context: {result.context.receipt}\n")
        if result.output_text:
            sys.stdout.write(result.output_text.rstrip() + "\n")
        else:
            sys.stderr.write(_runtime_error_message(result) + "\n")
    if status is RunStatus.COMPLETED:
        return EXIT_OK
    if status in {RunStatus.BUDGET_EXHAUSTED, RunStatus.INTERRUPTED}:
        return EXIT_INCOMPLETE
    return EXIT_RUNTIME


def _runtime_error_message(result: QuestionResult) -> str:
    run_result = result.runtime.run_result
    return run_result.error or run_result.reason or f"run ended with {run_result.status.value}"


__all__ = [
    "EXIT_CONFIG",
    "EXIT_INCOMPLETE",
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_RUNTIME",
    "EXIT_USAGE",
    "InteractiveShell",
    "build_parser",
    "main",
]
