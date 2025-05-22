from __future__ import annotations

import enum
import json
from pathlib import Path
from typing import TypedDict


class ServerState(TypedDict):
    hypervisors: dict[str, HypervisorState]


class HypervisorState(TypedDict):
    domains: dict[str, DomainState]


class HealthCheckState(enum.StrEnum):
    INITIALIZING = enum.auto()
    HEALTHY = enum.auto()
    UNHEALTHY = enum.auto()


class DomainState(TypedDict):
    bridge_iface_name: str
    healthcheck_state: HealthCheckState
    n_failed_healthchecks: int


class Server:
    state: ServerState

    def __init__(self, workdir: Path, hypervisor_url: str):
        assert not (workdir.exists() and workdir.is_file()), f"Workdir {workdir} already exists and is a file"
        self.workdir = workdir
        self.hypervisor_url = hypervisor_url
        self.state_file = workdir / "state.json"

    async def refresh_state(self):
        if not self.workdir.exists():
            self.workdir.mkdir(parents=True, exist_ok=True)

        if not self.state_file.exists():
            state = ServerState(
                hypervisors={
                    self.hypervisor_url: HypervisorState(
                        domains={},
                    ),
                },
            )
        else:
            with self.state_file.open("r") as f:
                state: ServerState = json.load(f)

        with self.state_file.open("w") as f:
            json.dump(state, f, indent=2)

    def start(self): ...

    def stop(self): ...
