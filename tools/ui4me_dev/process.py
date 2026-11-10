from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from .common import DevError


def stop_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    process.wait(timeout=15)


def run(argv: list[str], *, cwd: Path, log: Path, env: dict | None = None, timeout: int = 900, check: bool = True) -> dict:
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    creation = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    result = {"argv": [str(a) for a in argv], "log": log.name, "status": "failed", "returncode": None}
    with log.open("w", encoding="utf-8") as output:
        output.write("COMMAND " + repr(result["argv"]) + "\n"); output.flush()
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, **creation)
        except OSError as error:
            result.update(status="blocked", error=str(error))
            output.write(str(error) + "\n")
            if check:
                raise DevError(f"Cannot start {argv[0]}: {error}; log: {log}") from error
            return result
        try:
            process.wait(timeout=timeout)
            result.update(returncode=process.returncode, status="passed" if process.returncode == 0 else "failed")
        except subprocess.TimeoutExpired:
            stop_tree(process)
            result.update(status="failed", error=f"Timed out after {timeout}s")
        except KeyboardInterrupt:
            stop_tree(process)
            result.update(status="interrupted", error="Interrupted by operator")
        result["duration_seconds"] = round(time.monotonic() - started, 3)
    if check and result["status"] != "passed":
        raise DevError(f"Command {result['status']}; inspect {log}")
    return result
