from aesthetic_rule_check.math_utils import gaussian_score, json_pointer_get, json_pointer_set, text_similarity


def test_gaussian_score_peaks_at_mean() -> None:
    assert gaussian_score(0.42, 0.42, 0.1) == 100
    assert gaussian_score(0.62, 0.42, 0.1) < 20


def test_json_pointer_set_and_get() -> None:
    data = {}
    json_pointer_set(data, "/weather/temp", "26°")

    assert json_pointer_get(data, "/weather/temp") == "26°"


def test_text_similarity_ignores_spacing_and_punctuation() -> None:
    assert text_similarity("还有 15 分钟", "还有15分钟") >= 0.9
