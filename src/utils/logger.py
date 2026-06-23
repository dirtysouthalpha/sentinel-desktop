"""Logging utility for Sentinel Desktop."""
import logging
import sys
from pathlib import Path
from datetime import datetime
from src.config import LOG_DIR

def setup_logger(name="sentinel", level=logging.INFO):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # File handler
    log_file = LOG_DIR / f"sentinel_{datetime.now().strftime('%Y%m%d')}.log"
    fh = logging.FileHandler(str(log_file))
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger
