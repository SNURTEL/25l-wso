#!/usr/bin/env python3
"""
Test script to verify VM connectivity and networking setup.
This script demonstrates how the VMs can:
1. Access the internet via NAT
2. Be reached from the host machine via their local IP
"""

import asyncio
import subprocess
import sys

import libvirt

from wso.config import HYPERVISOR_URL
from wso.management import get_domain_ip_address


async def test_vm_connectivity(domain_name: str):
    """Test connectivity to a running VM"""
    print(f"Testing connectivity for domain: {domain_name}")

    # Connect to libvirt
    conn = libvirt.open(HYPERVISOR_URL)
    if not conn:
        print(f"Failed to connect to {HYPERVISOR_URL}")
        return False

    try:
        # Get domain IP
        ip_address = await get_domain_ip_address(conn, domain_name)
        if not ip_address:
            print(f"Could not get IP address for domain {domain_name}")
            return False

        print(f"Domain {domain_name} has IP address: {ip_address}")

        # Test ping connectivity from host to VM
        print(f"Testing ping from host to VM at {ip_address}...")
        try:
            result = subprocess.run(
                ["ping", "-c", "3", ip_address], capture_output=True, text=True, timeout=10, check=False
            )
            if result.returncode == 0:
                print("✓ Host can ping VM successfully")
            else:
                print("✗ Host cannot ping VM")
                print(f"Ping output: {result.stdout}")
        except subprocess.TimeoutExpired:
            print("✗ Ping timed out")
        except FileNotFoundError:
            print("✗ Ping command not found")

        # Test SSH connectivity (if SSH is running in VM)
        print(f"Testing SSH connectivity to {ip_address}...")
        try:
            result = subprocess.run(
                ["nc", "-z", "-v", ip_address, "22"], capture_output=True, text=True, timeout=5, check=False
            )
            if result.returncode == 0:
                print("✓ SSH port (22) is open on VM")
            else:
                print("✗ SSH port (22) is not accessible")
        except subprocess.TimeoutExpired:
            print("✗ SSH connection test timed out")
        except FileNotFoundError:
            print("✗ nc (netcat) command not found")

        return True

    finally:
        conn.close()


async def list_running_domains():
    """List all running domains"""
    print("Listing running domains...")

    conn = libvirt.open(HYPERVISOR_URL)
    if not conn:
        print(f"Failed to connect to {HYPERVISOR_URL}")
        return []

    try:
        domain_ids = conn.listDomainsID()
        domains = []

        for domain_id in domain_ids:
            domain = conn.lookupByID(domain_id)
            ip_address = await get_domain_ip_address(conn, domain.name())
            domains.append({"name": domain.name(), "id": domain_id, "ip": ip_address})
            print(f"  Domain: {domain.name()} (ID: {domain_id}, IP: {ip_address or 'Unknown'})")

        return domains

    finally:
        conn.close()


async def main():
    """Main function"""
    print("VM Connectivity Test Tool")
    print("=" * 40)

    # List running domains
    domains = await list_running_domains()

    if not domains:
        print("No running domains found.")
        return

    # Test connectivity for each domain
    print("\nTesting connectivity...")
    print("-" * 40)

    for domain in domains:
        if domain["name"].startswith("wso-"):
            await test_vm_connectivity(domain["name"])
            print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
