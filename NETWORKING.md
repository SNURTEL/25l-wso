# VM Networking Configuration

## Overview

The `launch_domain` method has been updated to create QEMU/KVM virtual machines with proper NAT networking that provides:

1. **Outbound Internet Access**: VMs can access the internet through NAT
2. **Host Accessibility**: VMs are accessible from the host machine via local IP addresses
3. **Isolation**: Each VM gets its own network configuration

## Network Architecture

### NAT Network Setup
- **Network Type**: NAT (Network Address Translation)
- **IP Range**: 192.168.100.0/24
- **Gateway**: 192.168.100.1 (provided by libvirt)
- **IP Assignment**: Static IPs generated deterministically from domain name
- **DNS**: 8.8.8.8, 8.8.4.4 (configured manually in VM)

### Static IP Assignment
- Each VM gets a unique static IP based on its domain name hash
- IP range: 192.168.100.2 - 192.168.100.254
- Example: Domain "wso-3332a2" gets IP "192.168.100.229"
- No DHCP server required

### Bridge Configuration
- Each VM gets its own libvirt network with a unique name: `wso-net-{domain_id}`
- Bridge interface is automatically created: `virbr{domain_id}` (max 13 chars to stay within 15 char limit)
- Bridge provides NAT forwarding and DHCP services
- Domain ID is extracted from the domain name (e.g., "wso-3332a2" → "3332a2")

## Key Features

### 1. Internet Access
VMs can access the internet through NAT:
```bash
# Inside the VM (once booted)
ping google.com
curl http://example.com
```

### 2. Host-to-VM Connectivity
Host can connect to VMs using their assigned IP addresses:
```bash
# From the host
ping 192.168.100.X  # Where X is the VM's assigned IP
ssh user@192.168.100.X  # If SSH is configured in the VM
```

### 3. VM Disk Management
- VMs get persistent storage via qcow2 disk images
- Disk images are stored in `/tmp/wso-{domain_name}-disk.qcow2`
- Default disk size: 10GB (configurable)

## Usage Example

```python
from wso.server import Server
from wso.config import ISO_PATH

# Create server instance
server = Server(workdir=Path("/tmp/wso"), hypervisor_url="qemu:///system")

# Launch a VM with NAT networking
domain_state = await server.launch_domain(
    domain_name="test-vm",
    n_cpus=2,
    memory_kib=2097152,  # 2GB RAM
    iso_path=ISO_PATH
)

print(f"VM IP: {domain_state['ip_address']}")
print(f"Network: {domain_state['network_name']}")
```

## Testing Connectivity

Use the provided test script to verify networking:

```bash
python test_vm_connectivity.py
```

This script will:
1. List all running WSO domains
2. Show their IP addresses
3. Test ping connectivity
4. Test SSH port accessibility

## Network Configuration Details

### VM XML Configuration
The VMs are configured with:
- **Interface Type**: `network` (connects to libvirt network)
- **Model**: `virtio` (high-performance networking)
- **Network Source**: Auto-created NAT network

### Libvirt Network XML
Each network is configured with:
- **Forward Mode**: `nat` with port range 1024-65535
- **Bridge**: Auto-created with STP enabled
- **IP Configuration**: Static gateway with DHCP pool
- **DNS**: Automatic DNS forwarding

## Troubleshooting

### VM Not Getting IP Address
1. Check if libvirt DHCP is running: `sudo systemctl status libvirtd`
2. Verify network is active: `virsh net-list --all`
3. Check VM's network interface inside the VM

### Cannot Ping VM from Host
1. Verify VM has an IP: Check domain state or use `test_vm_connectivity.py`
2. Check firewall rules on host
3. Ensure VM's network interface is up

### No Internet Access from VM
1. Check NAT is enabled: `virsh net-dumpxml {network_name}`
2. Verify host's internet connectivity
3. Check VM's DNS configuration

## Manual Network Configuration

If the VM doesn't automatically configure networking, you can manually set it up inside the VM:

### For Alpine Linux VMs:
```bash
# Configure network interface (replace with your VM's assigned IP)
ip addr add 192.168.100.229/24 dev eth0
ip link set eth0 up
ip route add default via 192.168.100.1

# Configure DNS
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf

# Test connectivity
ping 192.168.100.1  # Test gateway
ping 8.8.8.8        # Test internet
```

### Make Configuration Persistent:
```bash
# Create persistent network configuration
cat > /etc/network/interfaces << EOF
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.100.229
    netmask 255.255.255.0
    gateway 192.168.100.1
EOF
```

The system automatically generates a network configuration script for each VM at:
`/tmp/wso-{domain_name}-netconfig.sh`

You can copy this script into the VM and execute it to configure networking automatically.

## Security Considerations

- VMs are isolated from each other by default
- Only the host can directly access VMs (no external access)
- NAT provides outbound connectivity only
- For external access, additional port forwarding would be needed
