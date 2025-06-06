import asyncio
import os
import tempfile
from functools import partial
from pathlib import Path

import libvirt

from wso.config import QEMU_BINARY_PATH, SSH_KEY_PATH, VM_SETUP_SCRIPT_PATH, WORKDIR
from wso.utils import get_ssh_public_key


def _get_domain_xml(
    name: str,
    n_cpus: int,
    memory_kib: int,
    network_name: str,
    iso_path: str | os.PathLike,
    cloud_init_iso_path: str | os.PathLike,
) -> str:
    domain_xml = f"""
  <domain type='kvm'>
    <name>{name}</name>
    <memory>{memory_kib}</memory>
    <vcpu>{n_cpus}</vcpu>
    <os>
      <type arch="x86_64">hvm</type>
      <boot dev='cdrom'/>
      <boot dev='hd'/>
    </os>
    <features>
      <acpi/>
      <apic/>
    </features>
    <clock sync="localtime"/>
    <devices>
      <emulator>{QEMU_BINARY_PATH.resolve().absolute()}</emulator>
      <disk type='file' device='cdrom'>
        <driver name='qemu' type='raw'/>
        <source file='{iso_path}'/>
        <target dev='hdc' bus='ide'/>
        <readonly/>
      </disk>
      <disk type='file' device='cdrom'>
        <driver name='qemu' type='raw'/>
        <source file='{cloud_init_iso_path}'/>
        <target dev='hdd' bus='ide'/>
        <readonly/>
      </disk>
      <disk type='file' device='disk'>
        <driver name='qemu' type='qcow2'/>
        <source file='{WORKDIR.resolve().absolute()}/wso-{name}-disk.qcow2'/>
        <target dev='vda' bus='virtio'/>
      </disk>
      <interface type='network'>
        <source network='{network_name}'/>
        <model type='virtio'/>
      </interface>
      <graphics type='vnc' port='-1' listen='127.0.0.1'/>
      <serial type='pty'>
        <target port='0'/>
      </serial>
      <console type='pty'>
        <target type='serial' port='0'/>
      </console>
    </devices>
  </domain>
  """
    return domain_xml


def _get_network_xml(name: str, bridge_name: str, subnet: str = "192.168.100") -> str:
    network_xml = f"""
    <network>
        <name>{name}</name>
        <forward mode="nat">
            <nat>
                <port start="1024" end="65535"/>
            </nat>
        </forward>
        <bridge name="{bridge_name}" stp="on" delay="0"/>
        <ip address="{subnet}.1" netmask="255.255.255.0"/>
    </network>
    """
    return network_xml


async def create_disk_image(domain_name: str, size_gb: int = 1) -> Path:
    """Create a qcow2 disk image for the VM"""
    disk_path = WORKDIR / f"wso-{domain_name}-disk.qcow2"
    cmd = f"qemu-img create -f qcow2 {disk_path} {size_gb}G"
    process = await asyncio.create_subprocess_shell(cmd)
    await process.wait()
    return disk_path


async def get_or_create_nat_network(
    libvirt_connection: libvirt.virConnect, network_name: str, bridge_name: str, subnet: str = "192.168.100"
) -> libvirt.virNetwork:
    if len(bridge_name) > 15:
        raise ValueError(f"Bridge name '{bridge_name}' is too long (max 15 characters)")

    try:
        existing_network = libvirt_connection.networkLookupByName(network_name)
        return existing_network
    except libvirt.libvirtError as e:
        if "Network not found" not in str(e):
            raise
    network_xml = _get_network_xml(network_name, bridge_name, subnet)
    network = await asyncio.to_thread(partial(libvirt_connection.networkCreateXML, network_xml))
    if not network:
        raise SystemExit(f"Failed to create network {network_name}")
    return network


async def destroy_nat_network(libvirt_connection: libvirt.virConnect, network_name: str) -> None:
    network = libvirt_connection.networkLookupByName(network_name)
    await asyncio.to_thread(network.destroy)


async def launch_domain(
    libvirt_connection: libvirt.virConnect,
    name: str,
    n_cpus: int,
    memory_kib: int,
    network_name: str,
    iso_path: str | os.PathLike,
    static_ip: str,
) -> libvirt.virDomain:
    await create_disk_image(name)

    cloud_init_iso_path = await create_cloud_init_iso(name, static_ip)

    domain_xml = _get_domain_xml(
        name=name,
        n_cpus=n_cpus,
        memory_kib=memory_kib,
        network_name=network_name,
        iso_path=str(iso_path),
        cloud_init_iso_path=cloud_init_iso_path,
    )
    dom = await asyncio.to_thread(partial(libvirt_connection.createXML, xmlDesc=domain_xml))
    if not dom:
        raise SystemExit("Failed to create a domain from an XML definition")
    return dom


async def destroy_domain(libvirt_connection: libvirt.virConnect, name: str) -> None:
    dom = libvirt_connection.lookupByName(name)
    if not dom:
        raise SystemExit(f"Domain {name} not found")

    await asyncio.to_thread(dom.destroy)

    disk_path = WORKDIR / f"wso-{name}-disk.qcow2"
    if os.path.exists(disk_path):
        os.remove(disk_path)

    cloud_init_iso_path = WORKDIR / f"wso-{name}-cloud-init.iso"
    if os.path.exists(cloud_init_iso_path):
        os.remove(cloud_init_iso_path)


# DUMMY FUNCTION FOR DEBUGGING - to be replaced with actual health check
def is_domain_active(libvirt_connection: libvirt.virConnect, name: str) -> bool:
    dom = libvirt_connection.lookupByName(name)
    return dom.isActive()  # type: ignore[no-any-return]


async def create_cloud_init_iso(domain_name: str, static_ip: str, gateway: str = "192.168.100.1") -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        meta_data = f"""instance-id: {domain_name}
local-hostname: {domain_name}
"""

        # Create user-data file with network configuration
        user_data = f"""#cloud-config
hostname: {domain_name}
manage_etc_hosts: true

# Network configuration
write_files:
  - path: /etc/network/interfaces
    content: |
      auto lo
      iface lo inet loopback

      auto eth0
      iface eth0 inet static
          address {static_ip}
          netmask 255.255.255.0
          gateway {gateway}
    permissions: '0644'

  - path: /etc/resolv.conf
    content: |
      nameserver 8.8.8.8
      nameserver 8.8.4.4
    permissions: '0644'

runcmd:
  - hostname {domain_name}
  - ifdown eth0 || true
  - ifup eth0
  - setup-apkrepos -c -1
  - apk update
  - apk add openssh-client
  - apk add openssh-server
  - mv /tmp/index.html /var/lib/nginx/html/index.html
  - ssh-keygen -t ed25519 -q -f "/root/.ssh/id_ed25519" -N ""
  - echo "{get_ssh_public_key()}" >> /root/.ssh/authorized_keys
  - touch /initialized

final_message: "Cloud-init configuration completed for {domain_name}"
"""

        meta_data_path = os.path.join(temp_dir, "meta-data")
        user_data_path = os.path.join(temp_dir, "user-data")

        with open(meta_data_path, "w") as f:
            f.write(meta_data)

        with open(user_data_path, "w") as f:
            f.write(user_data)

        iso_path = WORKDIR / f"wso-{domain_name}-cloud-init.iso"
        cmd = [
            "genisoimage",
            "-output",
            str(iso_path.resolve().absolute()),
            "-volid",
            "cidata",
            "-joliet",
            "-rock",
            meta_data_path,
            user_data_path,
        ]

        process = await asyncio.create_subprocess_exec(*cmd)
        await process.wait()

        if process.returncode != 0:
            raise RuntimeError(f"Failed to create cloud-init ISO: {process.returncode}")

        return Path(iso_path)


async def configure_domain(
    ip: str,
    user: str = "root",
    config_script_file: str | os.PathLike = VM_SETUP_SCRIPT_PATH,
) -> None:
    proc = await asyncio.create_subprocess_shell(
        f"scp -o StrictHostKeyChecking=no -o PasswordAuthentication=no -o PreferredAuthentications=publickey -o UserKnownHostsFile=/dev/null -o 'BatchMode=yes' -i {SSH_KEY_PATH} {config_script_file} {user}@{ip}:/setup.sh",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to copy setup script to {ip}: {stderr.decode().strip()}")
    proc = await asyncio.create_subprocess_shell(
        f"ssh -t -o StrictHostKeyChecking=no -o PasswordAuthentication=no -o PreferredAuthentications=publickey -o UserKnownHostsFile=/dev/null -o 'BatchMode=yes' -i {SSH_KEY_PATH} {user}@{ip} 'sh /setup.sh > tee /setup.log'",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to run setup script on {ip}: {stderr.decode().strip()}")
