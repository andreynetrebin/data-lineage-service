"""Единая настройка логирования сервиса."""
from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=_FORMAT,
        stream=sys.stderr,
        force=True,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
