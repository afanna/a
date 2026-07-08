#!/usr/bin/env python3
# UI组件自动裁切程序，使用豆包多模态识别
import base64
import httpx
import json
import argparse
from PIL import Image
from pathlib import Path
import sys
# 修复控制台编码问题
sys.stdout.reconfigure(encoding='utf-8')

# 配置，和你现有API参数一致
API_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
API_KEY = ""
MODEL_NAME = "doubao-seed-2-0-lite"

def image_to_base64(img_path: Path) -> str:
    """图片转base64编码"""
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def detect_ui_components(img_path: Path) -> list[dict]:
    """调用豆包多模态识别UI组件坐标"""
    img_b64 = image_to_base64(img_path)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    prompt = """
你是专业的UI测试视觉定位助手，请识别这张手机截图中所有我们生成的UI组件（卡片/小程序/界面），不要识别桌面壁纸、状态栏、底部导航栏、系统图标，只识别非系统的、我们生成的UI组件。
返回每个组件的精确矩形边界坐标，JSON格式，不要其他任何内容，格式严格如下：
{"regions": [{"x1": 左边界像素(int), "y1": 上边界像素(int), "x2": 右边界像素(int), "y2": 下边界像素(int), "desc": "组件描述"}]}
坐标要精确到像素，x1 < x2，y1 < y2，不要有多余内容。
    """.strip()
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                ]
            }
        ],
        "temperature": 0.0,
        "max_tokens": 1024
    }
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{API_BASE_URL}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # 提取JSON（处理可能的包裹）
            if content.startswith("```"):
                content = content.split("```")[1].strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            result = json.loads(content)
            return result.get("regions", [])
    except Exception as e:
        print(f"识别失败：{str(e)}")
        return []

def crop_and_save(img_path: Path, regions: list[dict], output_dir: Path) -> list[Path]:
    """根据坐标裁切图片并保存"""
    img = Image.open(img_path)
    img_name = img_path.stem
    saved_paths = []
    for idx, region in enumerate(regions, 1):
        try:
            x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]
            # 校验坐标合法性
            if x1 < 0 or y1 < 0 or x2 > img.width or y2 > img.height or x1 >= x2 or y1 >= y2:
                print(f"跳过无效坐标：{region}")
                continue
            # 裁切
            cropped = img.crop((x1, y1, x2, y2))
            # 保存
            save_path = output_dir / f"{img_name}_crop_{idx}.png"
            cropped.save(save_path)
            saved_paths.append(save_path)
            print(f"裁切成功：{save_path.name}，位置：({x1},{y1})-({x2},{y2})，描述：{region.get('desc', '')}")
        except Exception as e:
            print(f"裁切失败：{str(e)}")
    return saved_paths

def main():
    parser = argparse.ArgumentParser(description="UI组件自动裁切程序，使用豆包多模态识别")
    parser.add_argument("--input", required=True, type=str, help="输入图片路径")
    parser.add_argument("--output", type=str, default="demo/output", help="输出目录，默认demo/output")
    args = parser.parse_args()
    
    img_path = Path(args.input).absolute()
    output_dir = Path(args.output).absolute()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not img_path.exists() or not img_path.is_file():
        print(f"图片不存在：{img_path}")
        return
    
    print(f"开始识别：{img_path.name}")
    regions = detect_ui_components(img_path)
    if not regions:
        print("未识别到任何UI组件")
        return
    
    print(f"识别到{len(regions)}个UI组件，开始裁切...")
    saved = crop_and_save(img_path, regions, output_dir)
    print(f"完成！共成功裁切{len(saved)}个组件，保存到：{output_dir}")

if __name__ == "__main__":
    main()
