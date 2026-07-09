from __future__ import annotations

from datetime import datetime


def ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_cli_error(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def normalize_address(address: str) -> str:
    return address.upper()
