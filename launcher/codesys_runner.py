from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODESYS_EXE = Path(r"C:\Program Files\CODESYS 3.5.22.10\CODESYS\Common\CODESYS.exe")
DEFAULT_PROFILE = "CODESYS V3.5 SP22 Patch 1"
AGENT_SCRIPT = ROOT / "ide_scripts" / "codesys_agent.py"
STATE_DIR = ROOT / ".codesys_agent"


def _quote(value: str) -> str:
    return '"' + value.replace('"', r'\"') + '"'


def _command_line(codesys_exe: Path, profile: str, script: Path, request_path: Path, no_ui: bool) -> str:
    parts = [
        _quote(str(codesys_exe)),
        "--profile=%s" % _quote(profile),
        "--runscript=%s" % _quote(str(script)),
        "--scriptargs:%s" % _quote(str(request_path)),
    ]
    if no_ui:
        parts.append("--noUI")
    return " ".join(parts)


def _write_request(payload: dict) -> Path:
    request_dir = STATE_DIR / "requests"
    result_dir = STATE_DIR / "results"
    request_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    request_path = request_dir / ("%s-%d.json" % (stamp, os.getpid()))
    payload["result_path"] = str(result_dir / ("%s-%d.result.json" % (stamp, os.getpid())))
    request_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return request_path


def run_request(payload: dict, codesys_exe: Path, profile: str, no_ui: bool, timeout: int) -> dict:
    request_path = _write_request(payload)
    result_path = Path(payload["result_path"])
    cmd = _command_line(codesys_exe, profile, AGENT_SCRIPT, request_path, no_ui)

    completed = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=timeout)
    result = {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "request_path": str(request_path),
        "result_path": str(result_path),
    }

    if result_path.exists():
        result["agent_result"] = json.loads(result_path.read_text(encoding="utf-8"))

    if completed.returncode != 0:
        raise RuntimeError(json.dumps(result, indent=2, sort_keys=True))

    return result


def _base_payload(args: argparse.Namespace, action: str) -> dict:
    payload = {
        "action": action,
        "require_project_path_match": args.require_project_path_match,
        "save": args.save,
    }
    if args.project:
        payload["project_path"] = str(Path(args.project).resolve())
    if args.container:
        payload["container"] = args.container
    return payload


def _print_result(result: dict) -> int:
    print(json.dumps(result, indent=2, sort_keys=True))
    agent_result = result.get("agent_result")
    if agent_result and not agent_result.get("ok", False):
        return 1
    return result["returncode"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CODESYS IDE ScriptEngine requests.")
    parser.add_argument("--codesys-exe", default=str(DEFAULT_CODESYS_EXE))
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--no-ui", action="store_true", help="Start CODESYS with --noUI.")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--project", default=str(ROOT / "FirstProject.project"))
    parser.add_argument("--container", default=None, help="Optional target container object name.")
    parser.add_argument(
        "--no-project-path-match",
        dest="require_project_path_match",
        action="store_false",
        help="Allow editing whichever primary project is open.",
    )
    parser.set_defaults(require_project_path_match=True)
    parser.add_argument("--no-save", dest="save", action="store_false")
    parser.set_defaults(save=True)

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("inspect", help="Inspect the primary project in the CODESYS instance.")

    add_gvl = subparsers.add_parser("add-gvl-var", help="Ensure a GVL variable exists.")
    add_gvl.add_argument("--gvl", default="GVL")
    add_gvl.add_argument("--var", required=True)
    add_gvl.add_argument("--type", default="BOOL")

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        payload = _base_payload(args, "inspect")
    elif args.command == "add-gvl-var":
        payload = _base_payload(args, "add_gvl_var")
        payload.update({
            "gvl_name": args.gvl,
            "var_name": args.var,
            "var_type": args.type,
        })
    else:
        parser.error("Unsupported command: %s" % args.command)

    result = run_request(
        payload=payload,
        codesys_exe=Path(args.codesys_exe),
        profile=args.profile,
        no_ui=args.no_ui,
        timeout=args.timeout,
    )
    return _print_result(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
