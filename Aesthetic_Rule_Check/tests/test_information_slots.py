from aesthetic_rule_check.metrics.information import slots_match


def test_temperature_number_passes_when_ocr_misses_unit() -> None:
    match = slots_match("25℃", ["25"], full_threshold=0.9)

    assert match["status"] == "weak_pass"
    assert match["score"] == 0.75
    assert match["numbers"] == ["25"]
    assert match["missing_units"] == ["℃"]


def test_equivalent_temperature_units_match() -> None:
    match = slots_match("25℃", ["25 °C"], full_threshold=0.9)

    assert match["status"] in {"pass", "numeric_pass"}
    assert match["score"] >= 0.85


def test_short_required_text_visible_inside_ocr_phrase() -> None:
    match = slots_match("相册", ["相册缓存"], full_threshold=0.9)

    assert match["status"] == "pass"
    assert match["score"] == 1.0
