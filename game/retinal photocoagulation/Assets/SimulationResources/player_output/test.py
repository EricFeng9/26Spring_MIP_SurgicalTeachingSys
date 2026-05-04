import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image
import os

def verify_laser_spots(image_path, json_path, output_path=None):
    """
    读取眼底图和激光打点JSON，并在图上绘制对应半径的圆圈进行验证。
    """
    if not os.path.exists(image_path):
        print(f"❌ 找不到图片文件: {image_path}")
        return
    if not os.path.exists(json_path):
        print(f"❌ 找不到JSON文件: {json_path}")
        return

    # 1. 加载图像
    img = Image.open(image_path)
    
    # 2. 读取 JSON 数据
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    shots = data.get('shots', [])
    print(f"✅ 成功加载数据，共找到 {len(shots)} 个激光打点记录。")

    # 3. 创建画板
    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)
    ax.imshow(img)

    # 4. 遍历所有打点并绘制圆圈
    for shot in shots:
        pos = shot.get('pos')
        radius = shot.get('radius_px')
        
        if pos and radius is not None:
            x, y = pos[0], pos[1]
            
            # 画一个红色的空心圆圈
            # edgecolor='r' 表示红色边框
            # facecolor='none' 表示内部透明，不遮挡眼底图
            circle = patches.Circle(
                (x, y), 
                radius=radius, 
                linewidth=1.2, 
                edgecolor='red', 
                facecolor='none',
                alpha=0.8
            )
            ax.add_patch(circle)
            
            # 可选：在圆心画一个小小的点，验证坐标中心是否准确
            ax.plot(x, y, marker='.', color='cyan', markersize=2)

    # 隐藏坐标轴
    plt.axis('off')
    plt.title(f"Laser Spot Verification - {len(shots)} spots", fontsize=14)
    plt.tight_layout()

    # 5. 显示或保存结果
    if output_path:
        plt.savefig(output_path, bbox_inches='tight', pad_inches=0)
        print(f"💾 验证图已保存至: {output_path}")
    
    # 弹窗显示
    plt.show()

if __name__ == "__main__":
    # === 请在这里替换为你的实际文件路径 ===
    # 假设导出文件都在同一目录下
    SESSION_ID = "SESS_20260503_214455" # 替换为你的 session_id
    
    IMG_FILE = f"{SESSION_ID}.png"
    JSON_FILE = f"{SESSION_ID}.json"
    OUTPUT_FILE = f"{SESSION_ID}_verified.png" # 如果不需要保存，设为 None

    print("🚀 开始验证渲染结果...")
    verify_laser_spots(IMG_FILE, JSON_FILE, OUTPUT_FILE)