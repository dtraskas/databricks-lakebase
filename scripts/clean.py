#!/usr/bin/env python3
"""
scripts/clean.py

Tear down the Lakebase app deployment.

Removes everything this bundle created in the Databricks workspace (the app,
its compute, and the uploaded source files) via `databricks bundle destroy`,
then deletes the local `.databricks/` bundle state directory.

This does NOT delete the Lakebase project/database — that is an independent
resource referenced by the bundle, not created by it. Deleting Lakebase data
is intentionally out of scope.

Usage:
    uv run python -m scripts.clean
    uv run python -m scripts.clean --profile my-profile
    uv run python -m scripts.clean --target prod
    uv run python -m scripts.clean --auto-approve
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def ok(msg: str):
    print(f"  [✓] {msg}")


def info(msg: str):
    print(f"  [*] {msg}")


def error(msg: str):
    print(f"  [!] {msg}")


def confirm(target_label: str) -> bool:
    print(
        f"\nThis will destroy the deployed app and uploaded files for target "
        f"'{target_label}' in Databricks,\nand remove the local .databricks/ "
        f"state directory.\n\nThe Lakebase project/database is NOT touched.\n"
    )
    answer = input("  Continue? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def destroy_bundle(profile: str | None, target: str | None) -> bool:
    """Remove all workspace resources + files created by the bundle."""
    cmd = ["databricks", "bundle", "destroy", "--auto-approve"]
    if profile:
        cmd += ["--profile", profile]
    if target:
        cmd += ["--target", target]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        error("bundle destroy failed")
        return False

    ok("Workspace resources destroyed")
    return True


def remove_local_state() -> bool:
    """Delete the local .databricks/ bundle state directory."""
    state_dir = PROJECT_ROOT / ".databricks"
    if not state_dir.exists():
        info(".databricks/ already absent")
        return True

    try:
        shutil.rmtree(state_dir)
    except OSError as e:
        error(f"Could not remove .databricks/: {e}")
        return False

    ok("Removed local .databricks/")
    return True


def main():
    parser = argparse.ArgumentParser(description="Tear down the Lakebase app deployment")
    parser.add_argument("--profile", help="Databricks CLI profile (~/.databrickscfg)")
    parser.add_argument("--target", help="Bundle target (e.g. prod, dev)")
    parser.add_argument("--auto-approve", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    target_label = args.target or "dev"
    print(f"\nCleaning lakebase → {target_label}")

    if not args.auto_approve and not confirm(target_label):
        print("\nCancelled")
        sys.exit(1)

    steps: list[tuple[str, object]] = [
        ("Destroy", lambda: destroy_bundle(args.profile, args.target)),
        ("Local state", lambda: remove_local_state()),
    ]

    for step_name, step_fn in steps:
        print(f"  {step_name}...")
        try:
            if not step_fn():
                print(f"\nAborted at: {step_name}")
                sys.exit(1)
        except KeyboardInterrupt:
            print("\nCancelled")
            sys.exit(1)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
