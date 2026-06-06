#!/usr/bin/env python3
"""
scripts/quickstart.py

Interactive initialization script for Lakebase.
Sets up .env and installs dependencies.

Usage:
    uv run python -m scripts.quickstart
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path

try:
    from dotenv import load_dotenv, set_key
except ImportError:
    print("[ERROR] python-dotenv not found. Run: uv sync")
    sys.exit(1)


PROJECT_ROOT = Path(__file__).parent.parent


def print_header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def check_prerequisites() -> bool:
    """Verify required tools are installed."""
    print_header("Checking Prerequisites")

    missing = []

    if subprocess.run(["uv", "--version"], capture_output=True).returncode != 0:
        missing.append("uv (Python package manager)")

    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        missing.append("Node.js (JavaScript runtime)")
    if subprocess.run(["npm", "--version"], capture_output=True).returncode != 0:
        missing.append("npm (Node package manager)")

    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        missing.append("Python 3.11+ (current: {}.{})".format(version.major, version.minor))

    if missing:
        print("[ERROR] Missing prerequisites:")
        for m in missing:
            print(f"  • {m}")
        return False

    print("[✓] All prerequisites met")
    return True


def setup_env_file() -> bool:
    """Set up .env file from template."""
    print_header("Environment Setup")

    env_file = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"

    if env_file.exists():
        print(f"[!] .env already exists")
        overwrite = input("Overwrite? (y/n) [n]: ").strip().lower() == "y"
        if not overwrite:
            print("[*] Using existing .env")
            return True

    if env_example.exists():
        print(f"[*] Creating .env from .env.example")
        env_file.write_text(env_example.read_text())
    else:
        print(f"[ERROR] No .env.example found")
        return False

    print("\n[?] Configure Lakebase PostgreSQL connection:")
    print("    (Get these from: Databricks → Compute → Lakebase Postgres → Connection details)\n")

    defaults = {
        "PGHOST": os.getenv("PGHOST", "your-instance.postgres.azuredatabricks.net"),
        "PGDATABASE": os.getenv("PGDATABASE", "default"),
        "PGUSER": os.getenv("PGUSER", "your_email@example.com"),
        "PGPORT": os.getenv("PGPORT", "5432"),
        "PGSSLMODE": os.getenv("PGSSLMODE", "require"),
    }

    for key, default in defaults.items():
        prompt = f"  {key} [{default}]: "
        value = input(prompt).strip()
        if value:
            set_key(env_file, key, value)
        elif not env_file.read_text().__contains__(f"{key}="):
            set_key(env_file, key, default)

    # Authentication
    print("\n[?] Choose authentication method:")
    print("  1. Use Databricks OAuth (recommended)")
    print("  2. Use static PostgreSQL password\n")

    auth_choice = input("  Select (1-2) [1]: ").strip() or "1"

    if auth_choice == "1":
        endpoint = input("  ENDPOINT_NAME (from connection details): ").strip()
        if endpoint:
            set_key(env_file, "ENDPOINT_NAME", endpoint)
        print("  [*] Using OAuth - make sure to run: databricks auth login")
    else:
        password = input("  PGPASSWORD: ").strip()
        if password:
            set_key(env_file, "PGPASSWORD", password)

    print("[✓] .env configured")
    return True


def install_dependencies() -> bool:
    """Install Python and frontend dependencies."""
    print_header("Installing Dependencies")

    print("[*] Running: uv sync")
    result = subprocess.run(["uv", "sync"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("[ERROR] Failed to install Python dependencies")
        return False

    print("[*] Running: npm install")
    result = subprocess.run(
        ["npm", "install"],
        cwd=PROJECT_ROOT / "frontend",
        capture_output=True
    )
    if result.returncode != 0:
        print("[ERROR] Failed to install frontend dependencies")
        return False

    print("[✓] Dependencies installed")
    return True


def summary():
    """Print setup summary and next steps."""
    print_header("Setup Complete")

    print("[✓] Lakebase initialized!")
    print("\n[Next steps]")
    print("  1. Start the app:")
    print("       uv run python -m scripts.start_app")
    print("\n  2. Or start with frontend dev server:")
    print("       uv run python -m scripts.start_app --dev")
    print("\n[Documentation]")
    print("  Backend API:  http://localhost:8000/docs")
    print("  Frontend:     http://localhost:8000")


def main():
    parser = argparse.ArgumentParser(description="Initialize Lakebase")
    args = parser.parse_args()

    steps = [
        ("Prerequisites", check_prerequisites),
        ("Environment", setup_env_file),
        ("Dependencies", install_dependencies),
    ]

    for step_name, step_fn in steps:
        try:
            if not step_fn():
                print(f"\n[ERROR] {step_name} failed")
                sys.exit(1)
        except KeyboardInterrupt:
            print("\n[!] Setup cancelled")
            sys.exit(1)

    summary()


if __name__ == "__main__":
    main()
