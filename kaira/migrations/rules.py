"""Upgrade and migration rules definitions."""

from __future__ import annotations

VALID_TIERS: set[str] = {"simple", "standard", "enterprise"}

TIER_RANKS: dict[str, int] = {
    "simple": 1,
    "standard": 2,
    "enterprise": 3,
}


def is_valid_upgrade(current_tier: str, target_tier: str) -> bool:
    """Return True if target_tier is higher than current_tier."""
    c = current_tier.lower()
    t = target_tier.lower()
    if c not in TIER_RANKS or t not in TIER_RANKS:
        return False
    return TIER_RANKS[t] > TIER_RANKS[c]


def describe_upgrade(current_tier: str, target_tier: str) -> list[str]:
    """Describe actions taken when moving from current_tier to target_tier."""
    actions: list[str] = []
    if current_tier == "simple" and target_tier in ("standard", "enterprise"):
        actions.extend(
            [
                "Deconstruct combined single-file modules into standard 5 layers (models, schemas, services, repositories, routers)",
                "Update main.py to instantiate KairaApp runtime",
                "Generate docs/ architectural and API reference manuals",
                "Wire runtime 5-layer pipeline enforcement and security middleware",
                "Update .kaira.json configuration to standard tier",
            ]
        )
    if target_tier == "enterprise":
        actions.extend(
            [
                "Enable domain-grouped architecture support (app/domains/)",
                "Scaffold OpenTelemetry distributed tracing hooks",
                "Scaffold Enterprise Dependency Injection (DI) container",
                "Update .kaira.json configuration to enterprise tier",
            ]
        )
    return actions
