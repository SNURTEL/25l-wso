#!/usr/bin/env python3
"""
Test script to launch a VM with static networking and verify the implementation.
"""

import asyncio
import sys
import time

# Add the wso module to Python path
sys.path.insert(0, "/home/tomek/wso")

from wso.config import ISO_PATH, WORKDIR
from wso.management import generate_static_ip
from wso.server import Server


async def test_vm_launch():
    """Test launching a VM with static networking"""
    print("🚀 VM Launch Test with Static Networking")
    print("=" * 50)

    # Initialize server
    print("1. Initializing server...")
    server = Server(workdir=WORKDIR, hypervisor_url="qemu:///system")
    print("   ✓ Server initialized")
    print(f"   ✓ Workdir: {server.workdir}")
    print()

    # Test domain name and parameters
    test_domain = f"wso-test{int(time.time()) % 1000}"  # Unique name
    print(f"2. Preparing to launch VM: {test_domain}")

    # Show what static IP will be assigned
    static_ip = generate_static_ip(test_domain)
    print(f"   ✓ Static IP: {static_ip}")

    # Generate bridge name to verify it's valid
    domain_id = test_domain.replace("wso-", "")[:8]
    bridge_name = f"virbr{domain_id[:8]}"
    print(f"   ✓ Bridge name: {bridge_name} ({len(bridge_name)} chars)")
    print(f"   ✓ Bridge name valid: {len(bridge_name) <= 15}")
    print()

    # Launch the VM
    print("3. Launching VM...")
    print(f"   📀 ISO Path: {ISO_PATH}")
    print("   💾 Memory: 512 MB")
    print("   🔧 CPUs: 1")
    print()

    try:
        domain_state = await server.launch_domain(
            domain_name=test_domain,
            n_cpus=1,
            memory_kib=512 * 1024,  # 512 MB
            iso_path=ISO_PATH,
        )

        print("   ✅ VM launched successfully!")
        print("   📊 Domain State:")
        for key, value in domain_state.items():
            print(f"     {key}: {value}")
        print()

        print("🎉 VM Launch Success!")
        print()
        print("📋 Manual Network Configuration Steps:")
        print("1. Connect to the VM console (VNC or serial)")
        print("2. Boot Alpine Linux")
        print("3. Login as root (no password)")
        print("4. Run these commands to configure networking:")
        print()
        print(f"   ip addr add {static_ip}/24 dev eth0")
        print("   ip link set eth0 up")
        print("   ip route add default via 192.168.100.1")
        print("   echo 'nameserver 8.8.8.8' > /etc/resolv.conf")
        print()
        print("5. Test connectivity:")
        print("   ping 192.168.100.1  # Gateway")
        print("   ping 8.8.8.8        # Internet")
        print()
        print("📄 Or use the generated script:")
        script_path = f"/tmp/wso-{test_domain}-netconfig.sh"
        print(f"   wget -O - http://HOST_IP/path/to/{script_path} | sh")
        print(f"   (or copy the script content from {script_path})")
        print()

        # Ask if user wants to destroy the VM
        print("⚠️  VM is still running!")
        user_input = input("Do you want to destroy the VM now? [y/N]: ").strip().lower()

        if user_input in ["y", "yes"]:
            print("Destroying VM...")
            await server.destroy_domain(domain_state)
            print("✅ VM destroyed")
        else:
            print("💡 VM left running. You can connect and test networking manually.")
            print(f"   Domain name: {test_domain}")
            print(f"   To destroy later: virsh destroy {test_domain} && virsh undefine {test_domain}")

        return True

    except Exception as e:
        print(f"   ❌ VM launch failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    print("Starting main function...")
    try:
        success = await test_vm_launch()
        print(f"test_vm_launch returned: {success}")
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
