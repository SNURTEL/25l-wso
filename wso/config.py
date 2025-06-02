import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

HYPERVISOR_URL = os.getenv("HYPERVISOR_URL", "qemu:///system")
ISO_PATH = Path(os.getenv("ISO_PATH", ""))
assert ISO_PATH.is_file(), f"ISO_PATH {ISO_PATH} does not exist or is not a file."
QEMU_BINARY_PATH = Path(os.getenv("QEMU_BINARY_PATH", "/usr/bin/qemu-system-x86_64"))
assert QEMU_BINARY_PATH.is_file(), f"QEMU_BINARY_PATH {QEMU_BINARY_PATH} does not exist or is not a file."
PHYSICAL_IFACE_NAME = os.getenv("PHYSICAL_IFACE_NAME", "eth0")
WORKDIR = Path(os.getenv("WORKDIR", "/tmp/wso-scaler"))
WORKDIR.mkdir(parents=True, exist_ok=True)
VM_SETUP_SCRIPT_PATH = os.getenv("VM_SETUP_SCRIPT_PATH", "NOTSET")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", None)

HEALTHCHECK_PORT = int(os.getenv("HEALTHCHECK_PORT", "5000"))
HEALTHCHECK_START_DELAY = int(os.getenv("HEALTHCHECK_START_DELAY", "600"))
HEALTHCHECK_INTERVAL = int(os.getenv("HEALTHCHECK_INTERVAL", "5"))
HEALTHCHECK_HEALTHY_THRESHOLD = int(os.getenv("HEALTHCHECK_HEALTHY_THRESHOLD", "3"))
HEALTHCHECK_UNHEALTHY_THRESHOLD = int(os.getenv("HEALTHCHECK_UNHEALTHY_THRESHOLD", "3"))

CONFIGURATION_INITIAL_DELAY = int(os.getenv("CONFIGURATION_INITIAL_DELAY", "20"))
CONFIGURATION_RETRY_INTERVAL = int(os.getenv("CONFIGURATION_RETRY_INTERVAL", "5"))
CONFIGURATION_RETRIES = int(os.getenv("CONFIGURATION_RETRIES", "5"))

SCALE_COOLDOWN = int(os.getenv("SCALE_COOLDOWN", "300"))
MIN_VMS = int(os.getenv("MIN_VMS", "1"))
MAX_VMS = int(os.getenv("MAX_VMS", "100"))
UP_THRESHOLD = float(os.getenv("UP_THRESHOLD", "0.5"))
DOWN_THRESHOLD = float(os.getenv("DOWN_THRESHOLD", "0.5"))
CPU_LOAD_CHECK = int(os.getenv("CPU_LOAD_CHECK", "10"))
CPU_CHECK_WINDOWSIZE = int(os.getenv("CPU_CHECK_WINDOWSIZE", "10"))

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "9124"))
