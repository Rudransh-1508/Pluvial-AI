from pluvial.mireye.fields import classify_soil_usability, is_soil_usable


def test_urban_land_dominant_is_unusable():
    assert is_soil_usable({"soil_map_unit_name": {"value": "Urban land, till substratum, 0 to 3 percent slopes"}}) is False
    assert is_soil_usable({"soil_map_unit_name": {"value": "Urban land-Greenbelt complex"}}) is False


def test_natural_soil_is_usable():
    assert is_soil_usable({"soil_map_unit_name": {"value": "Lake Charles clay, 0 to 1 percent slopes"}}) is True
    assert is_soil_usable({"soil_map_unit_name": {"value": "Bernard clay loam, 0 to 1 percent slopes"}}) is True


def test_missing_field_is_unusable_not_assumed_true():
    assert is_soil_usable({}) is False
    assert is_soil_usable({"soil_map_unit_name": {"value": None}}) is False


def test_bare_string_values_also_handled():
    # is_soil_usable should tolerate a raw string value, not only {value: ...}
    assert is_soil_usable({"soil_map_unit_name": "Urban land"}) is False
    assert is_soil_usable({"soil_map_unit_name": "Trinity clay, 0 to 1 percent slopes"}) is True


# --- classify_soil_usability: tri-state successor, design spec 2026-08-30 ---
# soil_component_breakdown is never actually fetched today (not in
# ALL_FIELDS — see fields.py comment on why), so every one of these cases
# except the synthetic-breakdown ones is exercising the exact fallback path
# production traffic takes right now.


def test_no_breakdown_field_falls_back_to_boolean_exactly():
    """The regression guard: with no component data, classify must agree
    with is_soil_usable() on every case that function already covers —
    this is the actual behaviour of every real request today."""
    cases = [
        {},
        {"soil_map_unit_name": {"value": None}},
        {"soil_map_unit_name": "Urban land"},
        {"soil_map_unit_name": "Trinity clay, 0 to 1 percent slopes"},
        {"soil_map_unit_name": {"value": "Urban land-Greenbelt complex"}},
        {"soil_map_unit_name": {"value": "Lake Charles clay, 0 to 1 percent slopes"}},
    ]
    for values in cases:
        expected = "usable" if is_soil_usable(values) else "unusable"
        result = classify_soil_usability(values)
        assert result["status"] == expected, values
        assert result["component"] is None


def test_breakdown_below_floor_is_usable():
    values = {
        "soil_map_unit_name": "Denver-Urban land complex, 2 to 5 percent slopes",
        "soil_component_breakdown": [
            {"component_name": "Denver", "comppct_r": 85, "soil_shrink_swell_class": "Moderate"},
            {"component_name": "Urban land", "comppct_r": 15},
        ],
    }
    result = classify_soil_usability(values)
    assert result["status"] == "usable"
    assert result["component"] is None


def test_breakdown_in_partial_band_cites_largest_non_urban_component():
    values = {
        "soil_map_unit_name": "Denver-Urban land complex, 2 to 5 percent slopes",
        "soil_component_breakdown": [
            {"component_name": "Urban land", "comppct_r": 60},
            {"component_name": "Denver", "comppct_r": 40, "soil_shrink_swell_class": "Moderate"},
        ],
    }
    result = classify_soil_usability(values)
    assert result["status"] == "partial"
    assert result["component"]["component_name"] == "Denver"
    assert result["component"]["comppct_r"] == 40


def test_breakdown_picks_largest_of_multiple_non_urban_components():
    values = {
        "soil_map_unit_name": "Some-Urban land complex",
        "soil_component_breakdown": [
            {"component_name": "Urban land", "comppct_r": 50},
            {"component_name": "Minor series", "comppct_r": 15},
            {"component_name": "Major series", "comppct_r": 35, "soil_shrink_swell_class": "High"},
        ],
    }
    result = classify_soil_usability(values)
    assert result["status"] == "partial"
    assert result["component"]["component_name"] == "Major series"


def test_breakdown_at_or_above_ceiling_is_unusable():
    values = {
        "soil_map_unit_name": "Mostly-Urban land complex",
        "soil_component_breakdown": [
            {"component_name": "Urban land", "comppct_r": 80},
            {"component_name": "Remnant", "comppct_r": 20, "soil_shrink_swell_class": "Low"},
        ],
    }
    result = classify_soil_usability(values)
    assert result["status"] == "unusable"
    assert result["component"] is None


def test_breakdown_fully_urban_is_unusable():
    values = {
        "soil_map_unit_name": "Urban land",
        "soil_component_breakdown": [{"component_name": "Urban land", "comppct_r": 100}],
    }
    result = classify_soil_usability(values)
    assert result["status"] == "unusable"
    assert result["component"] is None


def test_empty_breakdown_list_falls_back_to_substring_match():
    values = {
        "soil_map_unit_name": "Urban land",
        "soil_component_breakdown": [],
    }
    result = classify_soil_usability(values)
    assert result["status"] == "unusable"
