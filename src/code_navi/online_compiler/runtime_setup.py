"""Deployment helper that installs the pinned Python runtime into Piston."""

from __future__ import annotations

import logging
import os
import time

from .piston import PistonClient, PistonError

LOGGER = logging.getLogger("code_navi.online_compiler.setup")


def main() -> None:
    """Wait for Piston, install the pinned runtime once, and verify it."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    base_url = os.getenv("PISTON_BASE_URL", "http://piston:2000")
    version = os.getenv("PISTON_PYTHON_VERSION", "3.12.0")
    attempts = int(os.getenv("PISTON_SETUP_ATTEMPTS", "60"))
    client = PistonClient(base_url, timeout_seconds=10.0)

    for attempt in range(1, attempts + 1):
        try:
            runtimes = client.list_runtimes()
            already_installed = any(
                runtime.language == "python" and runtime.version == version
                for runtime in runtimes
            )
            if already_installed:
                LOGGER.info("Python %s is already installed", version)
                return
            packages = client.list_packages()
            available = any(
                package.get("language") == "python"
                and package.get("language_version") == version
                for package in packages
            )
            if not available:
                raise RuntimeError(f"Piston repository does not provide Python {version}")
            LOGGER.info("Installing Python %s into Piston", version)
            client.install_package("python", version)
            installed = client.list_runtimes()
            if not any(
                runtime.language == "python" and runtime.version == version
                for runtime in installed
            ):
                raise RuntimeError(f"Python {version} installation could not be verified")
            LOGGER.info("Python %s installation completed", version)
            return
        except PistonError as error:
            if attempt == attempts:
                raise RuntimeError("Piston did not become ready in time") from error
            LOGGER.info("Waiting for Piston (%s/%s)", attempt, attempts)
            time.sleep(2)


if __name__ == "__main__":
    main()
