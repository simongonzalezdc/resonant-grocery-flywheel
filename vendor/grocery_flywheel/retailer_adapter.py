from __future__ import annotations

from typing import Any


CORE_CAPABILITIES = [
    "purchase_history",
    "product_search",
    "price_lookup",
    "unit_price",
    "availability",
    "substitutions",
    "cart_draft",
    "order_submit",
]


CAPABILITY_WEIGHTS = {
    "purchase_history": 5,
    "product_search": 3,
    "price_lookup": 3,
    "unit_price": 2,
    "availability": 2,
    "substitutions": 2,
    "cart_draft": 1,
    "order_submit": -10,
}


def validate_retailer_profile(profile: dict[str, Any]) -> list[str]:
    """Return validation errors for a retailer adapter profile."""
    errors: list[str] = []
    required = ["id", "name", "type", "channels", "acquisition_methods", "capabilities"]
    for field in required:
        if field not in profile:
            errors.append(f"missing {field}")

    capabilities = profile.get("capabilities", {})
    if not isinstance(capabilities, dict):
        errors.append("capabilities must be an object")
        return errors

    for capability in CORE_CAPABILITIES:
        if capability not in capabilities:
            errors.append(f"missing capability {capability}")

    if capabilities.get("order_submit"):
        errors.append("order_submit must stay false for MVP adapter profiles")

    if (
        "retailer_history_import" in profile.get("acquisition_methods", [])
        and not capabilities.get("purchase_history")
    ):
        errors.append("retailer_history_import requires purchase_history capability")

    return errors


def adapter_score(profile: dict[str, Any]) -> int:
    capabilities = profile.get("capabilities", {})
    return sum(
        weight
        for capability, weight in CAPABILITY_WEIGHTS.items()
        if capabilities.get(capability)
    )


def capability_matrix(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for profile in profiles:
        capabilities = profile.get("capabilities", {})
        rows.append(
            {
                "id": profile.get("id", ""),
                "name": profile.get("name", ""),
                "type": profile.get("type", ""),
                "score": adapter_score(profile),
                "acquisition_methods": profile.get("acquisition_methods", []),
                "enabled_capabilities": [
                    capability
                    for capability in CORE_CAPABILITIES
                    if capabilities.get(capability)
                ],
                "errors": validate_retailer_profile(profile),
            }
        )
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def best_import_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank profiles for first-run setup."""
    eligible = [
        profile
        for profile in profiles
        if profile.get("capabilities", {}).get("purchase_history")
    ]
    return sorted(eligible, key=adapter_score, reverse=True)

