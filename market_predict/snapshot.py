"""Serialize/deserialize TickerView to/from JSON.

Used by the GitHub Actions cron pipeline: the Action runs `build_view` for
each ticker, writes `data/snapshot_<symbol>.json`, the Streamlit app reads
those JSONs instead of hitting 18 live APIs.

Design choice: decoded objects are `SimpleNamespace`, not the original
dataclasses. Chart code only uses attribute access (`view.spot`, `b.yes_mid`),
never isinstance checks — confirmed by grep before this module was written.
That sidesteps the need to import every dataclass back at decode time.
"""
from __future__ import annotations
import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd


def _encode(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return {"__type__": "datetime", "value": obj.isoformat()}
    if isinstance(obj, date):
        return {"__type__": "date", "value": obj.isoformat()}
    if isinstance(obj, pd.Timestamp):
        return {"__type__": "datetime", "value": obj.to_pydatetime().isoformat()}
    if isinstance(obj, pd.DataFrame):
        df = obj.copy()
        index_name = df.index.name or ("_index" if isinstance(df.index, pd.DatetimeIndex) else None)
        if index_name:
            df = df.reset_index()
            if df.columns[0] in ("index", "_index"):
                df = df.rename(columns={df.columns[0]: index_name})
        # Stringify all datetime cells so JSON can hold them
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].apply(lambda x: x.isoformat() if pd.notna(x) else None)
        records = df.where(pd.notnull(df), None).to_dict("records")
        return {
            "__type__": "dataframe",
            "records": records,
            "columns": df.columns.tolist(),
            "index_name": index_name,
        }
    if is_dataclass(obj):
        return {f.name: _encode(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_encode(v) for v in obj]
    # Unknown type — coerce to str so JSON encoder doesn't die mid-write
    return str(obj)


def _decode(obj: Any) -> Any:
    if isinstance(obj, dict):
        t = obj.get("__type__")
        if t == "date":
            return date.fromisoformat(obj["value"])
        if t == "datetime":
            return datetime.fromisoformat(obj["value"])
        if t == "dataframe":
            df = pd.DataFrame(obj["records"])
            # Restore declared column order even if some columns are all-null
            cols = obj.get("columns") or list(df.columns)
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            df = df[cols]
            idx_name = obj.get("index_name")
            if idx_name and idx_name in df.columns:
                df[idx_name] = pd.to_datetime(df[idx_name], errors="coerce")
                df = df.set_index(idx_name)
            return df
        return SimpleNamespace(**{k: _decode(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_decode(v) for v in obj]
    return obj


def save_snapshot(view, path: Path) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "view": _encode(view),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), default=str))


def load_snapshot(path: Path):
    """Return a view-like SimpleNamespace (with .timestamp + ._snapshot_meta),
    or None if the file is missing/corrupt/wrong schema."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return _materialize(raw)


def load_snapshot_from_text(text: str):
    """Parse a JSON string (e.g. from raw.githubusercontent.com) into a view."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None
    return _materialize(raw)


def _materialize(raw: dict):
    if raw.get("schema_version") != 1:
        return None
    view = _decode(raw["view"])
    view._snapshot_generated_at = raw.get("generated_at")
    return view
