"""The fixed field selection Pluvial-AI fetches per segment.

This list is deliberately small and named, not "everything Mireye has" —
credits are metered per field per location (see design spec §9) and every
field here maps to one of the four derived signals or the consequence
surface. No field is fetched speculatively.
"""
from __future__ import annotations

from typing import Literal, TypedDict

# Soil Movement Potential (design spec §4.1) — spatial discriminator.
SOIL_MOVEMENT_FIELDS = [
    "soil_shrink_swell_class",
    "soil_available_water_capacity",
    "soil_drainage_class",
    "bedrock_depth_cm",
    "in_karst_area",
    "karst_exposure_class",
    "soil_map_unit_name",  # the gate: 'Urban land' -> soil_usable = False
]

# Void Formation Likelihood (§4.2)
VOID_FORMATION_FIELDS = [
    "soil_erodibility_k_factor",
    "soil_hydrologic_group",
]

# Corroborating temporal signal (§4.2) — coarse, frequently null; NOAA NCEI
# daily precipitation is the primary trigger, this is the cited backstop.
DROUGHT_CORROBORATOR_FIELDS = [
    "drought_category",
]

# Consequence surface (§4.4) — priority, never probability.
CONSEQUENCE_FIELDS = [
    "nearest_school_distance_m",
    "nearest_hospital_distance_m",
    "nearest_major_road_class",
    "housing_units_within_1km",
    "public_water_system_population_served",
    "tract_population",
    "county_median_household_income",
]

# Context, cheap, used for the reporting-bias correction (§4.6) and general
# framing in agent explanations.
CONTEXT_FIELDS = [
    "elevation",
    "water_system_name",
    "within_water_service_area",
]

# Used by the Skeptic to rule out natural surface water as the source of a
# "standing water" complaint (design spec §5.2, usgs_gage tool).
GAGE_FIELDS = [
    "nearest_usgs_gage_daily_discharge_cfs",
    "nearest_usgs_gage_distance_m",
    "nearest_usgs_gage_name",
]

# Land-cover corroboration for "Urban land" points (design spec 2026-08-30
# addendum). "Urban land" is a soil-survey artifact — how the point was
# mapped, not a live reading of what's there now. These three fields are
# USFS LCMS, ~120m, completely independent of SSURGO: real evidence a
# soil-unusable point may still be less disturbed than the label implies.
# Confirmed valid against a live POST /v1/fetch/quote before adding here —
# unlike SOIL_COMPONENT_BREAKDOWN_FIELD above, these are real, priced,
# working fields today.
LAND_COVER_CORROBORATOR_FIELDS = [
    "land_use_class",
    "lcms_class",
    "tree_canopy_pct",
]

# Speculative: the component-percent breakdown behind an "Urban land
# complex" map unit (design spec 2026-08-30). Confirmed NOT in Mireye's
# live catalog as of 2026-08-30 (GET /v1/meta/fields) — every soil field
# there is explicitly "of the dominant component" only, sourced from the
# pre-collapsed gNATSGO raster.
#
# Deliberately NOT added to ALL_FIELDS. Verified live against
# POST /v1/fetch/quote: an unrecognised field name in the request fails
# the ENTIRE quote with `fields_unknown`, not a null for that field alone
# — so requesting it today would break every real analysis, not degrade
# gracefully. This name exists only so classify_soil_usability() below has
# a stable key to read *if* a future field request adds it and someone
# adds it to ALL_FIELDS at that point. Until then it is simply never
# present in any field_values dict, and classification always takes the
# fallback path.
SOIL_COMPONENT_BREAKDOWN_FIELD = "soil_component_breakdown"

ALL_FIELDS = (
    SOIL_MOVEMENT_FIELDS
    + VOID_FORMATION_FIELDS
    + DROUGHT_CORROBORATOR_FIELDS
    + CONSEQUENCE_FIELDS
    + CONTEXT_FIELDS
    + GAGE_FIELDS
    + LAND_COVER_CORROBORATOR_FIELDS
)

# de-dupe while preserving order (soil_map_unit_name etc. only listed once)
ALL_FIELDS = list(dict.fromkeys(ALL_FIELDS))

URBAN_LAND_MARKERS = ("urban land",)


def is_soil_usable(field_values: dict[str, object]) -> bool:
    """False when the dominant SSURGO component is Urban land — no
    shrink-swell, drainage or hydrologic-group data exists at that point.
    The agents must refuse to make a soil claim rather than guess.

    Accepts either a bare value or the {"value": ..., "source": ...} shape
    Mireye responses are normalized into (see mireye/wrapper.py).

    Thin wrapper over classify_soil_usability() for the many call sites
    (DB writes, API responses, negative-control eval) that only ever
    needed a boolean and should keep behaving exactly as before — the
    tri-state classification below is additive, not a replacement."""
    return classify_soil_usability(field_values)["status"] != "unusable"


# design spec 2026-08-30: below this share of the map unit being Urban
# land, treat the point as fully usable (today's path). At/above the
# ceiling, full veto (also today's path). In between, "partial" — the
# non-urban component's own data may be cited, capped and labelled.
# Starting guesses, not calibrated against real component distributions
# yet; expect these to move once soil_component_breakdown returns real
# data.
URBAN_PARTIAL_FLOOR_PCT = 20
URBAN_PARTIAL_CEILING_PCT = 80

SoilUsability = Literal["usable", "partial", "unusable"]


class SoilUsabilityResult(TypedDict):
    status: SoilUsability
    component: dict[str, object] | None


def classify_soil_usability(field_values: dict[str, object]) -> SoilUsabilityResult:
    """Tri-state successor to the old is_soil_usable() boolean.

    Returns {"status": "usable" | "partial" | "unusable", "component": {...} | None}.
    `component` is populated only for "partial", naming the largest
    non-urban SSURGO component and its own soil-movement values — what the
    Investigator may cite, attributed to that component specifically
    rather than to the map unit as a whole (see address_cascade.py).

    Falls back to exactly today's substring-on-map-unit-name behaviour
    whenever `soil_component_breakdown` (SOIL_COMPONENT_BREAKDOWN_FIELD) is
    absent — which is every real call today, since that field isn't in
    ALL_FIELDS (see the comment above it: requesting an unrecognised field
    name fails the entire Mireye quote, so it isn't fetched until Mireye's
    catalog actually has it). This function must never diverge from the
    old boolean's answer when the breakdown is missing — that divergence
    would be a silent behaviour change with no new data to justify it.
    """
    breakdown = field_values.get(SOIL_COMPONENT_BREAKDOWN_FIELD)
    if isinstance(breakdown, dict):
        breakdown = breakdown.get("value")

    if not isinstance(breakdown, list) or not breakdown:
        raw = field_values.get("soil_map_unit_name")
        if isinstance(raw, dict):
            raw = raw.get("value")
        if not raw:
            return {"status": "unusable", "component": None}
        unit_name = str(raw).lower()
        usable = not any(marker in unit_name for marker in URBAN_LAND_MARKERS)
        return {"status": "usable" if usable else "unusable", "component": None}

    urban_pct = 0.0
    non_urban: list[dict[str, object]] = []
    for comp in breakdown:
        name = str(comp.get("component_name", "")).lower()
        pct = float(comp.get("comppct_r") or 0)
        if any(marker in name for marker in URBAN_LAND_MARKERS):
            urban_pct += pct
        else:
            non_urban.append(comp)

    if urban_pct < URBAN_PARTIAL_FLOOR_PCT:
        return {"status": "usable", "component": None}
    if urban_pct >= URBAN_PARTIAL_CEILING_PCT or not non_urban:
        return {"status": "unusable", "component": None}

    largest = max(non_urban, key=lambda c: float(c.get("comppct_r") or 0))
    return {"status": "partial", "component": largest}
