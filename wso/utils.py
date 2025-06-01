import dataclasses
import functools
import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import wso.config


@functools.lru_cache()
def get_logger(level: int = logging.DEBUG, log_file: str | os.PathLike | None = None) -> logging.Logger:
    logger = logging.getLogger("wso")
    logger.setLevel(level=level)
    sh = logging.StreamHandler(sys.stdout)
    s_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh.setFormatter(s_format)
    logger.addHandler(sh)
    if log_file:
        fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=10**6, backupCount=5)
        f_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(f_format)
        logger.addHandler(fh)
    return logger


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)  # type: ignore[arg-type]
        elif isinstance(o, Path):
            return str(o.resolve().absolute())
        elif isinstance(o, datetime):
            return str(o.isoformat())
        return super().default(o)


def get_ssh_public_key() -> str:
    """
    Returns the SSH public key from the default location.
    """
    if wso.config.SSH_KEY_PATH is None:
        ssh_dir = Path.home() / ".ssh"
        for key_name in ["id_ed25519.pub", "id_rsa.pub"]:
            public_key_path = ssh_dir / key_name
            if public_key_path.is_file():
                break
        else:
            raise FileNotFoundError("No SSH public key found (tried id_ed25519.pub and id_rsa.pub)")
    else:
        public_key_path = Path(wso.config.SSH_KEY_PATH).with_suffix(".pub")
        if not public_key_path.is_file():
            raise FileNotFoundError(f"SSH public key file {public_key_path} does not exist or is not a file.")
    with open(public_key_path, "r") as f:
        return f.read().strip()
