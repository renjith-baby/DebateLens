from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path


logger = logging.getLogger(__name__)


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_port_open(host, port):
            return
        time.sleep(0.5)
    raise TimeoutError(f"transcribe-service did not become reachable at {host}:{port} within {timeout}s")


@contextmanager
def supervised_service(
    *,
    base_url: str,
    service_dir: Path,
    auto_start: bool = True,
):
    host_part = base_url.split("://", 1)[-1]
    host, _, port_str = host_part.partition(":")
    if host in ("", "localhost"):
        host = "127.0.0.1"
    port = int(port_str.split("/", 1)[0]) if port_str else 80

    if _is_port_open(host, port):
        logger.info("transcribe-service already running at %s:%s", host, port)
        yield None
        return

    if not auto_start:
        raise RuntimeError(f"transcribe-service not reachable at {base_url} and auto-start disabled")

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "transcribe_service.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    env = os.environ.copy()
    logger.info("starting transcribe-service: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(service_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        _wait_for_port(host, port, timeout=30.0)
        logger.info("transcribe-service ready at %s:%s (pid=%s)", host, port, proc.pid)
        yield proc
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
