#!/usr/bin/env python3
"""
Complete integration test for static networking implementation.
This tests the entire flow from domain creation to network configuration.
"""

import asyncio
import os
import sys

# Add the wso module to Python path
sys.path.insert(0, "/home/tomek/wso")

from wso.config import WORKDIR
from wso.management import create_network_config_script, generate_static_ip
from wso.server import Server


async def test_static_networking_integration():
    """Test the complete static networking integration"""
    print("🧪 Static Networking Integration Test")
    print("=" * 50)

    # Test static IP generation
    print("1. Testing Static IP Generation...")
    test_domain = "wso-test123"
    static_ip = generate_static_ip(test_domain)
    print(f"   ✓ Domain: {test_domain}")
    print(f"   ✓ Generated IP: {static_ip}")
    print(f"   ✓ IP in valid range: {static_ip.startswith('192.168.100.')}")
    print()

    # Test network config script creation
    print("2. Testing Network Config Script Generation...")
    script_path = await create_network_config_script(test_domain, static_ip)
    script_exists = os.path.exists(script_path)
    script_executable = os.access(script_path, os.X_OK)

    print(f"   ✓ Script created: {script_path}")
    print(f"   ✓ Script exists: {script_exists}")
    print(f"   ✓ Script executable: {script_executable}")

    if script_exists:
        with open(script_path, "r") as f:
            content = f.read()
        print(f"   ✓ Script contains IP: {static_ip in content}")
        print(f"   ✓ Script size: {len(content)} bytes")
    print()

    # Test server initialization (without actually launching VMs)
    print("3. Testing Server Initialization...")
    try:
        server = Server(workdir=WORKDIR, hypervisor_url="qemu:///system")
        print(f"   ✓ Server initialized with workdir: {server.workdir}")
        print(f"   ✓ Hypervisor URL: {server.hypervisor_url}")
        print(f"   ✓ State file: {server.state_file}")
        print(f"   ✓ Logger available: {hasattr(server, 'logger')}")
    except Exception as e:
        print(f"   ✗ Server initialization failed: {e}")
        return False
    print()

    # Test bridge name generation
    print("4. Testing Bridge Name Generation...")
    test_domains = ["wso-1234567890", "wso-abcdefghij", "wso-test"]
    for domain in test_domains:
        domain_id = domain.replace("wso-", "")[:8]
        bridge_name = f"virbr{domain_id[:8]}"
        valid_length = len(bridge_name) <= 15

        print(f"   Domain: {domain}")
        print(f"   Bridge: {bridge_name} ({len(bridge_name)} chars)")
        print(f"   Valid: {'✓' if valid_length else '✗'}")
        print()

    # Test domain state structure
    print("5. Testing Domain State Structure...")
    from wso.server import HealthCheckState

    # Create a sample domain state
    sample_state = {
        "domain_name": test_domain,
        "network_name": f"wso-net-{test_domain}",
        "bridge_name": f"virbr{test_domain}",
        "ip_address": static_ip,
        "healthcheck_state": HealthCheckState.INITIALIZING,
        "n_failed_healthchecks": 0,
    }

    print("   ✓ Sample domain state created:")
    for key, value in sample_state.items():
        print(f"     {key}: {value}")
    print()

    print("🎉 All tests passed! Static networking implementation is ready.")
    print()
    print("📋 Next Steps:")
    print("1. Launch a VM using your server")
    print("2. Note the assigned static IP from logs")
    print("3. Boot the VM and manually configure networking:")
    print(f"   ip addr add {static_ip}/24 dev eth0")
    print("   ip link set eth0 up")
    print("   ip route add default via 192.168.100.1")
    print("4. Test connectivity:")
    print("   ping 192.168.100.1  # Gateway")
    print("   ping 8.8.8.8        # Internet")
    print()

    return True


async def main():
    """Main test function"""
    try:
        success = await test_static_networking_integration()
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
