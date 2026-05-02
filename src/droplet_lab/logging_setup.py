"""Loguru configuration for droplet_lab.

Two sinks:

* **Console** at INFO+, colored, terse format.
* **File** ``<experiment_dir>/experiment.log`` at DEBUG+, full format with
  source location and UTC timestamps. ``enqueue=True`` makes it safe to write
  from multiple threads.

Each thread should bind a ``component`` extra::

    logger.bind(component="pump").info("set speed to 200")
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
    "<cyan>{extra[component]: <12}</cyan> | {message}"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS!UTC} | {level: <8} | "
    "{extra[component]: <12} | {name}:{function}:{line} | {message}"
)


def setup_logging(experiment_dir: Path, *, level: str = "INFO") -> Path:
    """Configure loguru sinks. Returns the path to the file sink."""
    logger.remove()
    logger.configure(extra={"component": "main"})

    logger.add(
        sys.stderr,
        level=level,
        format=_CONSOLE_FORMAT,
        backtrace=False,
        diagnose=False,
    )

    log_file = experiment_dir / "experiment.log"
    logger.add(
        log_file,
        level="DEBUG",
        format=_FILE_FORMAT,
        enqueue=True,
        backtrace=True,
        diagnose=False,
        rotation=None,
    )
    return log_file
