from __future__ import annotations

import asyncio
import contextlib
import datetime
import enum
import errno
import functools
import json
import logging
import os
import random
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import AsyncGenerator, TypedDict
from uuid import uuid4

import libvirt

from wso.config import ISO_PATH
from wso.management import (
    destroy_domain,
    destroy_nat_network,
    get_or_create_nat_network,
    launch_domain,
)
from wso.utils import get_logger


class ServerState(TypedDict):
    hypervisors: dict[str, HypervisorState]


class HypervisorState(TypedDict):
    domains: dict[str, Domain]


class DomainState(enum.StrEnum):
    LAUNCHING = enum.auto()
    HEALTHCHECK_INITIALIZING = enum.auto()
    HEALTHY = enum.auto()
    UNHEALTHY = enum.auto()
    TERMINATING = enum.auto()


@dataclass(init=False, slots=True)
class Domain:
    domain_name: str
    domain_id: str
    state: DomainState
    n_cpus: int
    memory_kib: int
    iso_path: Path
    network_name: str
    bridge_name: str
    ip_address: str
    ip_subnet: str
    n_success_healthchecks: int
    n_failed_healthchecks: int
    started_at: datetime.datetime | None

    def __init__(self, n_cpus: int, memory_kib: int, iso_path: Path, ip_address: str, ip_subnet: str):
        self.domain_id = str(uuid4())[:8]

        self.domain_name = f"wso-{self.domain_id}"
        self.network_name = "wso-net"
        self.bridge_name = "wso-virbr"

        self.n_success_healthchecks = 0
        self.n_failed_healthchecks = 0
        self.started_at = None
        self.state = DomainState.LAUNCHING

        self.n_cpus = n_cpus
        self.memory_kib = memory_kib
        self.iso_path = iso_path.resolve().absolute()
        self.ip_address = ip_address
        self.ip_subnet = ip_subnet


class HealthCheckFailureException(Exception): ...


class Server:
    _state: ServerState
    _state_changed = asyncio.Event()

    def __init__(self, workdir: Path, hypervisor_url: str):
        assert not (workdir.exists() and workdir.is_file()), f"Workdir {workdir} already exists and is a file"
        self.workdir = workdir
        self.hypervisor_url = hypervisor_url
        self.state_file = workdir / "state.json"

        if not self.workdir.exists():
            self.workdir.mkdir(parents=True, exist_ok=True)

        if not self.state_file.exists():
            self._state = ServerState(
                hypervisors={
                    self.hypervisor_url: HypervisorState(
                        domains={},
                    ),
                },
            )
        else:
            with self.state_file.open("r") as f:
                # TODO replace with shelve
                self._state: ServerState = json.load(f)

        self._state_changed.set()

    @property
    def state(self) -> ServerState:
        return self._state

    @state.setter
    def state(self, value: ServerState) -> None:
        changed = self._state != value
        self._state = value
        self.write_state()
        if changed:
            self._state_changed.set()

    def write_state(self) -> None:
        with self.state_file.open("w") as f:
            self.logger.debug(f"Saving state to {self.state_file}...")
            json.dump(self._state, f, indent=2)

    @property
    @functools.lru_cache
    def logger(self) -> logging.Logger:
        return get_logger(log_file=self.workdir / "server.log", level=logging.DEBUG)

    @contextlib.asynccontextmanager
    async def connection_context(self) -> AsyncGenerator[libvirt.virConnect]:
        conn = await asyncio.to_thread(partial(libvirt.open, self.hypervisor_url))
        if not conn:
            raise libvirt.libvirtError(f"Failed to open connection to {self.hypervisor_url}")
        try:
            yield conn
        finally:
            if conn:
                await asyncio.to_thread(conn.close)

    async def healthckeck_single(self, host: str, port: int, timeout_s: float = 1.0) -> None:
        try:
            future = asyncio.open_connection(host, port)
            _, writer = await asyncio.wait_for(future, timeout=timeout_s)
        except asyncio.TimeoutError as e:
            exception_msg = f"Healthcheck failed: timeout after {timeout_s}s while connecting to {host}:{port}"
            raise HealthCheckFailureException(exception_msg) from e
        except OSError as e:
            _errno, msg = e.args
            exception_msg = f"Healthcheck failed: [Error {_errno}] {errno.errorcode.get(_errno, '??? Unknown error')}: {msg} while connecting to {host}:{port}"
            raise HealthCheckFailureException(exception_msg) from e
        writer.close()

    def _generate_static_ip(self, subnet: str = "192.168.100") -> str:
        ip_suffix = random.randint(2, 254)
        return f"{subnet}.{ip_suffix}"

    async def launch_domain(self, domain: Domain) -> Domain:
        async with self.connection_context() as conn:
            self.logger.debug(f"Getting NAT network {domain.network_name}...")
            await get_or_create_nat_network(
                libvirt_connection=conn,
                network_name=domain.network_name,
                bridge_name=domain.bridge_name,
                subnet="192.168.100",
            )

            self.logger.debug(f"Launching domain {domain.domain_name}...")
            _ = await launch_domain(
                libvirt_connection=conn,
                name=domain.domain_name,
                n_cpus=domain.n_cpus,
                memory_kib=domain.memory_kib,
                network_name=domain.network_name,
                iso_path=domain.iso_path,
                static_ip=domain.ip_address,
            )
            self.logger.info(f"Launched domain {domain.domain_name} with static IP {domain.ip_address}")

            domain.state = DomainState.HEALTHCHECK_INITIALIZING
            domain.started_at = datetime.datetime.now()
            return domain

    async def destroy_domain(self, domain: Domain) -> None:
        domain_name = domain.domain_name
        network_name = domain.network_name

        async with self.connection_context() as conn:
            try:
                self.logger.debug(f"Destroying domain {domain_name}...")
                await destroy_domain(libvirt_connection=conn, name=domain_name)
                self.logger.info(f"Destroyed domain {domain_name}")
            except Exception as e:
                self.logger.error(f"Failed to destroy domain {domain_name} or network {network_name}: {e}")
                self.logger.exception(e)
                raise

    async def destroy_nat_network(self, network_name: str) -> None:
        async with self.connection_context() as conn:
            try:
                self.logger.debug(f"Destroying NAT network {network_name}...")
                await destroy_nat_network(libvirt_connection=conn, network_name=network_name)
                self.logger.info(f"Destroyed NAT network {network_name}")
            except Exception as e:
                self.logger.error(f"Failed to destroy NAT network {network_name}: {e}")
                self.logger.exception(e)
                raise

    async def _start_domain_task(self, domain: Domain) -> None:
        try:
            self.state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain
            # TODO this should not need to be done manually
            self._state_changed.set()
            launched_domain = await self.launch_domain(domain)
            self.state["hypervisors"][self.hypervisor_url]["domains"][launched_domain.domain_name] = launched_domain
            self._state_changed.set()
        except Exception as e:
            self.logger.error(f"Failed to launch domain {domain.domain_name}: {e}")
            self.logger.exception(e)
            del self.state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name]
            self._state_changed.set()
            raise e

    async def _destroy_domain_task(self, domain: Domain) -> None:
        try:
            domain.state = DomainState.TERMINATING
            self.state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain
            self._state_changed.set()
            await self.destroy_domain(domain)
            del self.state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name]
        except Exception as e:
            self.logger.error(f"Failed to destroy domain {domain.domain_name}: {e}")
            self.logger.exception(e)
            raise e

    async def respond_to_state_change(self) -> None:
        N_VMS = 2

        while True:
            await self._state_changed.wait()

            unhealthy_domains = [
                domain
                for domain in self.state["hypervisors"][self.hypervisor_url]["domains"].values()
                if domain.state == DomainState.UNHEALTHY
            ]
            for domain in unhealthy_domains:
                self.logger.warning(f"Domain {domain.domain_name} is unhealthy, destroying it...")
                asyncio.create_task(self._destroy_domain_task(domain), name=f"destroy {domain.domain_name}")

            running_domains = [
                domain
                for domain in self.state["hypervisors"][self.hypervisor_url]["domains"].values()
                if domain.state in (DomainState.LAUNCHING, DomainState.HEALTHY, DomainState.HEALTHCHECK_INITIALIZING)
            ]

            if len(running_domains) < N_VMS:
                self.logger.info(
                    f"{len(running_domains)} domains running, launching {N_VMS - len(running_domains)} more..."
                )
                for _ in range(N_VMS - len(running_domains)):
                    domain = Domain(
                        n_cpus=1,
                        memory_kib=1024 * 1024,
                        iso_path=ISO_PATH,
                        ip_address=self._generate_static_ip(subnet="192.168.100"),
                        ip_subnet="192.168.100",
                    )
                    asyncio.create_task(self._start_domain_task(domain), name=f"launch {domain.domain_name}")
            else:
                self.logger.info(f"{len(running_domains)} domains running, nothing to launch")
            self._state_changed.clear()
            await asyncio.sleep(5)

    # async def dummy(self) -> None:
    #     domain = Domain(
    #         n_cpus=2,
    #         memory_kib=2097152,
    #         iso_path=ISO_PATH,
    #         ip_address=self._generate_static_ip(subnet="192.168.100"),
    #         ip_subnet="192.168.100",
    #     )

    #     domain = await self.launch_domain(domain)
    #     self.state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain

    #     try:
    #         async with self.connection_context() as conn:
    #             while True:
    #                 try:
    #                     is_domain_active(libvirt_connection=conn, name=domain.domain_name)
    #                 except libvirt.libvirtError:
    #                     self.logger.warning(f"Domain {domain.domain_name} is not active, retrying...")
    #                 await asyncio.sleep(5)
    #     finally:
    #         await self.destroy_domain(domain)

    async def _run_jobs(self) -> None:
        await asyncio.gather(
            self.respond_to_state_change(),
        )

    async def _cleanup(self) -> None:
        await asyncio.gather(
            *(
                self._destroy_domain_task(domain)
                for domain in self.state["hypervisors"][self.hypervisor_url]["domains"].values()
                if domain.state not in (DomainState.TERMINATING, DomainState.LAUNCHING)
            ),
            self.destroy_nat_network("wso-net"),
        )

    def serve_forever(self) -> None:
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
            asyncio.run(self._cleanup())
            self.logger.info(f"Server PID {os.getpid()} terminated")
