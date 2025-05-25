import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

HYPERVISOR_URL = os.getenv("HYPERVISOR_URL", "qemu:///system")
ISO_PATH = Path(os.getenv("ISO_PATH", "/home/tomek/Pobrane/alpine-standard-3.21.3-x86_64.iso"))
QEMU_BINARY_PATH = os.getenv("QEMU_BINARY_PATH", "/usr/bin/qemu-system-x86_64")
PHYSICAL_IFACE_NAME = os.getenv("PHYSICAL_IFACE_NAME", "wlp3s0")
WORKDIR = Path(os.getenv("WORKDIR", "/tmp/wso-scaler"))
WORKDIR.mkdir(parents=True, exist_ok=True)
