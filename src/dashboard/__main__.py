"""Start the dashboard on this machine only; open it through VS Code port forwarding.

  python -m src.dashboard [--port 8050]                 uploads change the dashboard's workspace
  python -m src.dashboard --reset-workspace             start the workspace again from the reference run
  python -m src.dashboard --read-only --results PATH    show a saved run, without uploads

The workspace (outputs/dashboard/workspace) is a copy of data/courses and of the reference run,
made the first time; uploads never change data/courses or the reference run.
"""
import argparse
import json
import re
import socket
import subprocess
import urllib.request
from pathlib import Path

from src.common import ROOT
from src.dashboard.accounts import DEFAULT_ACCOUNTS, AccountStore
from src.dashboard.app import APP_NAME, COOKIE, create_app
from src.dashboard.data import AuditView
from src.dashboard.workspace import DEFAULT_REFERENCE, DEFAULT_WORKSPACE, Workspace

DEFAULT_PORT = 8050  # 8000-8002 are often taken by other users on the shared GPU node.


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def dashboard_running(port: int) -> bool:
    """Whether the program already on this port is a SkillAlignRAG dashboard."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            return json.load(response).get("app") == APP_NAME
    except (OSError, ValueError):
        return False


def port_holder(port: int) -> dict | None:
    """Your own process listening on the port: its PID, state and command (Linux only)."""
    try:
        listing = subprocess.run(["ss", "-ltnpH", f"sport = :{port}"], capture_output=True, text=True, timeout=5).stdout
        pid = int(re.search(r"pid=(\d+)", listing).group(1))
        status = Path(f"/proc/{pid}/status").read_text()
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
        return None
    state = re.search(r"^State:\s+(\S)", status, re.M)
    return {"pid": pid, "state": state.group(1) if state else "?", "command": command}


def busy_port_message(port: int) -> str | None:
    """Why the port is busy, when it is one of your own dashboards; otherwise None."""
    holder = port_holder(port)
    if holder and "src.dashboard" in holder["command"]:
        pid = holder["pid"]
        if holder["state"] == "T":
            return (f"A dashboard you paused (probably with Ctrl+Z) still holds port {port} as process {pid}, so its "
                    f"pages never load. Stop it with: kill -CONT {pid}; kill {pid}\n"
                    "Stop dashboards with Ctrl+C, not Ctrl+Z.")
        return f"A SkillAlignRAG dashboard is already running on port {port} as process {pid}. Stop it first: kill {pid}"
    if dashboard_running(port):
        return (f"A SkillAlignRAG dashboard is already running on port {port}, perhaps an older copy. "
                "Stop it first (Ctrl+C in its terminal, or: pkill -f 'python -m src.dashboard'), then start again.")
    return None




def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE, help="Folder that uploads change")
    parser.add_argument("--reset-workspace", action="store_true", help="Discard uploads and start again from --results")
    parser.add_argument("--read-only", action="store_true", help="Show --results without a workspace or uploads")
    parser.add_argument("--results", type=Path, default=DEFAULT_REFERENCE,
                        help="Saved audit run the workspace starts from, or the run shown with --read-only")
    parser.add_argument("--catalog", type=Path, default=ROOT / "outputs" / "course_catalog_manifest.json")
    parser.add_argument("--lookup", type=Path, default=ROOT / "outputs" / "verbatim_lookup_store.json",
                        help="Verbatim page text, for showing cited pages")
    parser.add_argument("--chunks", type=Path, default=ROOT / "outputs" / "parsed_course_chunks.json",
                        help="Line-broken page text, for laying out the source text")
    parser.add_argument("--accounts", type=Path, default=DEFAULT_ACCOUNTS)
    parser.add_argument("--static", type=Path, default=ROOT / "dashboard" / "dist", help="Built front end")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if not args.accounts.exists():
        parser.exit(1, f"No accounts yet; create one with: python -m src.dashboard.accounts add NAME --role approved_staff\n")
    if not port_is_free(args.port):
        message = busy_port_message(args.port)
        if message:
            parser.exit(1, message + "\n")
    if not port_is_free(args.port):
        free = next((p for p in range(args.port + 1, args.port + 100) if port_is_free(p)), None)
        hint = f" Port {free} is free: python -m src.dashboard --port {free}" if free else ""
        parser.exit(1, f"Port {args.port} is already in use, perhaps by another user on this node.{hint}\n")
    import uvicorn
    workspace, view = None, None
    if args.read_only:
        view = AuditView(args.results, args.catalog, args.lookup, args.chunks)
    else:
        if args.reset_workspace or not (args.workspace / "results.json").exists():
            print(f"Creating the dashboard workspace from {args.results.parent.name} (a copy; data/courses is not changed)…")
            Workspace.create(args.workspace, ROOT / "data", ROOT / "outputs", args.results)
        workspace = Workspace(args.workspace).open()
        workspace.start()
    # A cookie per port: browsers share cookies across ports, so two dashboards would sign each other out.
    app = create_app(view, AccountStore(args.accounts), args.static, cookie_name=f"{COOKIE}_{args.port}", workspace=workspace)
    # 127.0.0.1 only: other users of the node cannot reach it; VS Code forwards it to the laptop.
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
