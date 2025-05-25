#!/usr/bin/env python3
"""
Test static IP generation and create instructions for manual VM network configuration.
"""

import sys

sys.path.insert(0, "/home/tomek/wso")

from wso.management import generate_static_ip


def test_static_ip_generation():
    """Test static IP generation for various domain names"""
    test_domains = ["wso-12345678", "wso-abcdefgh", "wso-3332a2b4", "wso-test123", "wso-vm001"]

    print("Static IP Generation Test")
    print("=" * 40)
    print("Network: 192.168.100.0/24")
    print("Gateway: 192.168.100.1")
    print()

    ips_used = set()

    for domain_name in test_domains:
        static_ip = generate_static_ip(domain_name, subnet="192.168.100")

        # Check for IP collisions
        collision = static_ip in ips_used
        ips_used.add(static_ip)

        status = "✓" if not collision else "⚠"
        print(f"{status} Domain: {domain_name}")
        print(f"   Static IP: {static_ip}")
        if collision:
            print("   WARNING: IP collision detected!")
        print()

    print("Manual Network Configuration Instructions:")
    print("-" * 50)
    print("If VM doesn't automatically configure networking, run these commands inside the VM:")
    print()

    example_domain = test_domains[0]
    example_ip = generate_static_ip(example_domain, subnet="192.168.100")

    print(f"# For domain {example_domain} with IP {example_ip}:")
    print(f"ip addr add {example_ip}/24 dev eth0")
    print("ip link set eth0 up")
    print("ip route add default via 192.168.100.1")
    print("echo 'nameserver 8.8.8.8' > /etc/resolv.conf")
    print("echo 'nameserver 8.8.4.4' >> /etc/resolv.conf")
    print()
    print("# Test connectivity:")
    print("ping 192.168.100.1  # Test gateway")
    print("ping 8.8.8.8        # Test internet")
    print()

    print("Network Configuration Files:")
    print("-" * 30)
    print("The system generates network configuration scripts at:")
    print("/tmp/wso-{domain_name}-netconfig.sh")
    print()
    print("You can copy this script into the VM and run it to configure networking.")


if __name__ == "__main__":
    test_static_ip_generation()
