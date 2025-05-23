import asyncio
from functools import partial

import libvirt
import nmcli

from wso.config import PHYSICAL_IFACE_NAME, QEMU_BINARY_PATH


def _get_domain_xml(name: str, n_cpus: int, memory_kib: int, bridge_iface_name: str, iso_path):
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


async def launch_domain(
    libvirt_connection: libvirt.virConnect,
    name: str,
    n_cpus: int,
    memory_kib: int,
    bridge_iface_name: str,
    iso_path: str,
) -> libvirt.virDomain:
    domain_xml = _get_domain_xml(
        name=name, n_cpus=2, memory_kib=2097152, bridge_iface_name=bridge_iface_name, iso_path=iso_path
    )
    dom = await asyncio.to_thread(partial(libvirt_connection.createXML, xmlDesc=domain_xml))
    if not dom:
        raise SystemExit("Failed to create a domain from an XML definition")
    return dom


async def destroy_domain(libvirt_connection: libvirt.virConnect, name: str):
    dom = libvirt_connection.lookupByName(name)
    if not dom:
        raise SystemExit(f"Domain {name} not found")

    await asyncio.to_thread(dom.destroy)


async def create_bridge_iface(name: str, physical_iface_name: str = PHYSICAL_IFACE_NAME):
    assert len(name) <= 13

    connection = name
    connection_slave = f"{name}-s"
    iface = name

    await asyncio.to_thread(
        partial(nmcli.connection.add, name=connection, ifname=iface, conn_type="bridge", autoconnect=True)
    )

    await asyncio.to_thread(
        partial(
            nmcli.connection.add,
            name=connection_slave,
            ifname=physical_iface_name,
            conn_type="bridge-slave",
            options={"master": iface},
            autoconnect=True,
        )
    )

    await asyncio.to_thread(partial(nmcli.connection.up, connection))
    return {"connection": connection, "connection-slave": connection_slave, "iface": iface}


async def destroy_bridge_iface(name: str):
    await asyncio.to_thread(partial(nmcli.connection.delete, name))
    await asyncio.to_thread(partial(nmcli.connection.delete, f"{name}-s"))


# DUMMY FUNCTION FOR DEBUGGING - to be replaced with actual health check
def is_domain_active(libvirt_connection: libvirt.virConnect, name: str) -> bool:
    dom = libvirt_connection.lookupByName(name)
    return dom.isActive()
