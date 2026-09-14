"""Offline capability discovery for the quality protocol.

Discovery deliberately uses ``find_spec`` and metadata only; optional video,
UI and training packages are never imported or downloaded.
"""
from __future__ import annotations

import importlib.util
import platform
import sys
from typing import Any


def _available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def collect_capabilities() -> dict[str, Any]:
    """Return a JSON-serializable, deterministic capability document."""
    dependencies = {
            "parquet": {"module": "pyarrow", "available": _available("pyarrow"), "required_for": ["input_manifest", "measurements"]},
            "pandas": {"module": "pandas", "available": _available("pandas"), "required_for": ["parquet_fallback"]},
            "video": {"module": "av", "available": _available("av"), "required_for": ["media_decode"]},
            "training": {"module": "lerobot", "available": _available("lerobot"), "required_for": ["trainer_provider"], "optional": True},
            "ui": {"module": "streamlit", "available": _available("streamlit"), "required_for": ["review_ui"], "optional": True},
        }
    units = []
    for unit_id, dep, reason in (
        ("INPUT.PARQUET", "parquet", "missing_pyarrow"),
        ("MEDIA.H264", "video", "missing_pyav"),
        ("TRAINER.PARITY", "training", "no_pinned_trainer_provider"),
    ):
        info = dependencies[dep]
        units.append({"plan_unit_id": unit_id, "available": bool(info["available"]) if dep != "training" else False,
                      "reason_code": None if info["available"] and dep != "training" else reason})
    return {
        "capability_schema": 1,
        "protocol": {"name": "rda-quality", "major": 1},
        "config_schema": 1,
        "algorithms": {
            "measurement": "rda-measurement-v1",
            "rules": "rda-rules-v1",
            "windows": "rda-window-contract-v1",
        },
        "delegated_checks": ["robovet"],
        "dependencies": dependencies,
        "quality_units": units,
        "provider": {
            "reference_window": {"available": True, "aligned": False, "reason": "no pinned production trainer configured"},
            "lerobot": {"available": _available("lerobot"), "configured": False},
        },
        "sandbox": {"available": False, "reason": "production isolation backend not configured"},
        "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation(), "platform": sys.platform},
        "offline": True,
    }
