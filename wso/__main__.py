import sys
import time
from uuid import uuid4

import libvirt
import nmcli

ISO_PATH = "/home/tomek/Pobrane/alpine-standard-3.21.3-x86_64.iso"
QEMU_BINARY_PATH = "/usr/bin/qemu-system-x86_64"
PHYSICAL_IFACE_NAME = "wlp3s0"


def get_domain_xml(name: str, n_cpus: int, memory_kib: int, bridge_iface_name: str, iso_path):
    domain_xml = f"""
  <domain type='kvm'>
    <name>${name}</name>
    <memory>${memory_kib}</memory>
    <vcpu>${n_cpus}</vcpu>
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
    try:
        conn = libvirt.open("qemu:///system")
    except libvirt.libvirtError:
        print("Failed to open connection to the hypervisor")
        sys.exit(1)

    vm_id = str(uuid4())

    bridge_iface = "wso-${vm_id}"
    create_bridge_iface(name=bridge_iface, physical_iface_name="wlp3s0")

    domain_xml = get_domain_xml(
        name=f"wso-{vm_id}", n_cpus=2, memory_kib=2097152, bridge_iface_name=bridge_iface, iso_path=ISO_PATH
    )

    dom = conn.createXML(domain_xml)
    try:
        if not dom:
            raise SystemExit("Failed to create a domain from an XML definition")

        print("Guest " + dom.name() + " has booted")
        while dom.isActive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\b\bReceived keyboard interrupt, shutting down the domain")
    finally:
        if dom:
            dom.destroy()
            print("Guest " + dom.name() + " terminated")
        conn.close()
        destroy_bridge_iface(name=bridge_iface)
        sys.exit(0)


if __name__ == "__main__":
    main()
