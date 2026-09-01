from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from .normalized import import_normalized_history


def import_csv_history(path: Path, *, profile_id: str | None = None) -> dict[str, Any]:
    try:
        with path.open(newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if row.get("name") or row.get("item")]
    except csv.Error as exc:  # includes the 128KB field-size limit
        raise ValueError(f"CSV could not be parsed: {exc}") from exc
    if not rows:
        raise ValueError("CSV import has no rows")

    # One CSV, one order. A multi-order export must be split explicitly —
    # silently collapsing every order into the first row's store/date was
    # the old behavior and it corrupted provenance (QA finding).
    order_keys = sorted({
        (row.get("store") or "CSV retailer",
         row.get("order_date") or row.get("date") or date.today().isoformat())
        for row in rows
    })
    if len(order_keys) > 1:
        listed = ", ".join(f"{store}/{when}" for store, when in order_keys[:5])
        raise ValueError(
            f"CSV contains {len(order_keys)} distinct orders ({listed}); "
            "split it into one file per order and import each separately"
        )

    payload = {
        "source": "csv_export",
        "as_of": date.today().isoformat(),
        "order": {"store": order_keys[0][0], "date": order_keys[0][1]},
        "items": [
            {
                "name": row.get("name") or row.get("item") or "",
                "quantity": row.get("quantity") or 1,
                "size": row.get("size") or row.get("size_raw") or "",
                "spend": row.get("spend") or row.get("total_price") or row.get("price") or 0,
                "category": row.get("category") or "unknown",
                "role": row.get("role") or "",
                "notes": row.get("notes") or "",
                "source_row_id": row.get("id") or row.get("line_id") or "",
            }
            for row in rows
        ],
    }
    return import_normalized_history(payload, profile_id=profile_id)
