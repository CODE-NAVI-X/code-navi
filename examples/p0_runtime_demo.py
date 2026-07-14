"""Run from the repository root: python examples/p0_runtime_demo.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kernel.core import ContentBlock, Message, ProviderResult
from kernel.providers import MockProvider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest


def main() -> None:
    provider = MockProvider(
        [
            ProviderResult(
                Message(
                    "assistant",
                    (ContentBlock("text", {"text": "Runtime demo complete."}),),
                )
            )
        ]
    )
    result = AgentRuntime(provider).run(
        AgentSpec("demo", "Minimal runtime demo", "Answer concisely."),
        RuntimeRequest("Confirm the runtime is working."),
    )
    print(result.output_text)


if __name__ == "__main__":
    main()
