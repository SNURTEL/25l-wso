import logging
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import daemon.pidfile as pidfile
import libvirt
import nmcli

ISO_PATH = "/home/tomek/Pobrane/alpine-standard-3.21.3-x86_64.iso"
QEMU_BINARY_PATH = "/usr/bin/qemu-system-x86_64"
PHYSICAL_IFACE_NAME = "wlp3s0"
HYPERVISOR_URL = "qemu:///system"
WORKDIR = Path("/tmp/wso-scaler")
WORKDIR.mkdir(parents=True, exist_ok=True)


def get_logger():
    logger = logging.getLogger("wso")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(WORKDIR / "server.log")
    sh = logging.StreamHandler(sys.stdout)
    f_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(f_format)
    f_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh.setFormatter(f_format)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def get_domain_xml(name: str, n_cpus: int, memory_kib: int, bridge_iface_name: str, iso_path):
    domain_xml = f"""
  <domain type='kvm'>
    <name>{name}</name>
    <memory>{memory_kib}</memory>
    <vcpu>{n_cpus}</vcpu>
    <os>
      <type arch="i686">hvm</type>
    </os>
    <clock sync="localtime"/>
    <devices>
      <emulator>{QEMU_BINARY_PATH}</emulator>
      <disk type='file' device='disk'>
        <source file='{iso_path}'/>
        <target dev='hda'/>
      </disk>
      <interface type='bridge'>
        <source bridge='{bridge_iface_name}'/>
        <model type='virtio'/>
      </interface>
      <graphics type='vnc' port='-1' keymap='de'/>
    </devices>
  </domain>
  """
    return domain_xml


def create_bridge_iface(name: str, physical_iface_name: str = PHYSICAL_IFACE_NAME):
    connection = name
    iface = name

    nmcli.connection.add(name=connection, ifname=iface, conn_type="bridge", autoconnect=True)

    nmcli.connection.add(
        name=f"{connection}-slave",
        ifname=physical_iface_name,
        conn_type="bridge-slave",
        options={"master": iface},
        autoconnect=True,
    )

    nmcli.connection.up(connection)
    return {"connection": connection, "iface": iface}


def destroy_bridge_iface(name: str):
    nmcli.connection.delete(name)
    nmcli.connection.delete(f"{name}-slave")


def main():
    logger = get_logger()
    logger.info(f"Hello from {os.getpid()}")
    try:
        logger.info(f"Connecting to {HYPERVISOR_URL}...")
        conn = libvirt.open(HYPERVISOR_URL)
    except libvirt.libvirtError:
        logger.error(f"Failed to open connection to {HYPERVISOR_URL}")
        sys.exit(1)

    vm_id = str(uuid4())

    bridge_iface = "wso-${vm_id}"
    logger.debug("Creating iface ${bridge_iface}...")
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


def main1():
    import daemon

    _pidfile = pidfile.PIDLockFile(WORKDIR / "daemon.pid")
    print("Starting daemon")
    with daemon.DaemonContext(pidfile=_pidfile):
        main()


if __name__ == "__main__":
    main1()
