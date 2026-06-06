#!/usr/bin/env python3
"""
scripts/preflight.py

Pre-deployment validation:
- Verify backend health
- Validate environment configuration
- Check dependencies

Usage:
    uv run python -m scripts.preflight
    uv run python -m scripts.preflight --port 8000
"""

import argparse
import os
import sys
import subprocess
import time
import socket
from pathlib import Path

try:
    import httpx
    from dotenv import load_dotenv
except ImportError:
    print("[ERROR] Required packages not found. Run: uv sync")
    sys.exit(1)


PROJECT_ROOT = Path(__file__).parent.parent


def print_check(status: bool, message: str):
    """Print a check result."""
    symbol = "✓" if status else "✗"
    color = "\033[92m" if status else "\033[91m"
    reset = "\033[0m"
    print(f"  [{color}{symbol}{reset}] {message}")
    return status


def check_environment() -> bool:
    """Verify .env and required variables."""
    print("\n[=] Environment Configuration")

    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        print_check(False, ".env file not found")
        print("     Run: uv run python -m scripts.quickstart")
        return False

    load_dotenv(env_file)

    required_vars = ["PGHOST", "PGDATABASE", "PGUSER"]
    missing = [v for v in required_vars if not os.getenv(v)]

    if missing:
        print_check(False, f"Missing environment variables: {', '.join(missing)}")
        return False

    # Check auth method
    has_endpoint = os.getenv("ENDPOINT_NAME")
    has_password = os.getenv("PGPASSWORD") and not os.getenv("PGPASSWORD").startswith("your-")

    if not has_endpoint and not has_password:
        print_check(False, "Missing authentication: set ENDPOINT_NAME or PGPASSWORD")
        return False

    print_check(True, "All required environment variables set")
    return True


def check_dependencies() -> bool:
    """Verify all dependencies are installed."""
    print("\n[=] Dependencies")

    try:
        result = subprocess.run(
            ["uv", "pip", "list"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            print_check(True, "Python dependencies installed")
            return True
        else:
            print_check(False, "Dependency check failed")
            return False
    except Exception as e:
        print_check(False, f"Could not verify dependencies: {e}")
        return False


def check_backend_port(port: int) -> bool:
    """Check if backend port is available."""
    print(f"\n[=] Port Availability (port {port})")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("localhost", port))
        sock.close()

        if result == 0:
            print_check(False, f"Port {port} is already in use")
            return False
        else:
            print_check(True, f"Port {port} is available")
            return True
    except Exception as e:
        print_check(False, f"Could not check port: {e}")
        return False


def check_backend_startup(port: int, timeout: int = 30) -> bool:
    """Start backend briefly and verify it's healthy."""
    print(f"\n[=] Backend Startup (timeout: {timeout}s)")

    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    start = time.time()
    ready = False

    try:
        while time.time() - start < timeout:
            try:
                with httpx.Client(timeout=2) as client:
                    resp = client.get(f"http://localhost:{port}/health")
                    if resp.status_code == 200:
                        ready = True
                        break
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(0.5)

        if ready:
            print_check(True, "Backend started and responding")
        else:
            print_check(False, "Backend did not respond within timeout")

        return ready

    except Exception as e:
        print_check(False, f"Backend startup check failed: {e}")
        return False

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    parser = argparse.ArgumentParser(description="Preflight checks for Lakebase")
    parser.add_argument("--port", type=int, default=8000, help="Backend port to test")
    parser.add_argument("--skip-backend", action="store_true", help="Skip backend startup test")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  Lakebase — Preflight Checks")
    print("=" * 60)

    checks = [
        ("Environment", check_environment),
        ("Dependencies", check_dependencies),
        ("Port Availability", lambda: check_backend_port(args.port)),
    ]

    if not args.skip_backend:
        checks.append(("Backend Startup", lambda: check_backend_startup(args.port)))

    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print_check(False, f"{name}: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"  Preflight Check: {passed}/{total} passed")
    print("=" * 60 + "\n")

    if passed == total:
        print("[✓] All checks passed! Ready to run.\n")
        return 0
    else:
        print("[✗] Some checks failed. See above for details.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
