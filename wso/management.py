import asyncio
import os
from functools import partial

import libvirt

from wso.config import QEMU_BINARY_PATH


def _get_domain_xml(name: str, n_cpus: int, memory_kib: int, network_name: str, iso_path, static_ip: str = None):
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
      </disk>
      <disk type='file' device='disk'>
        <driver name='qemu' type='qcow2'/>
        <source file='/tmp/wso-{name}-disk.qcow2'/>
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


async def create_disk_image(domain_name: str, size_gb: int = 10):
    """Create a qcow2 disk image for the VM"""
    disk_path = f"/tmp/wso-{domain_name}-disk.qcow2"
    cmd = f"qemu-img create -f qcow2 {disk_path} {size_gb}G"
    process = await asyncio.create_subprocess_shell(cmd)
    await process.wait()
    return disk_path


async def create_nat_network(
    libvirt_connection: libvirt.virConnect, network_name: str, bridge_name: str, subnet: str = "192.168.100"
) -> libvirt.virNetwork:
    """Create a NAT network for VM internet access and host connectivity"""
    # Validate bridge name length (Linux interface names max 15 chars)
    if len(bridge_name) > 15:
        raise ValueError(f"Bridge name '{bridge_name}' is too long (max 15 characters)")

    try:
        # Try to get existing network
        network = libvirt_connection.networkLookupByName(network_name)
        if network.isActive():
            return network
        else:
            # Start the network if it exists but is not active
            await asyncio.to_thread(network.create)
            return network
    except libvirt.libvirtError:
        # Network doesn't exist, create it
        network_xml = _get_network_xml(network_name, bridge_name, subnet)
        network = await asyncio.to_thread(partial(libvirt_connection.networkCreateXML, network_xml))
        if not network:
            raise SystemExit(f"Failed to create network {network_name}")
        return network


async def destroy_nat_network(libvirt_connection: libvirt.virConnect, network_name: str):
    """Destroy a NAT network"""
    try:
        network = libvirt_connection.networkLookupByName(network_name)
        if network.isActive():
            await asyncio.to_thread(network.destroy)
    except libvirt.libvirtError:
        # Network doesn't exist or already destroyed
        pass


async def launch_domain(
    libvirt_connection: libvirt.virConnect,
    name: str,
    n_cpus: int,
    memory_kib: int,
    network_name: str,
    iso_path: str,
    static_ip: str = None,
) -> libvirt.virDomain:
    # Create disk image for the VM
    await create_disk_image(name)

    domain_xml = _get_domain_xml(
        name=name,
        n_cpus=n_cpus,
        memory_kib=memory_kib,
        network_name=network_name,
        iso_path=iso_path,
        static_ip=static_ip,
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

    # Clean up the disk image
    disk_path = f"/tmp/wso-{name}-disk.qcow2"
    try:
        os.remove(disk_path)
    except FileNotFoundError:
        pass  # Disk image doesn't exist or already removed


# async def get_domain_ip_address(libvirt_connection: libvirt.virConnect, domain_name: str) -> str | None:
#     """Get the IP address assigned to a domain via DHCP"""
#     try:
#         domain = libvirt_connection.lookupByName(domain_name)
#         if not domain.isActive():
#             return None

#         # Get network interfaces
#         interfaces = await asyncio.to_thread(domain.interfaceAddresses, 0)

#         for interface_name, interface_info in interfaces.items():
#             if interface_info["addrs"]:
#                 for addr in interface_info["addrs"]:
#                     if addr["type"] == 0:  # IPv4 address
#                         return addr["addr"]
#         return None
#     except libvirt.libvirtError:
#         return None


# async def wait_for_domain_ip(libvirt_connection: libvirt.virConnect, domain_name: str, timeout: int = 60) -> str | None:
#     """Wait for a domain to get an IP address"""
#     import time

#     start_time = time.time()

#     while time.time() - start_time < timeout:
#         ip = await get_domain_ip_address(libvirt_connection, domain_name)
#         if ip:
#             return ip
#         await asyncio.sleep(2)

#     return None


# Legacy bridge functions - keeping for compatibility but not used with NAT setup
# async def create_bridge_iface(name: str, physical_iface_name: str = PHYSICAL_IFACE_NAME):
#     assert len(name) <= 13

#     connection = name
#     connection_slave = f"{name}-s"
#     iface = name

#     nmcli.connection.add(name=connection, ifname=iface, conn_type="bridge", autoconnect=True)

#     nmcli.connection.add(
#         name=connection_slave,
#         ifname=physical_iface_name,
#         conn_type="bridge-slave",
#         options={"master": iface},
#         autoconnect=True,
#     )

#     nmcli.connection.modify(
#         connection,
#         options={
#             "bridge.stp": " no",
#             "ipv4.method": "manual",
#             "ipv4.addresses": "10.128.0.128/16",
#             "ipv4.gateway": "10.1.1.1",
#             "ipv4.dns": "10.1.1.1,8.8.8.8,8.8.4.4",
#             "ipv4.dns-search": "example.com",
#         },
#     )

#     await asyncio.to_thread(partial(nmcli.connection.up, connection))
#     return {"connection": connection, "connection-slave": connection_slave, "iface": iface}


# async def destroy_bridge_iface(name: str):
#     await asyncio.to_thread(partial(nmcli.connection.delete, name))
#     await asyncio.to_thread(partial(nmcli.connection.delete, f"{name}-s"))


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


async def create_network_config_script(domain_name: str, static_ip: str, gateway: str = "192.168.100.1") -> str:
    """Create a network configuration script for Alpine Linux"""
    # Create network configuration script for Alpine Linux
    network_script = f"""#!/bin/sh
# Network configuration script for {domain_name}

# Configure eth0 with static IP
ip addr add {static_ip}/24 dev eth0
ip link set eth0 up
ip route add default via {gateway}

# Configure DNS
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf

# Make configuration persistent
cat > /etc/network/interfaces << EOF
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address {static_ip}
    netmask 255.255.255.0
    gateway {gateway}
EOF

echo "Network configured: {static_ip}"
"""

    script_path = f"/tmp/wso-{domain_name}-netconfig.sh"
    with open(script_path, "w") as f:
        f.write(network_script)

    # Make script executable
    os.chmod(script_path, 0o755)

    return script_path
