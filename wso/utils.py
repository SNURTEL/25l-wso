import functools
import logging
import os
import sys


@functools.lru_cache()
def get_logger(level: int = logging.DEBUG, log_file: str | os.PathLike | None = None) -> logging.Logger:
    logger = logging.getLogger("wso")
    logger.setLevel(level=level)
    sh = logging.StreamHandler(sys.stdout)
    s_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh.setFormatter(s_format)
    logger.addHandler(sh)
    if log_file:
        fh = logging.FileHandler(log_file)
        f_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(f_format)
        logger.addHandler(fh)
    return logger
