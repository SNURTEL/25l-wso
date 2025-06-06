# 25l-wso

## Prerequisites

- A KVM-capable host:

```shell
sudo apt update && sudo apt install -y cpu-checker && kvm-ok
ls /dev | grep kvm
```

- `libvirt`, `pkg-config` and `genisoimage` packages
- `virsh` for convenience

- Access to libvirt, and KVM **without sudo**. When running as a regular user:

```shell
sudo usermod -aG kvm $USER
sudo usermod -aG libvirt $USER
# reload permissions
exec $SHELL -l
```

## Setup

```shell
cp .env.sample .env
pdm install
```

Download [Alpine Linux ISO](https://alpinelinux.org/downloads/) and enter its path to `.env` (tested with alpine-standard-3.21.3-x86_64.iso).

Also check whether QEMU path and iface name in `.env` match you configuration and adjust if needed + enter absolute path to `scripts/vmScriptAlpine.sh` to `VM_SETUP_SCRIPT_PATH`

## Run

Run the daemon:

```shell
pdm run python3 -m wso
```

Tail logs:

```shell
tail -f /tmp/wso-scaler/server.log
```

You should have two VMs running:

```shell
virsh -c qemu:///system list
```

Get their IPs from logs, then:

```shell
curl http://<VM_IP>
```

You should get a sample HTML page with VM name and IP.

### Access services

- HAProxy stats: [`localhost:8080/haproxy_stats`](localhost:8080/haproxy_stats)
- Consul: [`localhost:8500`](localhost:8500)
- App: [`localhost`](localhost)

### Simulate fault

The daemon will try to keep a given number of VMs healthy. It will perform TCP healthckecks on VMs and recreate ones that fail. You can simulate a fault by destroying VM.

Get VM names:

```shell
virsh -c qemu:///system list
```

Destroy:

```shell
virsh destroy <VM_NAME>
```

In a few seconds you should see warnings about failing healthchecks in logs and then the VM should be destroyed and a new one should be created in place.

## Talk to the daemon

```shell
# start the daemon
pdm run python3 -m wso start

# stop the daemon
pdm run python3 -m wso stop

# scale to N VMs
pdm run python3 -m wso scale <N>

# get current state
pdm run python3 -m wso state
```

## Stop the daemon

Using pidfile

```shell
kill -TERM $(cat /tmp/wso-scaler/daemon.pid)
```

The daemon will terminate all VMs, remove volumes and the shared NAT network.


## Development

```shell
pre-commit install
```

https://libvirt-python.readthedocs.io/

## Host Haproxy Consul setup

```shell
sudo bash -x scripts/consulHaproxySetup.sh
```

## Vm repo

[Flask-service](https://github.com/skoda-octavia/flask-service)


## Locust

After running deamon execute `locust -f wso/locustfile.py` and open [localhost:8089](http://0.0.0.0:8089/) in browser. Put HaProxy address (192.168.100.xxx) in host input and number of agents.