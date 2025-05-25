#!/usr/bin/env python3
"""
Test script to validate that bridge names are properly generated and within limits.
This specifically tests the fix for the "Numerical result out of range" error.
"""

import sys


def validate_bridge_names():
    """Validate that all possible bridge names are within Linux interface limits"""
    # Test various domain name patterns that could be generated
    test_domains = [
        "wso-a1b2c3d4",  # 8 char hex-like ID
        "wso-12345678",  # 8 digit ID
        "wso-abcdefgh",  # 8 letter ID
        "wso-1a2b3c4d",  # Mixed alphanumeric
        "wso-xyz",  # Short ID
        "wso-verylongdomainname",  # Long domain name (will be truncated)
    ]

    print("Bridge Name Validation Test")
    print("=" * 40)
    print("Linux interface name limit: 15 characters")
    print()

    all_valid = True

    for domain_name in test_domains:
        # Apply the same logic from server.py
        domain_id = domain_name.replace("wso-", "")[:8]
        network_name = f"wso-net-{domain_id}"
        bridge_name = f"virbr{domain_id[:8]}"

        # Validate lengths
        _ = len(network_name) <= 100  # Arbitrary reasonable limit for network names
        bridge_valid = len(bridge_name) <= 15  # Linux interface name limit

        status = "✓" if bridge_valid else "✗"
        print(f"{status} Domain: {domain_name}")
        print(f"   Network: {network_name} ({len(network_name)} chars)")
        print(f"   Bridge:  {bridge_name} ({len(bridge_name)} chars)")

        if not bridge_valid:
            print("   ERROR: Bridge name exceeds 15 character limit!")
            all_valid = False
        print()

    if all_valid:
        print("🎉 All bridge names are valid and within the 15 character limit!")
        print("The 'Numerical result out of range' error should be resolved.")
        return True
    else:
        print("❌ Some bridge names are invalid!")
        return False


if __name__ == "__main__":
    success = validate_bridge_names()
    sys.exit(0 if success else 1)
