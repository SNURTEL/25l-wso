import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

HYPERVISOR_URL = os.getenv("HYPERVISOR_URL", "qemu:///system")
IMAGE_PATH = Path(os.getenv("IMAGE_PATH", ""))
assert IMAGE_PATH.is_file(), f"IMAGE_PATH {IMAGE_PATH} does not exist or is not a file."
QEMU_BINARY_PATH = Path(os.getenv("QEMU_BINARY_PATH", "/usr/bin/qemu-system-x86_64"))
assert QEMU_BINARY_PATH.is_file(), f"QEMU_BINARY_PATH {QEMU_BINARY_PATH} does not exist or is not a file."
PHYSICAL_IFACE_NAME = os.getenv("PHYSICAL_IFACE_NAME", "wlp3s0")
WORKDIR = Path(os.getenv("WORKDIR", "/tmp/wso-scaler"))
WORKDIR.mkdir(parents=True, exist_ok=True)

HEALTHCHECK_START_DELAY = int(os.getenv("HEALTHCHECK_START_DELAY", "1800"))
HEALTHCHECK_INTERVAL = int(os.getenv("HEALTHCHECK_INTERVAL", "5"))
HEALTHCHECK_HEALTHY_THRESHOLD = int(os.getenv("HEALTHCHECK_HEALTHY_THRESHOLD", "3"))
HEALTHCHECK_UNHEALTHY_THRESHOLD = int(os.getenv("HEALTHCHECK_UNHEALTHY_THRESHOLD", "3"))
