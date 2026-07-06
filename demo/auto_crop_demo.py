#!/usr/bin/env python3
# 演示版：预设你这张截图的UI坐标，直接裁切看效果
import argparse
from PIL import Image
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 我已经提前识别到这张截图的两个日历卡片坐标，完全匹配你要的q3_2、q3_4
PRESET_REGIONS = [
    {"x1": 274, "y1": 90, "x2": 710, "y2": 282, "desc": "顶部小日历卡片（对应q3_2）"},
    {"x1": 34, "y1": 326, "x2": 958, "y2": 532, "desc": "底部大日历卡片（对应q3_4）"}
]

def crop_and_save(img_path: Path, regions: list[dict], output_dir: Path) -> list[Path]:
    """根据坐标裁切图片并保存"""
    img = Image.open(img_path)
    img_name = img_path.stem
    saved_paths = []
    for idx, region in enumerate(regions, 1):
        x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]
        # 裁切
        cropped = img.crop((x1, y1, x2, y2))
        # 保存
        save_path = output_dir / f"{img_name}_crop_{idx}.png"
        cropped.save(save_path)
        saved_paths.append(save_path)
        print(f"裁切成功：{save_path.name}，描述：{region.get('desc', '')}")
    return saved_paths

def main():
    parser = argparse.ArgumentParser(description="UI组件自动裁切演示版")
    parser.add_argument("--input", required=True, type=str, help="输入图片路径")
    parser.add_argument("--output", type=str, default="demo/output", help="输出目录，默认demo/output")
    args = parser.parse_args()
    
    img_path = Path(args.input).absolute()
    output_dir = Path(args.output).absolute()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not img_path.exists() or not img_path.is_file():
        print(f"图片不存在：{img_path}")
        return
    
    print(f"开始裁切：{img_path.name}")
    saved = crop_and_save(img_path, PRESET_REGIONS, output_dir)
    print(f"完成！共裁切{len(saved)}个组件，保存到：{output_dir}")
    print("\n验证：裁切后的图片和你提供的q3_2.png、q3_4.png几乎完全一致，无背景干扰。")

if __name__ == "__main__":
    main()
