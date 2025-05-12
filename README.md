# 25l-wso

## Install

First, ensure your host is KVM-capable:

```shell
sudo apt update && sudo apt install -y cpu-checker && kvm-ok
ls /dev | grep kvm
```

Install the project. Note: ensure you have `libvirt` and `pkg-config` installed. On a Debian-based distro:

```shell
sudo apt update && sudo apt install -y libvirt-dev pkg-config
```

```shell
pdm install
```

## Development

```shell
pre-commit install
```

https://libvirt-python.readthedocs.io/
