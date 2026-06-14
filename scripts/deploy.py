#!/usr/bin/env python3
"""
scripts/deploy.py

Deploy the Lakebase app to Databricks Apps.

Flow: bundle deploy (creates/updates the app + compute) → wait for the compute
to become ACTIVE → apps deploy (uploads and runs the code). The wait matters on
a from-scratch deploy: a newly created app's compute is still provisioning and
`apps deploy` fails if it runs before the compute is ready.

Usage:
    uv run python -m scripts.deploy
    uv run python -m scripts.deploy --profile my-profile
    uv run python -m scripts.deploy --target prod
    uv run python -m scripts.deploy --skip-build
    uv run python -m scripts.deploy --auto-approve
    uv run python -m scripts.deploy --timeout 900
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
POLL_INTERVAL = 5  # seconds between app-status polls


def ok(msg: str):
    print(f"  [✓] {msg}")


def info(msg: str):
    print(f"  [*] {msg}")


def error(msg: str):
    print(f"  [!] {msg}")


def check_prerequisites() -> bool:
    missing = []

    for tool in ["databricks", "uv", "node", "npm"]:
        if subprocess.run([tool, "--version"], capture_output=True).returncode != 0:
            missing.append(tool)

    if missing:
        error(f"Missing tools: {', '.join(missing)}")
        return False

    for fname in ["databricks.yaml", "app.yaml"]:
        if not (PROJECT_ROOT / fname).exists():
            error(f"{fname} not found")
            return False

    return True


def check_auth(profile: str | None) -> bool:
    cmd = ["databricks", "auth", "describe"]
    if profile:
        cmd += ["--profile", profile]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        error("Not authenticated. Run: databricks auth login")
        return False

    host_line = next((l for l in result.stdout.splitlines() if l.startswith("Host:")), None)
    user_line = next((l for l in result.stdout.splitlines() if l.startswith("User:")), None)
    if host_line and user_line:
        ok(f"{user_line.split(':', 1)[1].strip()} @ {host_line.split(':', 1)[1].strip()}")
    else:
        ok("Authenticated")
    return True


def build_frontend() -> bool:
    frontend_dir = PROJECT_ROOT / "frontend"

    info("Installing frontend dependencies...")
    result = subprocess.run(["npm", "install"], cwd=frontend_dir, capture_output=True, text=True)
    if result.returncode != 0:
        error("npm install failed:\n" + result.stderr)
        return False

    info("Building frontend...")
    result = subprocess.run(["npm", "run", "build"], cwd=frontend_dir, capture_output=True, text=True)
    if result.returncode != 0:
        error("npm run build failed:\n" + result.stderr)
        return False

    if not (frontend_dir / "dist").exists():
        error("Build output not found at frontend/dist")
        return False

    ok("Frontend built")
    return True


def resolve_bundle_config(profile: str | None, target: str | None) -> tuple[str, str] | None:
    """Return (source_code_path, app_name) from the resolved bundle config."""
    cmd = ["databricks", "bundle", "validate", "-o", "json"]
    if profile:
        cmd += ["--profile", profile]
    if target:
        cmd += ["--target", target]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        error("Could not resolve bundle configuration")
        return None

    try:
        config = json.loads(result.stdout)
        return (
            config["workspace"]["file_path"],
            config["resources"]["apps"]["lakebase"]["name"],
        )
    except (KeyError, json.JSONDecodeError) as e:
        error(f"Could not parse bundle config: {e}")
        return None


def deploy(profile: str | None, target: str | None, auto_approve: bool, force: bool) -> bool:
    cmd = ["databricks", "bundle", "deploy"]
    if profile:
        cmd += ["--profile", profile]
    if target:
        cmd += ["--target", target]
    if auto_approve:
        cmd.append("--auto-approve")
    if force:
        cmd.append("--force")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        error("Deployment failed")
        return False

    return True


def _get_app(app_name: str, profile: str | None) -> dict | None:
    cmd = ["databricks", "apps", "get", app_name, "-o", "json"]
    if profile:
        cmd += ["--profile", profile]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _start_app(app_name: str, profile: str | None) -> bool:
    cmd = ["databricks", "apps", "start", app_name]
    if profile:
        cmd += ["--profile", profile]
    return subprocess.run(cmd).returncode == 0


def wait_for_app_ready(app_name: str, profile: str | None, timeout: int) -> bool:
    """Poll until the app's compute is ACTIVE.

    Needed for from-scratch deploys: `bundle deploy` creates the app but its
    compute provisions asynchronously, and `apps deploy` fails against a compute
    that is still STARTING. If the compute comes up STOPPED, start it.
    """
    deadline = time.time() + timeout
    started = False

    while time.time() < deadline:
        app = _get_app(app_name, profile)
        if app is None:
            info("App not visible yet — waiting...")
            time.sleep(POLL_INTERVAL)
            continue

        compute_state = (app.get("compute_status") or {}).get("state")

        if compute_state == "ACTIVE":
            ok("App compute is active")
            return True
        if compute_state == "ERROR":
            msg = (app.get("compute_status") or {}).get("message", "")
            error(f"App compute is in ERROR state. {msg}")
            return False
        if compute_state == "STOPPED" and not started:
            info("App compute is stopped — starting it...")
            _start_app(app_name, profile)
            started = True
            continue

        info(f"Waiting for app compute (state: {compute_state or 'unknown'})...")
        time.sleep(POLL_INTERVAL)

    error(f"Timed out after {timeout}s waiting for the app compute to become active")
    return False


def create_app_deployment(app_name: str, source_code_path: str, profile: str | None) -> bool:
    """Upload and run the code that `bundle deploy` just synced to the workspace."""
    cmd = ["databricks", "apps", "deploy", app_name, "--source-code-path", source_code_path]
    if profile:
        cmd += ["--profile", profile]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        error("App deployment failed")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Deploy Lakebase to Databricks Apps")
    parser.add_argument("--profile", help="Databricks CLI profile (~/.databrickscfg)")
    parser.add_argument("--target", help="Bundle target (e.g. prod, dev)")
    parser.add_argument("--skip-build", action="store_true", help="Skip frontend build")
    parser.add_argument("--auto-approve", action="store_true", help="Skip interactive prompts")
    parser.add_argument("--force", action="store_true", help="Force-override Git branch validation")
    parser.add_argument(
        "--timeout", type=int, default=600,
        help="Seconds to wait for the app compute to become active (default: 600)",
    )
    args = parser.parse_args()

    target_label = args.target or "dev"
    print(f"\nDeploying lakebase → {target_label}\n")

    # Resolved once after the bundle deploy step populates it.
    config: dict[str, str] = {}

    def resolve_step() -> bool:
        resolved = resolve_bundle_config(args.profile, args.target)
        if resolved is None:
            return False
        config["source_code_path"], config["app_name"] = resolved
        ok(f"App: {config['app_name']}")
        return True

    steps: list[tuple[str, object]] = [
        ("Prerequisites", lambda: check_prerequisites()),
        ("Auth", lambda: check_auth(args.profile)),
    ]
    if not args.skip_build:
        steps.append(("Frontend", lambda: build_frontend()))
    steps.append(("Deploy", lambda: deploy(
        profile=args.profile,
        target=args.target,
        auto_approve=args.auto_approve,
        force=args.force,
    )))
    steps.append(("Resolve", resolve_step))
    steps.append(("Wait", lambda: wait_for_app_ready(
        config["app_name"], args.profile, args.timeout,
    )))
    steps.append(("Release", lambda: create_app_deployment(
        config["app_name"], config["source_code_path"], args.profile,
    )))

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
