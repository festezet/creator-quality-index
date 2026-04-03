"""Scoring engine for YouTube Creator Quality Index."""
from backend.config import WEIGHTS, TIERS


def compute_composite(scores: dict) -> float | None:
    """Compute weighted composite score from individual scores."""
    fields = [
        ("score_research_depth", "research_depth"),
        ("score_production", "production"),
        ("score_signal_noise", "signal_noise"),
        ("score_originality", "originality"),
        ("score_lasting_impact", "lasting_impact"),
    ]
    values = []
    for db_field, weight_key in fields:
        val = scores.get(db_field)
        if val is None:
            return None
        values.append(val * WEIGHTS[weight_key])
    return round(sum(values), 2)


def compute_tier(composite: float | None) -> str | None:
    """Determine tier from composite score."""
    if composite is None:
        return None
    for tier, threshold in sorted(TIERS.items(), key=lambda x: -x[1]):
        if composite >= threshold:
            return tier
    return "D"


def score_channel(scores: dict) -> tuple[float | None, str | None]:
    """Compute composite score and tier for a channel."""
    composite = compute_composite(scores)
    tier = compute_tier(composite)
    return composite, tier
