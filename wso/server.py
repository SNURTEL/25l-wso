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

import wso.config as config
from wso.management import (
    configure_domain,
    destroy_domain,
    destroy_nat_network,
    get_or_create_nat_network,
    launch_domain,
)
from wso.utils import EnhancedJSONEncoder, get_logger


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

    _healthcheck_tasks: dict[str, asyncio.Task[None]] = {}

    _desired_num_vms = 2

    def __init__(self, workdir: Path, hypervisor_url: str):
        assert not (workdir.exists() and workdir.is_file()), f"Workdir {workdir} already exists and is a file"
        self.workdir = workdir
        self.hypervisor_url = hypervisor_url

        if not self.workdir.exists():
            self.workdir.mkdir(parents=True, exist_ok=True)

        self._state = ServerState(
            hypervisors={
                self.hypervisor_url: HypervisorState(
                    domains={},
                ),
            },
        )

        self._state_changed.set()

    async def handle_msg(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(1024)
        message = data.decode()

        self.logger.debug(f"Received msg {message!r}")

        if message.strip() == "state":
            response = json.dumps(self._state, cls=EnhancedJSONEncoder)
            writer.write("OK\n".encode())
            writer.write(response.encode())
        elif message.startswith("scale "):
            n_vms_str = message.split()[1]
            if not n_vms_str.isnumeric() or not (1 <= int(n_vms_str) <= 100):
                response = "Expected integer <1,100>"
                writer.write("ERROR\n".encode())
                writer.write(response.encode())
            else:
                self._desired_num_vms = int(n_vms_str)
                response = f"Scale to {self._desired_num_vms}"
                writer.write("OK\n".encode())
                writer.write(response.encode())
                self._state_changed.set()
        else:
            self.logger.warning(f"Unknown message received: {message!r}")
            response = f"Unknown command: {message!r}"
            writer.write("ERROR\n".encode())
            writer.write(response.encode())

        await writer.drain()

        writer.close()
        await writer.wait_closed()

    async def run_server(self) -> None:
        server = await asyncio.start_server(self.handle_msg, config.SERVER_HOST, config.SERVER_PORT)

        addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
        self.logger.debug(f"Serving on TCP {addrs}")

        async with server:
            await server.serve_forever()

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

    @staticmethod
    async def healthckeck_single(host: str, port: int, timeout_s: float = 1.0) -> None:
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

    # todo this is wrong
    def _generate_static_ip(self, subnet: str = "192.168.100") -> str:
        ip_suffix = random.randint(2, 254)
        return f"{subnet}.{ip_suffix}"

    async def _configure_domain_task(self, domain: Domain) -> None:
        try:
            self.logger.debug(
                f"Waiting {config.CONFIGURATION_INITIAL_DELAY}s for {domain.domain_name} to boot before attempting configuring..."
            )
            await asyncio.sleep(config.CONFIGURATION_INITIAL_DELAY)
            self.logger.debug(f"Configuring domain {domain.domain_name} with static IP {domain.ip_address}...")

            for _ in range(config.CONFIGURATION_RETRIES):
                try:
                    await configure_domain(ip=domain.ip_address)
                    break
                except Exception as e:
                    self.logger.error(f"Configuration failed for domain {domain.domain_name}: {e}")
                    await asyncio.sleep(config.CONFIGURATION_RETRY_INTERVAL)
            else:
                domain.state = DomainState.UNHEALTHY
                self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain
                self._state_changed.set()
                raise RuntimeError(
                    f"Failed to configure domain {domain.domain_name} after {config.CONFIGURATION_RETRIES} retries"
                )
            self.logger.info(f"Configured domain {domain.domain_name} with static IP {domain.ip_address}")
        except Exception as e:
            self.logger.error(f"Failed to configure domain {domain.domain_name}: {e}")
            self.logger.exception(e)
            raise e

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
            asyncio.create_task(self._configure_domain_task(domain=domain))

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

    async def _healthcheck_task(self, domain: Domain) -> None:
        self.logger.debug(
            f"Waiting {config.HEALTHCHECK_START_DELAY}s before starting healthcheck for domain {domain.domain_name}"
        )
        await asyncio.sleep(config.HEALTHCHECK_START_DELAY)
        while True:
            try:
                await self.healthckeck_single(domain.ip_address, config.HEALTHCHECK_PORT)
                healthy = True
            except HealthCheckFailureException as e:
                self.logger.warning(f"Healthcheck failed for domain {domain.domain_name}: {e}")
                healthy = False
            domain = self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name]
            if healthy and domain.n_success_healthchecks < config.HEALTHCHECK_HEALTHY_THRESHOLD:
                domain.n_success_healthchecks += 1
                if domain.n_success_healthchecks >= config.HEALTHCHECK_HEALTHY_THRESHOLD:
                    domain.state = DomainState.HEALTHY
                    domain.n_failed_healthchecks = 0
                    self.logger.info(f"Domain {domain.domain_name} is healthy")
                self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain
                self._state_changed.set()
            elif not healthy and domain.n_failed_healthchecks < config.HEALTHCHECK_UNHEALTHY_THRESHOLD:
                domain.n_failed_healthchecks += 1
                if domain.n_failed_healthchecks >= config.HEALTHCHECK_UNHEALTHY_THRESHOLD:
                    domain.state = DomainState.UNHEALTHY
                    domain.n_success_healthchecks = 0
                    self.logger.warning(f"Domain {domain.domain_name} is unhealthy, will be destroyed")
                    self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain
                    self._state_changed.set()
                self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain
                self._state_changed.set()

            await asyncio.sleep(config.HEALTHCHECK_INTERVAL)

    async def _start_domain_task(self, domain: Domain) -> None:
        try:
            self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain
            # TODO this should not need to be done manually
            self._state_changed.set()
            launched_domain = await self.launch_domain(domain)
            self._state["hypervisors"][self.hypervisor_url]["domains"][launched_domain.domain_name] = launched_domain
            self._state_changed.set()
            self._healthcheck_tasks[launched_domain.domain_name] = asyncio.create_task(
                self._healthcheck_task(launched_domain),
                name=f"healthcheck {launched_domain.domain_name}",
            )
        except Exception as e:
            self.logger.error(f"Failed to launch domain {domain.domain_name}: {e}")
            self.logger.exception(e)
            del self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name]
            self._state_changed.set()
            raise e

    async def _destroy_domain_task(self, domain: Domain) -> None:
        try:
            domain.state = DomainState.TERMINATING
            self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name] = domain
            self._state_changed.set()
            if domain.domain_name in self._healthcheck_tasks.keys():
                self.logger.debug(f"Cancelling healthcheck task for domain {domain.domain_name}")
                self._healthcheck_tasks[domain.domain_name].cancel()
                del self._healthcheck_tasks[domain.domain_name]
            await self.destroy_domain(domain)
            del self._state["hypervisors"][self.hypervisor_url]["domains"][domain.domain_name]
        except Exception as e:
            self.logger.error(f"Failed to destroy domain {domain.domain_name}: {e}")
            self.logger.exception(e)
            raise e

    async def respond_to_state_change(self) -> None:
        while True:
            await self._state_changed.wait()

            unhealthy_domains = [
                domain
                for domain in self._state["hypervisors"][self.hypervisor_url]["domains"].values()
                if domain.state == DomainState.UNHEALTHY
            ]
            for domain in unhealthy_domains:
                self.logger.warning(f"Domain {domain.domain_name} is unhealthy, destroying")
                asyncio.create_task(self._destroy_domain_task(domain), name=f"destroy {domain.domain_name}")

            running_domains = [
                domain
                for domain in self._state["hypervisors"][self.hypervisor_url]["domains"].values()
                if domain.state in (DomainState.LAUNCHING, DomainState.HEALTHY, DomainState.HEALTHCHECK_INITIALIZING)
            ]
            healthy_domains = [
                domain
                for domain in self._state["hypervisors"][self.hypervisor_url]["domains"].values()
                if domain.state == DomainState.HEALTHY
            ]

            if len(running_domains) < self._desired_num_vms:
                self.logger.info(
                    f"{len(running_domains)} domains running, {self._desired_num_vms} expected, launching {self._desired_num_vms - len(running_domains)} more..."
                )
                for _ in range(self._desired_num_vms - len(running_domains)):
                    domain = Domain(
                        n_cpus=1,
                        memory_kib=1024 * 1024,
                        iso_path=config.ISO_PATH,
                        ip_address=self._generate_static_ip(subnet="192.168.100"),
                        ip_subnet="192.168.100",
                    )
                    asyncio.create_task(self._start_domain_task(domain), name=f"launch {domain.domain_name}")
            elif len(healthy_domains) > self._desired_num_vms:
                n_destroy = len(healthy_domains) - self._desired_num_vms
                self.logger.info(
                    f"{len(healthy_domains)} healthy domains running, {self._desired_num_vms} expected, destroying {n_destroy} excess..."
                )
                picks = random.sample(healthy_domains, n_destroy)
                for domain in picks:
                    asyncio.create_task(self._destroy_domain_task(domain), name=f"destroy {domain.domain_name}")

            self._state_changed.clear()

    async def _run_jobs(self) -> None:
        await asyncio.gather(
            self.respond_to_state_change(),
            self.run_server(),
        )

    async def _cleanup(self) -> None:
        await asyncio.gather(
            *(
                self._destroy_domain_task(domain)
                for domain in self._state["hypervisors"][self.hypervisor_url]["domains"].values()
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
