#!/usr/bin/env python3
"""
Manual networking test - launches a VM and provides instructions for manual network configuration testing.
This test will launch a VM and wait for user input to verify networking works inside the VM.
"""

import asyncio
import sys
import time

# Add the wso module to Python path
sys.path.insert(0, "/home/tomek/wso")

from wso.config import ISO_PATH, WORKDIR
from wso.management import generate_static_ip
from wso.server import Server


async def test_manual_networking():
    """Launch a VM and provide manual testing instructions"""
    print("🔧 Manual Networking Test")
    print("=" * 50)

    # Initialize server
    server = Server(workdir=WORKDIR, hypervisor_url="qemu:///system")
    test_domain = f"wso-manual{int(time.time()) % 1000}"
    static_ip = generate_static_ip(test_domain)

    print(f"1. Launching VM: {test_domain}")
    print(f"   📍 Assigned Static IP: {static_ip}")
    print(f"   📀 ISO: {ISO_PATH}")
    print()

    try:
        # Launch the VM
        domain_state = await server.launch_domain(
            domain_name=test_domain,
            n_cpus=1,
            memory_kib=512 * 1024,  # 512 MB
            iso_path=ISO_PATH,
        )

        print("✅ VM launched successfully!")
        print("📊 VM Details:")
        for key, value in domain_state.items():
            print(f"   {key}: {value}")
        print()

        print("🖥️  MANUAL TESTING STEPS:")
        print("=" * 50)
        print("1. Connect to the VM console:")
        print(f"   virt-viewer -c qemu:///system {test_domain}")
        print("   OR")
        print(f"   virsh -c qemu:///system console {test_domain}")
        print()

        print("2. Boot Alpine Linux from the ISO")
        print("   - Wait for the boot process to complete")
        print("   - Login as 'root' (no password required)")
        print()

        print("3. Configure networking manually:")
        print(f"   ip addr add {static_ip}/24 dev eth0")
        print("   ip link set eth0 up")
        print("   ip route add default via 192.168.100.1")
        print("   echo 'nameserver 8.8.8.8' > /etc/resolv.conf")
        print("   echo 'nameserver 8.8.4.4' >> /etc/resolv.conf")
        print()

        print("4. Test connectivity inside the VM:")
        print("   ping 192.168.100.1      # Test gateway (should work)")
        print("   ping 8.8.8.8            # Test internet (should work)")
        print("   nslookup google.com      # Test DNS (should work)")
        print()

        print("5. Test connectivity from host:")
        print("   # Open a new terminal on your host and run:")
        print(f"   ping {static_ip}         # Should work once VM is configured")
        print()

        print("🔍 Expected Results:")
        print("✅ Gateway ping (192.168.100.1) should work immediately")
        print("✅ Internet ping (8.8.8.8) should work (proves NAT is working)")
        print("✅ DNS resolution should work")
        print("✅ Host can ping VM at its static IP")
        print()

        # Wait for user to complete manual testing
        input("⏸️  Press ENTER when you have completed the manual testing...")

        print()
        print("📝 Test Results Summary:")
        success_tests = []

        # Ask user about test results
        while True:
            print("\nDid the following tests work? (y/n)")

            gateway_test = input("1. Ping gateway (192.168.100.1): ").strip().lower()
            if gateway_test in ["y", "yes"]:
                success_tests.append("Gateway connectivity")

            internet_test = input("2. Ping internet (8.8.8.8): ").strip().lower()
            if internet_test in ["y", "yes"]:
                success_tests.append("Internet connectivity via NAT")

            dns_test = input("3. DNS resolution (nslookup google.com): ").strip().lower()
            if dns_test in ["y", "yes"]:
                success_tests.append("DNS resolution")

            host_ping_test = input(f"4. Host ping to VM ({static_ip}): ").strip().lower()
            if host_ping_test in ["y", "yes"]:
                success_tests.append("Host-to-VM connectivity")

            break

        print()
        print("🎯 Test Results:")
        if success_tests:
            print("✅ Successful tests:")
            for test in success_tests:
                print(f"   - {test}")

        if len(success_tests) == 4:
            print()
            print("🎉 ALL TESTS PASSED! Your static networking implementation is working perfectly!")
            print("✅ VMs can access the internet via NAT")
            print("✅ VMs are accessible from the host")
            print("✅ Network configuration is deterministic and reliable")
        elif len(success_tests) >= 2:
            print()
            print("⚠️  PARTIAL SUCCESS - Some tests passed, but there may be configuration issues")
        else:
            print()
            print("❌ TESTS FAILED - There may be networking configuration problems")

        print()
        user_input = input("Do you want to destroy the VM now? [y/N]: ").strip().lower()

        if user_input in ["y", "yes"]:
            print("Destroying VM...")
            await server.destroy_domain(domain_state)
            print("✅ VM destroyed and cleaned up")
        else:
            print("💡 VM left running for further testing.")
            print(f"   Domain name: {test_domain}")
            print(f"   Static IP: {static_ip}")
            print(
                f"   To destroy later: virsh -c qemu:///system destroy {test_domain} && virsh -c qemu:///system undefine {test_domain}"
            )

        return len(success_tests) >= 3

    except Exception as e:
        print(f"❌ VM launch failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    try:
        success = await test_manual_networking()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
