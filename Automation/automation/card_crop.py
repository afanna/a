from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

import cv2
import numpy as np
from PIL import Image


CardType = Literal["2x2", "2x4"]
CardTypeOption = Literal["auto", "2x2", "2x4"]


@dataclass(frozen=True)
class CropBox:
    x1: int
    y1: int
    x2: int
    y2: int

    @classmethod
    def from_json(cls, value: object, *, name: str) -> "CropBox":
        if isinstance(value, dict):
            try:
                return cls(
                    x1=int(value["x1"]),
                    y1=int(value["y1"]),
                    x2=int(value["x2"]),
                    y2=int(value["y2"]),
                )
            except KeyError as exc:
                raise ValueError(f"{name} missing coordinate key: {exc.args[0]}") from exc

        if isinstance(value, list | tuple) and len(value) == 4:
            return cls(x1=int(value[0]), y1=int(value[1]), x2=int(value[2]), y2=int(value[3]))

        raise ValueError(f"{name} must be {{\"x1\": int, \"y1\": int, \"x2\": int, \"y2\": int}} or [x1, y1, x2, y2]")

    def clamp(self, width: int, height: int) -> tuple[int, int, int, int]:
        x_start, x_end = clamp_bounds(self.x1, self.x2, width)
        y_start, y_end = clamp_bounds(self.y1, self.y2, height)
        return x_start, y_start, x_end, y_end


@dataclass(frozen=True)
class CardCropConfig:
    crop_box_2x2: CropBox = field(default_factory=lambda: CropBox(364, 96, 920, 576))
    crop_box_2x4: CropBox = field(default_factory=lambda: CropBox(95, 96, 1192, 576))
    detect_box: CropBox = field(default_factory=lambda: CropBox(0, 96, 1280, 576))
    wide_card_threshold: float = 0.80
    bg_gray_threshold: int = 235
    min_block_width: int = 50
    col_gap_threshold: int = 15
    col_content_threshold: int = 3
    row_content_threshold: int = 2
    y_refine_top_margin: int = 2
    y_refine_bottom_margin: int = 3
    card_type: CardTypeOption = "auto"

    @classmethod
    def from_json(cls, path: Path) -> "CardCropConfig":
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.loads(strip_json_comments(f.read()))
        if not isinstance(data, dict):
            raise ValueError(f"Card crop config must be a JSON object: {path}")

        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"Unknown card crop config keys in {path}: {', '.join(unknown)}")

        data = dict(data)
        for key in ("crop_box_2x2", "crop_box_2x4", "detect_box"):
            if key in data:
                data[key] = CropBox.from_json(data[key], name=key)
        return cls(**data)


def strip_json_comments(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    in_line_comment = False
    in_block_comment = False

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
                output.append(char)
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue

        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue

        output.append(char)
        index += 1

    return "".join(output)


@dataclass(frozen=True)
class CardCropResult:
    source_path: Path
    card_path: Path
    card_type: CardType
    box: tuple[int, int, int, int]
    content_width_ratio: float
    debug_path: Path | None = None


class CardCropper:
    def __init__(self, config: CardCropConfig | None = None):
        self.config = config or CardCropConfig()

    def crop(
        self,
        input_path: Path,
        output_dir: Path | None = None,
        *,
        output_path: Path | None = None,
        debug: bool = False,
        debug_dir: Path | None = None,
    ) -> CardCropResult:
        input_path = Path(input_path)
        if not input_path.exists() or not input_path.is_file():
            raise FileNotFoundError(input_path)
        if output_path is None:
            target_dir = Path(output_dir) if output_dir else input_path.parent
            output_path = target_dir / f"{input_path.stem}_card.png"
        else:
            output_path = Path(output_path)

        image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Failed to read image: {input_path}")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid image size: {input_path}")

        if self.config.card_type == "auto":
            detected_type, content_width_ratio = self._detect_card_type(gray, width, height)
            card_type = detected_type
        else:
            card_type = self.config.card_type
            content_width_ratio = 0.0

        box = self._crop_box(card_type, width, height)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(input_path) as pil_image:
            pil_image.crop(box).save(output_path)

        debug_path = None
        if debug:
            target_debug_dir = Path(debug_dir) if debug_dir else output_path.parent / "_debug"
            debug_path = target_debug_dir / f"{input_path.stem}_card_annotated.png"
            self._save_debug(image, box, debug_path)

        return CardCropResult(
            source_path=input_path,
            card_path=output_path,
            card_type=card_type,
            box=box,
            content_width_ratio=content_width_ratio,
            debug_path=debug_path,
        )

    def crop_many(
        self,
        input_paths: Iterable[Path],
        output_dir: Path,
        *,
        debug: bool = False,
    ) -> list[CardCropResult]:
        results: list[CardCropResult] = []
        for input_path in input_paths:
            results.append(self.crop(input_path, output_dir, debug=debug))
        return results

    def _detect_card_type(self, gray: np.ndarray, img_w: int, img_h: int) -> tuple[CardType, float]:
        x_start, y_start, x_end, y_end = self.config.detect_box.clamp(img_w, img_h)
        band_gray = gray[y_start:y_end, x_start:x_end]
        content_mask = band_gray < self.config.bg_gray_threshold
        col_proj = content_mask.sum(axis=0)
        content_cols = np.where(col_proj > self.config.col_content_threshold)[0]
        blocks = [
            (start, end)
            for start, end in contiguous_blocks(content_cols, self.config.col_gap_threshold)
            if end - start + 1 >= self.config.min_block_width
        ]

        if not blocks:
            return "2x2", 0.0

        x_min = x_start + min(start for start, _ in blocks)
        x_max = x_start + max(end for _, end in blocks)
        content_width_ratio = (x_max - x_min) / img_w
        card_type: CardType = "2x4" if content_width_ratio > self.config.wide_card_threshold else "2x2"
        return card_type, content_width_ratio

    def _crop_box(self, card_type: CardType, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        config_box = self.config.crop_box_2x4 if card_type == "2x4" else self.config.crop_box_2x2
        return config_box.clamp(img_w, img_h)

    def _save_debug(self, image: np.ndarray, box: tuple[int, int, int, int], debug_path: Path) -> None:
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        annotated = image.copy()
        x_start, y_start, x_end, y_end = box
        cv2.rectangle(annotated, (x_start, y_start), (x_end - 1, y_end - 1), (0, 0, 255), 2)
        cv2.imwrite(str(debug_path), annotated)


def load_card_crop_config(path: Path | None) -> CardCropConfig:
    if path is None:
        return CardCropConfig()
    return CardCropConfig.from_json(path)


def find_image_files(input_path: Path) -> list[Path]:
    input_path = Path(input_path)
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(input_path)

    image_files: list[Path] = []
    for pattern in ("*.png", "*.jpg", "*.jpeg"):
        image_files.extend(input_path.glob(pattern))
    return sorted(path for path in image_files if not path.stem.endswith("_card"))


def contiguous_blocks(indices: np.ndarray, gap_threshold: int) -> list[tuple[int, int]]:
    if indices.size == 0:
        return []

    blocks: list[tuple[int, int]] = []
    start = int(indices[0])
    previous = int(indices[0])
    for raw_index in indices[1:]:
        index = int(raw_index)
        if index - previous > gap_threshold:
            blocks.append((start, previous))
            start = index
        previous = index
    blocks.append((start, previous))
    return blocks


def clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def clamp_bounds(start: int, end: int, maximum: int) -> tuple[int, int]:
    start = clamp_int(start, 0, maximum)
    end = clamp_int(end, start + 1, maximum)
    return start, end
