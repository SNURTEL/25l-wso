import argparse
import json
import subprocess
from typing import Callable

import daemon.pidfile as pidfile  # type: ignore[import-untyped]

import wso.cli as cli
from wso.config import HYPERVISOR_URL, WORKDIR
from wso.server import Server


def daemonize(func: Callable[[], None]) -> None:
    import daemon

    _pidfile = pidfile.PIDLockFile(WORKDIR / "daemon.pid")
    print("Starting daemon")
    with daemon.DaemonContext(pidfile=_pidfile):
        func()


def get_pid() -> int | None:
    try:
        with open(WORKDIR / "daemon.pid", "r") as f:
            return int(f.read().strip())
    except FileNotFoundError:
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WSO Scaler Server")
    valid_commands = ["start", "stop", "state", "scale"]
    parser.add_argument(
        "command",
        choices=valid_commands,
        help="Command to execute: " + ", ".join(valid_commands),
    )
    parser.add_argument(
        "args",
        nargs="*",
        help="Arguments for the command, if any.",
    )
    args = parser.parse_args()

    if args.command == "start":
        if args.args:
            print("Usage: wso start")
            exit(1)
        server = Server(
            workdir=WORKDIR,
            hypervisor_url=HYPERVISOR_URL,
        )
        daemonize(server.serve_forever)
    elif args.command == "stop":
        if args.args:
            print("Usage: wso stop")
            exit(1)
        pid = get_pid()
        if pid is None:
            print("Daemon is not running")
            exit(0)
        print("Stopping daemon")
        proc = subprocess.Popen(["kill", "-TERM", str(pid)])
        proc.wait()
        if proc.returncode != 0:
            print("Failed to stop daemon. Is it running?")
        print("Daemon stopped.")
    elif args.command == "state":
        if args.args:
            print("Usage: wso state")
            exit(1)
        pid = get_pid()
        if pid is None:
            print("Daemon is not running")
            exit(0)
        else:
            print(f"Daemon is running with PID {pid}")

            response = cli.send_msg("state")
            print(json.dumps(json.loads(response), indent=2, sort_keys=True))
            exit(0)
    elif args.command == "scale":
        if not args.args or len(args.args) != 1 or not args.args[0].isnumeric() or not (1 <= int(args.args[0]) <= 100):
            print("Usage: wso scale <number_of_vms> (1-100)")
            exit(1)
        response = cli.send_msg(f"scale {' '.join(args.args)}")
        print(response)
    else:
        print(f"Unknown command: {args.command}")
        print("Valid commands are: " + ", ".join(valid_commands))
        exit(1)
