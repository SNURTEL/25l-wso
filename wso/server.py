from __future__ import annotations

import asyncio
import contextlib
import enum
import functools
import json
import logging
import os
import sys
from functools import partial
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import libvirt

from wso.config import ISO_PATH
from wso.management import create_bridge_iface, destroy_bridge_iface, destroy_domain, is_domain_active, launch_domain
from wso.utils import get_logger


class ServerState(TypedDict):
    hypervisors: dict[str, HypervisorState]


class HypervisorState(TypedDict):
    domains: dict[str, DomainState]


class HealthCheckState(enum.StrEnum):
    INITIALIZING = enum.auto()
    HEALTHY = enum.auto()
    UNHEALTHY = enum.auto()


class DomainState(TypedDict):
    domain_name: str
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

    @property
    @functools.lru_cache
    def logger(self) -> logging.Logger:
        return get_logger(log_file=self.workdir / "server.log", level=logging.DEBUG)

    @contextlib.asynccontextmanager
    async def connection_context(self):
        self.logger.debug(f"Connecting to {self.hypervisor_url}...")
        try:
            conn = await asyncio.to_thread(partial(libvirt.open, self.hypervisor_url))
            if not conn:
                raise libvirt.libvirtError(f"Failed to open connection to {self.hypervisor_url}")
            yield conn
        finally:
            if conn:
                self.logger.debug(f"Closing connection to {self.hypervisor_url}...")
                await asyncio.to_thread(conn.close)

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

    async def refresh_state_job(self, interval: int = 5):
        while True:
            self.logger.debug("Refreshing state...")
            await self.refresh_state()
            await asyncio.sleep(interval)

    async def launch_domain(self, domain_name: str, n_cpus: int, memory_kib: int, iso_path: str) -> DomainState:
        async with self.connection_context() as conn:
            bridge_iface = f"br-{domain_name[:10]}"
            self.logger.debug(f"Creating iface {bridge_iface}...")
            await create_bridge_iface(name=bridge_iface)
            self.logger.debug(f"Created iface {bridge_iface}")

            self.logger.debug(f"Creating domain {domain_name}...")
            domain = await launch_domain(
                libvirt_connection=conn,
                name=domain_name,
                n_cpus=2,
                memory_kib=2097152,
                bridge_iface_name=bridge_iface,
                iso_path=ISO_PATH,
            )
            self.logger.info(f"Launched domain {domain.name()}")

            return {
                "domain_name": domain.name(),
                "bridge_iface_name": bridge_iface,
                "healthcheck_state": HealthCheckState.INITIALIZING,
                "n_failed_healthchecks": 0,
            }

    async def destroy_domain(self, domain: DomainState):
        domain_name = domain["domain_name"]
        bridge_iface_name = domain["bridge_iface_name"]

        async with self.connection_context() as conn:
            self.logger.debug(f"Destroying domain {domain_name}...")
            await destroy_domain(libvirt_connection=conn, name=domain_name)
            self.logger.info(f"Destroyed domain {domain_name}")

            self.logger.debug(f"Destroying interface {bridge_iface_name}...")
            await destroy_bridge_iface(name=bridge_iface_name)
            self.logger.debug(f"Destroyed interface {bridge_iface_name}")

    async def dummy(self):
        vm_id = str(uuid4())[:8]
        domain_name = f"wso-{vm_id}"

        domain = await self.launch_domain(domain_name=f"wso-{vm_id}", n_cpus=2, memory_kib=2097152, iso_path=ISO_PATH)

        try:
            async with self.connection_context() as conn:
                while True:
                    try:
                        is_domain_active(libvirt_connection=conn, name=domain_name)
                    except libvirt.libvirtError:
                        self.logger.warning(f"Domain {domain_name} is not active, retrying...")
                    await asyncio.sleep(5)
        finally:
            await self.destroy_domain(domain)

    async def _run_jobs(self):
        await asyncio.gather(
            self.refresh_state_job(),
            self.dummy(),
        )

    def serve_forever(self):
        self.logger.info(f"Server running with PID {os.getpid()}")
        try:
            asyncio.run(self._run_jobs())
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, shutting down the domain")
            sys.exit(0)
        except Exception as e:
            self.logger.fatal(f"An error occurred: {e}; aborting")
            self.logger.exception(e)
            sys.exit(1)
        finally:
            self.logger.info(f"Server PID {os.getpid()} terminated")
