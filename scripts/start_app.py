#!/usr/bin/env python3
"""
scripts/start_app.py

Start Lakebase app locally with backend and optionally frontend in dev mode.
Monitors processes and provides a single entry point.

Usage:
    uv run python -m scripts.start_app              # backend + built frontend
    uv run python -m scripts.start_app --dev        # backend + frontend dev server
    uv run python -m scripts.start_app --backend-port 9000
"""

import argparse
import os
import sys
import subprocess
import time
import signal
import atexit
import socket
from pathlib import Path
from typing import Optional, List


PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"


class ProcessManager:
    """Manages multiple subprocesses with unified logging."""

    def __init__(self):
        self.processes: dict[str, subprocess.Popen] = {}
        self.ready_signals = {
            "backend": ["Uvicorn running on", "Application startup complete"],
            "frontend": ["Local:.*http", "VITE.*ready in"],
        }
        self.ready_flags = {}

        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print("\n[!] Shutting down...")
        self.cleanup()
        sys.exit(0)

    def find_available_port(self, start: int = 8000, max_attempts: int = 10) -> int:
        """Find an available port starting from `start`."""
        for port in range(start, start + max_attempts):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind(("localhost", port))
                sock.close()
                return port
            except OSError:
                continue
        raise RuntimeError(f"No available ports in range {start}-{start + max_attempts}")

    def start(self, name: str, cmd: List[str], cwd: Optional[Path] = None):
        """Start a subprocess and monitor its output."""
        LOGS_DIR.mkdir(exist_ok=True)
        log_file = LOGS_DIR / f"{name}.log"
        cwd = cwd or PROJECT_ROOT

        print(f"[*] Starting {name}...")

        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        self.processes[name] = proc
        self.ready_flags[name] = False

        def monitor_output():
            try:
                with open(log_file, "w") as lf:
                    for line in proc.stdout:
                        lf.write(line)
                        lf.flush()
                        print(f"[{name}] {line.rstrip()}")

                        if not self.ready_flags[name]:
                            for signal in self.ready_signals.get(name, []):
                                if signal in line:
                                    self.ready_flags[name] = True
                                    print(f"[✓] {name} is ready!")
                                    break
            except Exception as e:
                print(f"[ERROR] {name} monitoring failed: {e}")

        import threading
        thread = threading.Thread(target=monitor_output, daemon=True)
        thread.start()

    def wait_ready(self, names: List[str], timeout: int = 60) -> bool:
        """Wait for multiple processes to be ready."""
        start = time.time()
        while time.time() - start < timeout:
            if all(self.ready_flags.get(n) for n in names):
                print(f"\n[✓] All services ready!")
                return True
            time.sleep(0.5)

        print(f"\n[ERROR] Services did not start within {timeout}s")
        for name in names:
            if not self.ready_flags.get(name):
                print(f"  • {name} not ready")
        return False

    def is_running(self, name: str) -> bool:
        """Check if a process is still running."""
        proc = self.processes.get(name)
        if proc is None:
            return False
        return proc.poll() is None

    def cleanup(self):
        """Terminate all processes."""
        for name, proc in self.processes.items():
            if proc.poll() is None:
                print(f"[*] Stopping {name}...")
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def main():
    parser = argparse.ArgumentParser(description="Start Lakebase app locally")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run frontend in dev mode (Vite dev server)"
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=8000,
        help="Backend port (default: 8000)"
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=5173,
        help="Frontend port (default: 5173, only with --dev)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for backend"
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  Lakebase — Local Development")
    print("=" * 60)

    manager = ProcessManager()

    backend_port = manager.find_available_port(args.backend_port)
    if backend_port != args.backend_port:
        print(f"[!] Port {args.backend_port} in use, using {backend_port}")

    # Start backend
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.app:app",
        "--host", "127.0.0.1",
        "--port", str(backend_port),
    ]
    if args.reload:
        backend_cmd.append("--reload")

    manager.start("backend", backend_cmd)

    # Optionally start frontend dev server
    if args.dev:
        frontend_port = manager.find_available_port(args.frontend_port)
        if frontend_port != args.frontend_port:
            print(f"[!] Port {args.frontend_port} in use, using {frontend_port}")

        print("[*] Installing frontend dependencies...")
        subprocess.run(
            ["npm", "install"],
            cwd=PROJECT_ROOT / "frontend",
            capture_output=True,
        )

        frontend_cmd = ["npm", "run", "dev", "--", "--port", str(frontend_port)]
        manager.start("frontend", frontend_cmd, cwd=PROJECT_ROOT / "frontend")

    # Wait for services
    services = ["backend"]
    if args.dev:
        services.append("frontend")

    if not manager.wait_ready(services, timeout=60):
        print("\n[ERROR] Failed to start services")
        manager.cleanup()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  Services Running")
    print("=" * 60)
    print(f"\n  Backend:  http://localhost:{backend_port}")
    print(f"  Docs:     http://localhost:{backend_port}/docs")
    if args.dev:
        print(f"  Frontend: http://localhost:{frontend_port}")
    else:
        print(f"  Frontend: http://localhost:{backend_port} (built)")
    print("\n  Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
            for name in services:
                if not manager.is_running(name):
                    print(f"\n[ERROR] {name} crashed!")
                    manager.cleanup()
                    sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.cleanup()


if __name__ == "__main__":
    main()
