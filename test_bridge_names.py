#!/usr/bin/env python3
"""
Test bridge name generation to ensure it meets Linux interface name limits.
"""


def test_bridge_name_generation():
    """Test that bridge names are within the 15 character limit"""
    test_cases = ["wso-12345678", "wso-abcdefgh", "wso-3332a2b4", "very-long-domain-name-that-exceeds-normal-limits"]

    print("Testing bridge name generation:")
    print("=" * 50)

    for domain_name in test_cases:
        # Simulate the new logic from server.py
        domain_id = domain_name.replace("wso-", "")[:8]
        network_name = f"wso-net-{domain_id}"
        bridge_name = f"virbr{domain_id[:8]}"

        print(f"Domain name: {domain_name}")
        print(f"  Network name: {network_name} (length: {len(network_name)})")
        print(f"  Bridge name: {bridge_name} (length: {len(bridge_name)})")

        if len(bridge_name) <= 15:
            print("  ✓ Bridge name is within 15 character limit")
        else:
            print("  ✗ Bridge name exceeds 15 character limit!")
        print()


if __name__ == "__main__":
    test_bridge_name_generation()
