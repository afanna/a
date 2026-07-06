# UI自动裁切Demo
## 安装依赖
```powershell
pip install httpx pillow
```

## 使用方法
```powershell
# 裁切指定图片
python demo/auto_crop_ui.py --input output/Snipaste_2026-07-02_15-58-22.png

# 指定输出目录
python demo/auto_crop_ui.py --input output/Snipaste_2026-07-02_15-58-22.png --output demo/my_output
```

## 效果
会自动识别截图中的UI组件，逐个裁切出来保存到输出目录，文件名类似：Snipaste_2026-07-02_15-58-22_crop_1.png、Snipaste_2026-07-02_15-58-22_crop_2.png

## 验证
裁切后的图片和你提供的q3_2.png、q3_4.png几乎完全一致，无背景干扰。
