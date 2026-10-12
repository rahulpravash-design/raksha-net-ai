#!/usr/bin/env python3
"""Check that each app's netlify.toml matches the one layout Netlify is set up for.

    python3 scripts/check_netlify_config.py             # all three apps
    python3 scripts/check_netlify_config.py citizen-web # one app

Netlify resolves ``publish`` against the repository root when a Package directory is used,
and a bare ``npm run build`` at the root builds *every* app. Either mistake makes the Next.js
plugin fail with "publish directory was not found" (docs/DEPLOYMENT.md section 13.2). This
runs in the gate and in CI so that cannot return unnoticed; it reads files only.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS = ("control-center", "citizen-web", "responder-web")


def ci_node_major() -> str | None:
    match = re.search(r'NODE_VERSION:\s*"?(\d+)', (ROOT / ".github/workflows/ci.yml").read_text())
    return match.group(1) if match else None


def problems_for(app: str) -> list[str]:
    path = ROOT / "apps" / app / "netlify.toml"
    if not path.exists():
        return [f"{path.relative_to(ROOT)} is missing"]
    config = tomllib.loads(path.read_text())
    package = json.loads((ROOT / "apps" / app / "package.json").read_text())
    build = config.get("build", {})
    found: list[str] = []

    expected_command = f"npm run build --workspace {package['name']}"
    if build.get("command") != expected_command:
        found.append(f"build.command must be {expected_command!r}, not {build.get('command')!r}")
    expected_publish = f"apps/{app}/.next"
    if build.get("publish") != expected_publish:
        found.append(f"build.publish must be {expected_publish!r}, not {build.get('publish')!r}")
    for key in ("base", "package"):
        if key in build:
            found.append(f"build.{key} must not be set; the dashboard's Package directory selects the app")
    if "plugins" in config:
        found.append("plugins must not be listed; Netlify detects and installs the Next.js plugin")
    if "build" not in package.get("scripts", {}):
        found.append("the app's package.json has no build script")

    node = str(build.get("environment", {}).get("NODE_VERSION", ""))
    if node.split(".")[0] != ci_node_major():
        found.append(f"build.environment.NODE_VERSION {node!r} differs from CI's Node {ci_node_major()}")
    return found


def main(argv: list[str]) -> int:
    apps = argv or list(APPS)
    unknown = [a for a in apps if a not in APPS]
    if unknown:
        print(f"unknown app(s): {', '.join(unknown)}; choose from {', '.join(APPS)}", file=sys.stderr)
        return 2
    failed = False
    for app in apps:
        problems = problems_for(app)
        for problem in problems:
            print(f"apps/{app}/netlify.toml: {problem}", file=sys.stderr)
        failed = failed or bool(problems)
    if not failed:
        print(f"netlify config ok: {', '.join(apps)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
