"""Shared schemas and response helpers for WallWin Gem V3."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

API_VERSION = "3.0.0-phase1"

STATUS_OK = "OK"
STATUS_DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
STATUS_VALIDATION_ERROR = "VALIDATION_ERROR"
STATUS_DATA_SOURCE_ERROR = "DATA_SOURCE_ERROR"
STATUS_DATA_SOURCE_RATE_LIMIT = "DATA_SOURCE_RATE_LIMIT"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_INSUFFICIENT = "insufficient"

SOURCE_RULE_ENGINE = "wallwin.rule_engine"
SOURCE_SYNTHETIC_OR_USER = "input.ohlcv"
SOURCE_HITL = "input.hitl"
SOURCE_YFINANCE = "yfinance"


@dataclass
class ApiError:
    code: str
    message: str
    field: str | None = None


@dataclass
class ApiMeta:
    status: str = STATUS_OK
    confidence: str = CONFIDENCE_MEDIUM
    source_tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[ApiError] = field(default_factory=list)
    insufficient_data: list[str] = field(default_factory=list)


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy/datetime values into JSON-safe Python objects."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if pd.isna(value) if not isinstance(value, (list, tuple, dict)) else False:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def meta_dict(meta: ApiMeta) -> dict[str, Any]:
    payload = asdict(meta)
    payload["errors"] = [asdict(err) if isinstance(err, ApiError) else err for err in meta.errors]
    return json_safe(payload)


def api_response(
    endpoint: str,
    result: dict[str, Any] | None,
    meta: ApiMeta,
    input_echo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return json_safe(
        {
            "api_version": API_VERSION,
            "endpoint": endpoint,
            "status": meta.status,
            "meta": meta_dict(meta),
            "input_echo": input_echo or {},
            "result": result or {},
        }
    )
