from typing import Callable

import daemon.pidfile as pidfile  # type: ignore[import-untyped]

from wso.config import HYPERVISOR_URL, WORKDIR
from wso.server import Server


def daemonize(func: Callable[[], None]) -> None:
    import daemon

    _pidfile = pidfile.PIDLockFile(WORKDIR / "daemon.pid")
    print("Starting daemon")
    with daemon.DaemonContext(pidfile=_pidfile):
        func()


if __name__ == "__main__":
    server = Server(
        workdir=WORKDIR,
        hypervisor_url=HYPERVISOR_URL,
    )

    daemonize(server.serve_forever)
