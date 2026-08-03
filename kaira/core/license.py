"""Feature-gating seam for a future licensed tier.

Nothing is gated today. This exists so the decision of *where* a paywall would
sit is made once, in code, while the answer is still cheap to change — rather
than being retrofitted across command modules later.

The call site is ``kaira export add`` (generating API endpoints), deliberately
not ``kaira export data`` (the developer's own ad hoc pulls), because that is
the split most likely to be drawn. No license validation exists in Phase 7 and
none should be added here without the corresponding product decision.
"""

from __future__ import annotations

#: Feature keys passed to :func:`is_pro_enabled`, kept in one place so a typo
#: in a call site is visible rather than silently gating nothing.
FEATURE_EXPORT_API = "export.api"


def is_pro_enabled(feature: str) -> bool:
    """Stub for future license-key gating (Gumroad/LemonSqueezy).

    Returns True unconditionally in Phase 7 — no paywall enforced yet.

    Args:
        feature: Feature key, e.g. :data:`FEATURE_EXPORT_API`.

    Returns:
        Always ``True``.
    """
    return True
