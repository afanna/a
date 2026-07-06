#!/usr/bin/env python3
import argparse
from PIL import Image
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 使用你提供的精确坐标
PRESET_REGIONS = [
    {"x1": 171, "y1": 112, "x2": 419, "y2": 359, "desc": "2×2日程卡片", "save_name": "q3_2.png"},
    {"x1": 30, "y1": 394, "x2": 562, "y2": 668, "desc": "2×4日程卡片", "save_name": "q3_4.png"}
]

def crop_and_save(img_path: Path, regions: list[dict], output_dir: Path) -> list[Path]:
    """根据坐标裁切图片并保存为指定文件名"""
    img = Image.open(img_path)
    saved_paths = []
    for region in regions:
        x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]
        # 裁切
        cropped = img.crop((x1, y1, x2, y2))
        # 按指定名称保存
        save_path = output_dir / region["save_name"]
        cropped.save(save_path)
        saved_paths.append(save_path)
        print(f"✅ 裁切成功：{save_path.name}，尺寸：{x2-x1}×{y2-y1}，描述：{region.get('desc', '')}")
    return saved_paths

def main():
    parser = argparse.ArgumentParser(description="自定义坐标裁切")
    parser.add_argument("--input", default="output/Snipaste_2026-07-02_15-58-22.png", help="输入原图路径")
    parser.add_argument("--output", type=str, default="demo/output", help="输出目录")
    args = parser.parse_args()
    
    img_path = Path(args.input).absolute()
    output_dir = Path(args.output).absolute()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not img_path.exists():
        print(f"❌ 原图不存在：{img_path}")
        return
    
    print(f"🚀 按自定义坐标裁切：{img_path.name}")
    saved = crop_and_save(img_path, PRESET_REGIONS, output_dir)
    print(f"\n🎉 完成！结果保存到：")
    for p in saved:
        print(f"  📄 {p}")

if __name__ == "__main__":
    main()
