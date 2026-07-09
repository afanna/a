from pathlib import Path

from aesthetic_rule_check.dsl import load_dsl_info
from aesthetic_rule_check.dsl import resolve_dynamic_string


def test_extracts_static_path_and_format_string(tmp_path: Path) -> None:
    dsl = tmp_path / "sample.jsonl"
    dsl.write_text(
        "\n".join(
            [
                '{"version":"v0.9","updateComponents":{"surfaceId":"s","components":['
                '{"id":"a","component":"Text","content":"天气"},'
                '{"id":"b","component":"Text","content":{"path":"/weather/temp"}},'
                '{"id":"c","component":"Text","content":{"call":"formatString","args":{"value":"还有 ${/count} 分钟"}}},'
                '{"id":"d","component":"Text","content":" "}'
                ']}}',
                '{"version":"v0.9","updateDataModel":{"surfaceId":"s","path":"/","value":{"weather":{"temp":"26°"},"count":15}}}',
            ]
        ),
        encoding="utf-8",
    )

    info = load_dsl_info(dsl)
    texts = [item.text for item in info.required_texts]

    assert "天气" in texts
    assert "26°" in texts
    assert "还有 15 分钟" in texts
    assert " " not in texts


def test_missing_dsl_has_no_required_text() -> None:
    info = load_dsl_info(None)

    assert info.required_texts == []
    assert info.component_count == 0


def test_missing_dsl_file_does_not_raise(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"

    info = load_dsl_info(missing)

    assert info.required_texts == []
    assert info.component_count == 0
    assert info.warnings
    assert "DSL 文件不存在" in info.warnings[0]


def test_resolves_extended_data_model_expression() -> None:
    data_model = {
        "user": {"name": "北京"},
        "items": [{"title": "晴"}],
        "count": 3,
    }

    assert resolve_dynamic_string("{{ $__dataModel.user.name }}", data_model) == "北京"
    assert resolve_dynamic_string("{{ '天气：' + $__dataModel.items[0].title + ' ' + $__dataModel.count }}", data_model) == "天气：晴 3"
    assert resolve_dynamic_string("城市 ${/user/name}", data_model) == "城市 北京"


def test_extracts_extended_display_fields(tmp_path: Path) -> None:
    dsl = tmp_path / "extended.jsonl"
    dsl.write_text(
        '{"version":"v0.9","updateComponents":{"surfaceId":"s","components":['
        '{"id":"a","component":"Extended.Text","content":"标题"},'
        '{"id":"b","component":"TextInput","placeholder":"请输入城市","text":{"path":"/city"}},'
        '{"id":"c","component":"Toggle","label":"专注模式"},'
        '{"id":"d","component":"TabContent","title":"日程"},'
        '{"id":"e","component":"Select","options":[{"label":"北京"},{"title":"上海"}]}'
        ']}}\n'
        '{"version":"v0.9","updateDataModel":{"surfaceId":"s","path":"/","value":{"city":"深圳"}}}',
        encoding="utf-8",
    )

    info = load_dsl_info(dsl)
    texts = {item.text for item in info.required_texts}

    assert {"标题", "请输入城市", "深圳", "专注模式", "日程", "北京", "上海"} <= texts
