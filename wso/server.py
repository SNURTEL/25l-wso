from __future__ import annotations

import enum
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import libvirt

from wso.config import HYPERVISOR_URL, ISO_PATH, WORKDIR
from wso.management import create_bridge_iface, destroy_bridge_iface, get_domain_xml
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

    def start(self) -> None:
        logger = get_logger(log_file=WORKDIR / "server.log", level=logging.DEBUG)
        try:
            logger.info(f"Daemon running with PID {os.getpid()}")
            try:
                logger.debug(f"Connecting to {HYPERVISOR_URL}...")
                conn = libvirt.open(HYPERVISOR_URL)
            except libvirt.libvirtError:
                logger.error(f"Failed to open connection to {HYPERVISOR_URL}")
                sys.exit(1)

            vm_id = str(uuid4())[:8]

            bridge_iface = f"wso-{vm_id}"
            logger.debug(f"Creating iface {bridge_iface}...")
            create_bridge_iface(name=bridge_iface, physical_iface_name="wlp3s0")

            domain_name = f"wso-{vm_id}"
            domain_xml = get_domain_xml(
                name=domain_name, n_cpus=2, memory_kib=2097152, bridge_iface_name=bridge_iface, iso_path=ISO_PATH
            )

            logger.debug(f"Creating domain {domain_name}...")
            dom = conn.createXML(domain_xml)

            try:
                if not dom:
                    raise SystemExit("Failed to create a domain from an XML definition")

                logger.info("Domain " + dom.name() + " has booted")
                while dom.isActive():
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down the domain")
            finally:
                if dom:
                    dom.destroy()
                    logger.info("Domain " + dom.name() + " terminated")
                conn.close()
                destroy_bridge_iface(name=bridge_iface)
                sys.exit(0)
        except Exception as e:
            logger.fatal(f"An error occurred: {e}; aborting")
            logger.exception(e)
            sys.exit(1)

    def stop(self): ...
