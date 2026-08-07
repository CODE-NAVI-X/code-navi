from __future__ import annotations

import json
import os

import pytest

from code_navi.online_compiler.piston import ExecutionLimits, PistonClient

pytestmark = pytest.mark.live


@pytest.fixture
def live_piston() -> PistonClient:
    """Connect only when the developer explicitly opts into local Piston checks."""

    if os.getenv("CODE_NAVI_PISTON_LIVE_TEST") != "1":
        pytest.skip("set CODE_NAVI_PISTON_LIVE_TEST=1 to verify local Piston isolation")
    return PistonClient(
        os.getenv("PISTON_BASE_URL", "http://127.0.0.1:2000"),
        timeout_seconds=8.0,
    )


def _run(client: PistonClient, source: str) -> str:
    result = client.execute_python(
        source,
        "",
        version=os.getenv("PISTON_PYTHON_VERSION", "3.12.0"),
        limits=ExecutionLimits(),
    )
    assert result.outcome == "success", result.as_dict()
    return result.stdout.strip()


def test_live_piston_blocks_outbound_network(live_piston: PistonClient) -> None:
    output = _run(
        live_piston,
        """
import socket

try:
    socket.create_connection(("1.1.1.1", 80), timeout=0.5)
except OSError:
    print("blocked")
else:
    print("open")
""".strip(),
    )

    assert output == "blocked"


def test_live_piston_cleans_workspaces_and_hides_repository(
    live_piston: PistonClient,
) -> None:
    marker = "code-navi-piston-isolation-marker"
    first = _run(
        live_piston,
        f"""
from pathlib import Path

Path("/tmp/{marker}").write_text("created", encoding="utf-8")
print(Path("/workspace/pyproject.toml").exists())
""".strip(),
    )
    second = _run(
        live_piston,
        f"""
from pathlib import Path

print(Path("/tmp/{marker}").exists())
""".strip(),
    )

    assert first == "False"
    assert second == "False"


def test_live_piston_applies_process_and_file_limits(live_piston: PistonClient) -> None:
    output = _run(
        live_piston,
        """
import json
import resource

print(json.dumps({
    "files": resource.getrlimit(resource.RLIMIT_NOFILE)[0],
    "processes": resource.getrlimit(resource.RLIMIT_NPROC)[0],
}))
""".strip(),
    )
    limits = json.loads(output)

    assert 0 < limits["files"] <= 64
    assert 0 < limits["processes"] <= 64
