"""Scoring feedback + preferences endpoints with nudge algorithm."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from boat_ride.auth import get_current_user
from boat_ride.db import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/scoring", tags=["scoring"])

# Rating → implied score mapping
RATING_TO_SCORE = {1: 10, 2: 35, 3: 60, 4: 80, 5: 95}

# Nudge step per feedback
NUDGE_STEP = 0.03
OFFSET_STEP = 1.0

# Multiplier bounds
MULT_MIN = 0.2
MULT_MAX = 3.0
OFFSET_MIN = -20.0
OFFSET_MAX = 20.0

# Condition keys that map to multiplier fields
CONDITION_TO_MULTIPLIER = {
    "wind_kt": "wind_multiplier",
    "wind_gust_kt": "wind_multiplier",
    "wave_ft": "wave_multiplier",
    "wave_period_s": "period_multiplier",
    "wave_steepness": "chop_multiplier",
    "pop": "precip_multiplier",
    "tide_rate_ft_per_hr": "tide_multiplier",
    "tide_ft": "tide_multiplier",
}

# Thresholds: condition is "active" if its value exceeds this
CONDITION_THRESHOLDS = {
    "wind_kt": 5.0,
    "wind_gust_kt": 10.0,
    "wave_ft": 0.5,
    "wave_period_s": 0.0,  # always active if present (short period = bad)
    "wave_steepness": 0.015,
    "pop": 0.1,
    "tide_rate_ft_per_hr": 0.3,
    "tide_ft": 0.0,
}


class PreferencesOut(BaseModel):
    wind_multiplier: float = 1.0
    wave_multiplier: float = 1.0
    period_multiplier: float = 1.0
    chop_multiplier: float = 1.0
    precip_multiplier: float = 1.0
    tide_multiplier: float = 1.0
    overall_offset: float = 0.0


class FeedbackIn(BaseModel):
    lat: float
    lon: float
    original_score: float = Field(..., ge=0, le=100)
    user_rating: int = Field(..., ge=1, le=5)
    conditions_snapshot: Optional[Dict[str, Any]] = None


class FeedbackOut(BaseModel):
    message: str
    nudged_fields: list[str] = []
    new_preferences: PreferencesOut


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _get_or_create_prefs(sb, user_id: str) -> dict:
    """Fetch scoring_preferences for user, creating a default row if missing."""
    resp = (
        sb.table("scoring_preferences")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    if resp.data:
        return resp.data[0]

    # Create default row
    default = {"user_id": user_id}
    resp = sb.table("scoring_preferences").insert(default).execute()
    return resp.data[0]


def _identify_active_factors(snapshot: Optional[Dict[str, Any]]) -> set[str]:
    """Return set of multiplier field names where conditions were active."""
    if not snapshot:
        return set()
    active = set()
    for cond_key, mult_field in CONDITION_TO_MULTIPLIER.items():
        val = snapshot.get(cond_key)
        if val is not None:
            threshold = CONDITION_THRESHOLDS.get(cond_key, 0.0)
            try:
                if abs(float(val)) > threshold:
                    active.add(mult_field)
            except (TypeError, ValueError):
                pass
    return active


def _nudge_prefs(prefs_row: dict, direction: float, active_fields: set[str]) -> list[str]:
    """
    Nudge multipliers in-place. direction > 0 means user thinks score was too LOW
    (needs less penalty → decrease multipliers). direction < 0 means score was too HIGH.

    Returns list of nudged field names.
    """
    nudged = []

    if active_fields:
        for field in active_fields:
            old = prefs_row.get(field, 1.0)
            # direction > 0: score too low → decrease multiplier (less penalty)
            # direction < 0: score too high → increase multiplier (more penalty)
            new = old - (NUDGE_STEP * direction)
            prefs_row[field] = _clamp(new, MULT_MIN, MULT_MAX)
            if prefs_row[field] != old:
                nudged.append(field)
    else:
        # No specific factors identified → adjust overall offset
        old = prefs_row.get("overall_offset", 0.0)
        # direction > 0: score too low → increase offset (boost score)
        new = old + (OFFSET_STEP * direction)
        prefs_row["overall_offset"] = _clamp(new, OFFSET_MIN, OFFSET_MAX)
        if prefs_row["overall_offset"] != old:
            nudged.append("overall_offset")

    return nudged


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    row = _get_or_create_prefs(sb, user_id)
    return PreferencesOut(
        wind_multiplier=row.get("wind_multiplier", 1.0),
        wave_multiplier=row.get("wave_multiplier", 1.0),
        period_multiplier=row.get("period_multiplier", 1.0),
        chop_multiplier=row.get("chop_multiplier", 1.0),
        precip_multiplier=row.get("precip_multiplier", 1.0),
        tide_multiplier=row.get("tide_multiplier", 1.0),
        overall_offset=row.get("overall_offset", 0.0),
    )


@router.post("/feedback", response_model=FeedbackOut)
def submit_feedback(body: FeedbackIn, user_id: str = Depends(get_current_user)):
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # 1. Store feedback
    feedback_row = {
        "user_id": user_id,
        "lat": body.lat,
        "lon": body.lon,
        "original_score": body.original_score,
        "user_rating": body.user_rating,
        "conditions_snapshot": body.conditions_snapshot,
    }
    sb.table("scoring_feedback").insert(feedback_row).execute()

    # 2. Compute mismatch
    implied_score = RATING_TO_SCORE.get(body.user_rating, 60)
    mismatch = implied_score - body.original_score  # positive = user thinks it's better

    if abs(mismatch) < 5:
        prefs_row = _get_or_create_prefs(sb, user_id)
        return FeedbackOut(
            message="Score aligned with your rating, no adjustment needed",
            nudged_fields=[],
            new_preferences=PreferencesOut(
                wind_multiplier=prefs_row.get("wind_multiplier", 1.0),
                wave_multiplier=prefs_row.get("wave_multiplier", 1.0),
                period_multiplier=prefs_row.get("period_multiplier", 1.0),
                chop_multiplier=prefs_row.get("chop_multiplier", 1.0),
                precip_multiplier=prefs_row.get("precip_multiplier", 1.0),
                tide_multiplier=prefs_row.get("tide_multiplier", 1.0),
                overall_offset=prefs_row.get("overall_offset", 0.0),
            ),
        )

    # 3. Identify active factors from conditions snapshot
    active_fields = _identify_active_factors(body.conditions_snapshot)

    # 4. Load current prefs and nudge
    prefs_row = _get_or_create_prefs(sb, user_id)
    direction = 1.0 if mismatch > 0 else -1.0
    nudged = _nudge_prefs(prefs_row, direction, active_fields)

    # 5. Write updated prefs back
    update_fields = {
        "wind_multiplier": prefs_row.get("wind_multiplier", 1.0),
        "wave_multiplier": prefs_row.get("wave_multiplier", 1.0),
        "period_multiplier": prefs_row.get("period_multiplier", 1.0),
        "chop_multiplier": prefs_row.get("chop_multiplier", 1.0),
        "precip_multiplier": prefs_row.get("precip_multiplier", 1.0),
        "tide_multiplier": prefs_row.get("tide_multiplier", 1.0),
        "overall_offset": prefs_row.get("overall_offset", 0.0),
    }
    sb.table("scoring_preferences").update(update_fields).eq("user_id", user_id).execute()

    return FeedbackOut(
        message=f"Preferences nudged based on your feedback (mismatch={mismatch:+.0f})",
        nudged_fields=nudged,
        new_preferences=PreferencesOut(**update_fields),
    )
