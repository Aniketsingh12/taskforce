#!/usr/bin/env python
"""Start the whole TaskForce stack with ONE command.

    python run.py             # start backend (:8000) + frontend (:5173)
    python run.py --install   # install backend + frontend deps first, then start
    python run.py --backend   # backend only (e.g. to use the CLI demo/API docs)

Backend  -> http://localhost:8000  (API docs at /docs)
Frontend -> http://localhost:5173  (open this)

Ctrl+C stops both. Works on Windows, macOS, and Linux; no extra dependencies —
it just orchestrates uvicorn and `npm run dev` as child processes.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
IS_WIN = os.name == "nt"


def _free_port(preferred: int) -> int:
    """Return `preferred` if we can bind it, else the next free port above it.

    Keeps the single command working even when something (e.g. a leftover
    uvicorn) already holds the default port. The frontend is pointed at whatever
    we pick via BACKEND_URL, so the user always just opens the Vite URL.

    Note: we release the probe socket before uvicorn binds it, so this is
    best-effort — another process could still take the port in between. The
    caller re-checks and retries rather than dying on that race.
    """
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred  # give up and let uvicorn surface the real error


def _popen(cmd, cwd: Path, env: dict | None = None) -> subprocess.Popen:
    """Launch a child with its own process group so we can tree-kill it later.

    stdout+stderr are merged and piped back so we can prefix each line with the
    service name. `shell=True` on Windows lets `npm` (a .cmd shim) resolve.
    """
    kwargs: dict = dict(
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # line-buffered
        env=env,
    )
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        return subprocess.Popen(cmd if isinstance(cmd, str) else subprocess.list2cmdline(cmd),
                                shell=True, **kwargs)
    kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _pump(proc: subprocess.Popen, prefix: str) -> None:
    """Forward a child's output to our terminal, one prefixed line at a time."""
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(f"{prefix} {line}")
        sys.stdout.flush()


def _stop(proc: subprocess.Popen | None) -> None:
    """Terminate a child and everything it spawned (uvicorn reloader, node)."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        proc.kill()


def _install() -> None:
    print("[run] installing backend deps…", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                   cwd=str(BACKEND), check=True)
    print("[run] installing frontend deps…", flush=True)
    subprocess.run("npm install", cwd=str(FRONTEND), shell=True, check=True)


def main() -> int:
    args = set(sys.argv[1:])
    if "--install" in args:
        _install()

    backend_only = "--backend" in args

    # Pick the backend port: default 8000, override with `--port N` or PORT env,
    # and hop to the next free port if it's taken so the command never dies on a
    # busy port.
    want = int(os.environ.get("PORT", "8000"))
    for a in sys.argv[1:]:
        if a.startswith("--port="):
            want = int(a.split("=", 1)[1])
    port = _free_port(want)

    procs: list[tuple[str, subprocess.Popen]] = []

    # Backend: uvicorn with autoreload. --reload spawns a watcher child, which is
    # why _stop() does a tree-kill rather than a plain terminate().
    # Retry a couple of times in case another process grabbed the port between
    # our probe and uvicorn's bind (see _free_port).
    backend = None
    for _ in range(3):
        backend = _popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--reload"],
            BACKEND,
        )
        time.sleep(1.5)
        if backend.poll() is None:
            break  # still alive → it got the port
        port = _free_port(port + 1)  # died immediately; try the next one
    procs.append(("backend ", backend))

    frontend = None
    if not backend_only:
        # Point Vite's /api proxy (and its WebSocket upgrade) at the backend port
        # we actually chose — see BACKEND_URL in frontend/vite.config.js.
        fe_env = {**os.environ, "BACKEND_URL": f"http://localhost:{port}"}
        frontend = _popen(["npm", "run", "dev"], FRONTEND, env=fe_env)
        procs.append(("frontend", frontend))

    for prefix, p in procs:
        threading.Thread(target=_pump, args=(p, f"[{prefix}]"), daemon=True).start()

    print("\n[run] TaskForce is starting…")
    print(f"[run]   backend  -> http://localhost:{port}  (docs at /docs)")
    if port != want:
        print(f"[run]   (port {want} was busy, used {port} instead)")
    if not backend_only:
        print("[run]   frontend -> http://localhost:5173  <-- open this")
    print("[run] press Ctrl+C to stop.\n", flush=True)

    try:
        # Stay alive until Ctrl+C, or until a child dies (then take the rest down).
        while True:
            for name, p in procs:
                if p.poll() is not None:
                    print(f"\n[run] {name.strip()} exited (code {p.returncode}); shutting down.")
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[run] stopping…", flush=True)
    finally:
        # Stop frontend first so it isn't left calling a dead backend.
        _stop(frontend)
        _stop(backend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
