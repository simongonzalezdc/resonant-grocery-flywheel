from __future__ import annotations

import re
from typing import Any

from .model.contract import OrderItem, ProductEvidence, ProductIdentity, to_dict


SIZE_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>fl\s*oz|fluid\s*ounce|oz|ounce|lb|pound|ct|count|pack|pk)\b",
    re.IGNORECASE,
)

UNIT_ALIASES = {
    "oz": "oz",
    "ounce": "oz",
    "fl oz": "fl_oz",
    "fluid ounce": "fl_oz",
    "lb": "lb",
    "pound": "lb",
    "ct": "ct",
    "count": "ct",
    "pack": "ct",
    "pk": "ct",
}


def canonical_name(value: str) -> str:
    return " ".join(value.lower().strip().split())


def parse_size(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {"raw": "", "amount": None, "unit": None, "confidence": "low"}
    text = str(raw)
    matches = list(SIZE_RE.finditer(text))
    if not matches:
        return {"raw": text, "amount": None, "unit": None, "confidence": "low"}

    total = 1.0
    if "x" in text.lower():
        multiplier_match = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", text, re.I)
        if multiplier_match:
            total = float(multiplier_match.group(1))

    match = matches[-1]
    amount = float(match.group("amount")) * total
    unit_raw = " ".join(match.group("unit").lower().split())
    return {
        "raw": text,
        "amount": amount,
        "unit": UNIT_ALIASES.get(unit_raw, unit_raw),
        "confidence": "high",
    }


def compute_unit_price(spend: float, size: dict[str, Any], quantity: float = 1) -> float | None:
    amount = size.get("amount")
    if not amount:
        return None
    return round(float(spend) / (float(amount) * float(quantity or 1)), 4)


def normalize_evidence(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    evidence = []
    for row in rows or []:
        if row.get("source") and row.get("checked_date") and row.get("evidence_type"):
            evidence.append(
                to_dict(
                    ProductEvidence(
                        evidence_type=str(row["evidence_type"]),
                        source=str(row["source"]),
                        checked_date=str(row["checked_date"]),
                        ingredients=list(row.get("ingredients", [])),
                        allergen_statements=list(row.get("allergen_statements", [])),
                        certifications=list(row.get("certifications", [])),
                        nutrition_facts=dict(row.get("nutrition_facts", {})),
                    )
                )
            )
    return evidence


def normalize_item(row: dict[str, Any], *, source: str) -> dict[str, Any]:
    def _value(key: str) -> Any:
        # Hand-edited exports often carry "" for "not set"; treat it as
        # absent instead of letting float("") crash with a confusing error.
        value = row.get(key)
        return None if value == "" else value

    quantity = float(_value("quantity") or 1)
    spend = _value("spend") if _value("spend") is not None else _value("total_price")
    if spend is None:
        unit_price = float(_value("unit_price") or 0)
        spend = unit_price * quantity
    spend = round(float(spend), 2)
    size = parse_size(_value("size") or _value("size_raw"))
    unit_price = _value("unit_price")
    if unit_price is None:
        unit_price = compute_unit_price(spend, size, quantity)
    confidence = "high" if size.get("confidence") == "high" else "low"
    identity = ProductIdentity(
        name=str(row["name"]),
        canonical_name=canonical_name(str(row["name"])),
        category=str(row.get("category", "unknown")),
        size=size,
        confidence=confidence,
    )
    item = to_dict(
        OrderItem(
            name=str(row["name"]),
            spend=spend,
            quantity=quantity,
            category=str(row.get("category", "unknown")),
            role=str(row.get("role", infer_role(row))),
            size=size,
            unit_price=round(float(unit_price), 4) if unit_price is not None else None,
            confidence=confidence,
            source_provenance={
                "source": source,
                "source_row_id": row.get("source_row_id") or row.get("id"),
                "raw_size": row.get("size") or row.get("size_raw", ""),
            },
            product_evidence=normalize_evidence(row.get("product_evidence")),
            pricing_status=_value("pricing_status"),
            last_price_check=_value("last_price_check"),
            added_on=_value("added_on"),
        )
    ) | {"product_identity": to_dict(identity), "notes": row.get("notes", "")}

    # added_on is a presence signal (absence = baseline). asdict() writes
    # nulls for unset dataclass fields, so strip the freshness keys when
    # they were not actually present in the source row.
    for field_name in ("added_on", "last_price_check", "pricing_status"):
        if item.get(field_name) is None:
            item.pop(field_name, None)

    # Depletion and household context travel with the item: an import that
    # knows how much is left should not silently forget it.
    for field_name in (
        "remaining_fraction", "units_total", "units_remaining", "consumed_fraction",
        "storage", "recurring",
    ):
        value = _value(field_name)
        if value is not None:
            item[field_name] = value
    return item


def infer_role(row: dict[str, Any]) -> str:
    category = str(row.get("category", "")).lower()
    name = str(row.get("name", "")).lower()
    if any(token in category or token in name for token in ["coffee", "tea"]):
        return "coffee"
    if any(token in category or token in name for token in ["cleaning", "soap", "detergent"]):
        return "critical_household_essential"
    if any(token in category for token in ["dry_good", "pantry", "rice", "beans"]):
        return "pantry_base"
    if any(token in category or token in name for token in ["frozen", "burrito", "waffle"]):
        return "bridge_food"
    return "general_household"
