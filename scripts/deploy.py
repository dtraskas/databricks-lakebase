#!/usr/bin/env python3
"""
scripts/deploy.py

Deploy the Lakebase app to Databricks Apps.

Usage:
    uv run python -m scripts.deploy
    uv run python -m scripts.deploy --profile my-profile
    uv run python -m scripts.deploy --target prod
    uv run python -m scripts.deploy --skip-build
    uv run python -m scripts.deploy --auto-approve
"""

import argparse
import json
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


ENV_KEYS = ["PGHOST", "PGDATABASE", "PGUSER", "PGPORT", "PGSSLMODE", "ENDPOINT_NAME", "PGPASSWORD"]


def sync_env_to_app_yaml() -> bool:
    env_file = PROJECT_ROOT / ".env"
    app_yaml = PROJECT_ROOT / "app.yaml"

    if not env_file.exists():
        error(".env not found — cannot inject environment into app.yaml")
        return False

    # Parse .env (simple key=value, skip comments and blanks)
    env_vars: dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() in ENV_KEYS:
            env_vars[key.strip()] = value.strip()

    if not env_vars:
        error("No recognised env vars found in .env")
        return False

    # Build the env block
    env_lines = ["env:"]
    for key, value in env_vars.items():
        env_lines.append(f"  - name: {key}")
        env_lines.append(f"    value: '{value}'")

    # Replace the existing env: block (everything from 'env:' to end of file)
    content = app_yaml.read_text()
    if "env:" in content:
        content = content[: content.index("env:")] + "\n".join(env_lines) + "\n"
    else:
        content = content.rstrip() + "\n\n" + "\n".join(env_lines) + "\n"

    app_yaml.write_text(content)
    ok(f"app.yaml env synced ({', '.join(env_vars)})")
    return True


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


def create_app_deployment(profile: str | None, target: str | None) -> bool:
    # Resolve the bundle's file_path for this target so the deployment points
    # at the code that bundle deploy just uploaded.
    validate_cmd = ["databricks", "bundle", "validate", "-o", "json"]
    if profile:
        validate_cmd += ["--profile", profile]
    if target:
        validate_cmd += ["--target", target]

    result = subprocess.run(validate_cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        error("Could not resolve bundle configuration")
        return False

    try:
        config = json.loads(result.stdout)
        source_code_path = config["workspace"]["file_path"]
        app_name = config["resources"]["apps"]["lakebase"]["name"]
    except (KeyError, json.JSONDecodeError) as e:
        error(f"Could not parse bundle config: {e}")
        return False

    cmd = ["databricks", "apps", "deploy", app_name, "--source-code-path", source_code_path]
    if profile:
        cmd += ["--profile", profile]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        error("App deployment failed")
        return False

    return True


def start_app(profile: str | None, target: str | None) -> bool:
    cmd = ["databricks", "apps", "start"]
    if profile:
        cmd += ["--profile", profile]
    if target:
        cmd += ["--target", target]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        error("Failed to start app")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Deploy Lakebase to Databricks Apps")
    parser.add_argument("--profile", help="Databricks CLI profile (~/.databrickscfg)")
    parser.add_argument("--target", help="Bundle target (e.g. prod, dev)")
    parser.add_argument("--skip-build", action="store_true", help="Skip frontend build")
    parser.add_argument("--auto-approve", action="store_true", help="Skip interactive prompts")
    parser.add_argument("--force", action="store_true", help="Force-override Git branch validation")
    args = parser.parse_args()

    target_label = args.target or "dev"
    print(f"\nDeploying lakebase → {target_label}\n")

    steps: list[tuple[str, object]] = [
        ("Prerequisites", lambda: check_prerequisites()),
        ("Auth", lambda: check_auth(args.profile)),
    ]
    if not args.skip_build:
        steps.append(("Frontend", lambda: build_frontend()))
    steps.append(("Env", lambda: sync_env_to_app_yaml()))
    steps.append(("Deploy", lambda: deploy(
        profile=args.profile,
        target=args.target,
        auto_approve=args.auto_approve,
        force=args.force,
    )))
    steps.append(("Release", lambda: create_app_deployment(
        profile=args.profile,
        target=args.target,
    )))
    steps.append(("Start", lambda: start_app(
        profile=args.profile,
        target=args.target,
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
