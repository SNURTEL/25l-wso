import asyncio
import os
import tempfile
from functools import partial
from pathlib import Path

import libvirt

from wso.config import QEMU_BINARY_PATH, WORKDIR


def _get_domain_xml(
    name: str, n_cpus: int, memory_kib: int, network_name: str, iso_path, cloud_init_iso_path: str | None = None
):
    cloud_init_disk = ""
    if cloud_init_iso_path:
        cloud_init_disk = f"""
      <disk type='file' device='cdrom'>
        <driver name='qemu' type='raw'/>
        <source file='{cloud_init_iso_path}'/>
        <target dev='hdd' bus='ide'/>
        <readonly/>
      </disk>"""

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
      <emulator>{QEMU_BINARY_PATH}</emulator>
      <disk type='file' device='cdrom'>
        <driver name='qemu' type='raw'/>
        <source file='{iso_path}'/>
        <target dev='hdc' bus='ide'/>
        <readonly/>
      </disk>{cloud_init_disk}
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


def _get_network_xml(name: str, bridge_name: str, subnet: str = "192.168.100"):
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


async def create_disk_image(domain_name: str, size_gb: int = 1):
    """Create a qcow2 disk image for the VM"""
    disk_path = WORKDIR / f"wso-{domain_name}-disk.qcow2"
    cmd = f"qemu-img create -f qcow2 {disk_path} {size_gb}G"
    process = await asyncio.create_subprocess_shell(cmd)
    await process.wait()
    return disk_path


async def create_nat_network(
    libvirt_connection: libvirt.virConnect, network_name: str, bridge_name: str, subnet: str = "192.168.100"
) -> libvirt.virNetwork:
    if len(bridge_name) > 15:
        raise ValueError(f"Bridge name '{bridge_name}' is too long (max 15 characters)")

    network_xml = _get_network_xml(network_name, bridge_name, subnet)
    network = await asyncio.to_thread(partial(libvirt_connection.networkCreateXML, network_xml))
    if not network:
        raise SystemExit(f"Failed to create network {network_name}")
    return network


async def destroy_nat_network(libvirt_connection: libvirt.virConnect, network_name: str):
    network = libvirt_connection.networkLookupByName(network_name)
    await asyncio.to_thread(network.destroy)


async def launch_domain(
    libvirt_connection: libvirt.virConnect,
    name: str,
    n_cpus: int,
    memory_kib: int,
    network_name: str,
    iso_path: str,
    static_ip: str = None,
) -> libvirt.virDomain:
    await create_disk_image(name)

    cloud_init_iso_path = None
    if static_ip:
        cloud_init_iso_path = await create_cloud_init_iso(name, static_ip)

    domain_xml = _get_domain_xml(
        name=name,
        n_cpus=n_cpus,
        memory_kib=memory_kib,
        network_name=network_name,
        iso_path=iso_path,
        cloud_init_iso_path=cloud_init_iso_path,
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

    disk_path = WORKDIR / f"wso-{name}-disk.qcow2"
    if os.path.exists(disk_path):
        os.remove(disk_path)

    cloud_init_iso_path = WORKDIR / f"wso-{name}-cloud-init.iso"
    if os.path.exists(cloud_init_iso_path):
        os.remove(cloud_init_iso_path)


# DUMMY FUNCTION FOR DEBUGGING - to be replaced with actual health check
def is_domain_active(libvirt_connection: libvirt.virConnect, name: str) -> bool:
    dom = libvirt_connection.lookupByName(name)
    return dom.isActive()


def generate_static_ip(domain_name: str, subnet: str = "192.168.100") -> str:
    """Generate a static IP address based on the domain name"""
    # Extract the domain ID and use it to generate a consistent IP
    domain_id = domain_name.replace("wso-", "")
    # Convert first 6 characters of domain ID to a number for IP generation
    ip_suffix = abs(hash(domain_id[:6])) % 253 + 2  # Range 2-254
    return f"{subnet}.{ip_suffix}"


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

  - path: /etc/nginx/http.d/default.conf
    content: |
        server {{
            listen 80 default_server;
            listen [::]:80 default_server;

            # Everything is a 404
            location / {{
                root   html;
                index  index.html;
            }}

            # You may need this to prevent return 404 recursion.
            location = /404.html {{
                    internal;
            }}
        }}
    permissions: '0644'

  - path: /tmp/index.html
    content: |
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Hello from {domain_name}</title>
            <style>
            html {{ color-scheme: light dark; }}
            body {{ width: 35em; margin: 0 auto;
            font-family: Tahoma, Verdana, Arial, sans-serif; }}
            </style>
        </head>
        <body>
            <h1>Hello from {domain_name}!</h1>
            <p>Nginx running on {domain_name}, {static_ip} </p>
        </body>
        </html>
    permissions: '0644'

# Run commands to apply network configuration
runcmd:
  - ifdown eth0 || true
  - ifup eth0
  - echo "Network configured: {static_ip}"
  - setup-apkrepos -1
  - apk update
  - apk add nginx
  - service nginx start
  - mv /tmp/index.html /var/lib/nginx/html/index.html

# Ensure network service is enabled
packages:
  - ifupdown

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
