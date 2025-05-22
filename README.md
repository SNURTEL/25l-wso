# 25l-wso

## Prerequisites

- A KVM-capable host:

```shell
sudo apt update && sudo apt install -y cpu-checker && kvm-ok
ls /dev | grep kvm
```

- `libvirt` and `pkg-config` packages
- `NetworkManager` and `nmcli`

- Access to libvirt, kvm and `nmcli`. When running as a regular user:

```shell
sudo usermod -aG kvm $USER
sudo usermod -aG libvirt $USER
sudo touch /etc/sudoers.d/nmcli-nopasswd
echo "$USER ALL = (root) NOPASSWD: $(which nmcli)" | sudo EDITOR='tee -a' visudo /etc/sudoers.d/nmcli-nopasswd
# reload permissions
exec $SHELL -l
```

## Install

```shell
pdm install
```

## Development

```shell
pre-commit install
```

https://libvirt-python.readthedocs.io/
