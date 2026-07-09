from pathlib import Path

from main import find_images, find_matching_dsl


def test_find_images_and_matching_dsl(tmp_path: Path) -> None:
    input_dir = tmp_path / "images"
    dsl_dir = tmp_path / "dsl"
    input_dir.mkdir()
    dsl_dir.mkdir()
    image = input_dir / "q1.png"
    image.write_bytes(b"fake")
    (input_dir / "notes.txt").write_text("ignore", encoding="utf-8")
    dsl = dsl_dir / "q1.jsonl"
    dsl.write_text("{}", encoding="utf-8")

    assert find_images(input_dir) == [image.resolve()]
    assert find_matching_dsl(image, dsl_dir) == dsl.resolve()
