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
