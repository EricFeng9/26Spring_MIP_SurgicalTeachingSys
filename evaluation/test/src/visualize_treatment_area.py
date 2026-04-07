import json
import os
import sys

from PIL import Image, ImageDraw
from shapely.geometry import MultiPolygon, Polygon

# 导入主评估模块中的有效靶区构建算法
MAIN_SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../main/src"))
sys.path.append(MAIN_SRC_PATH)

from evaluator import _build_player_treatment_area, _normalize_shots  # noqa: E402


def _draw_polygon_with_holes(draw: ImageDraw.ImageDraw, polygon: Polygon) -> None:
    """绘制单个多边形（含内部空洞）。"""
    ext = [(float(x), float(y)) for x, y in polygon.exterior.coords]
    draw.polygon(ext, fill=(255, 80, 0, 70), outline=(255, 80, 0, 220), width=2)

    # 内部空洞用透明擦除，让可视化结果与几何定义一致
    for hole in polygon.interiors:
        hole_pts = [(float(x), float(y)) for x, y in hole.coords]
        draw.polygon(hole_pts, fill=(0, 0, 0, 0), outline=(0, 170, 255, 220), width=2)


def main() -> None:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    output_dir = os.path.join(project_root, "evaluation", "test", "output")
    os.makedirs(output_dir, exist_ok=True)

    # 两组样例都做可视化
    cases = [
        ("player", "player.json", "player.png"),
        ("gt", "gt.json", "gt.png"),
    ]

    for case_name, json_name, img_name in cases:
        json_path = os.path.join(project_root, "evaluation", "test", "sample_data", json_name)
        img_path = os.path.join(project_root, "evaluation", "test", "sample_data", img_name)
        output_img_path = os.path.join(output_dir, f"{case_name}_treatment_area_visualization.png")

        with open(json_path, "r", encoding="utf-8") as f:
            session_data = json.load(f)

        # 调用 evaluator.py 中当前算法：统一日志结构 -> 构建有效靶区几何
        all_shots = _normalize_shots(session_data)
        valid_shots = [s for s in all_shots if not s.get("is_trial", False)]
        player_area = _build_player_treatment_area(valid_shots)
        if player_area is None:
            raise RuntimeError(f"未能从 {json_name} 构建有效靶区，请检查输入数据。")

        base_img = Image.open(img_path).convert("RGBA")
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")

        if isinstance(player_area, Polygon):
            _draw_polygon_with_holes(draw, player_area)
        elif isinstance(player_area, MultiPolygon):
            for poly in player_area.geoms:
                _draw_polygon_with_holes(draw, poly)
        else:
            raise RuntimeError(f"暂不支持的几何类型: {player_area.geom_type}")

        # 叠加并导出可视化结果
        vis_img = Image.alpha_composite(base_img, overlay)
        vis_img.save(output_img_path)

        hole_count = 0
        if isinstance(player_area, Polygon):
            hole_count = len(player_area.interiors)
        elif isinstance(player_area, MultiPolygon):
            hole_count = sum(len(poly.interiors) for poly in player_area.geoms)

        print(f"[{case_name}] 可视化已生成: {output_img_path}")
        print(f"[{case_name}] 几何类型: {player_area.geom_type}")
        print(f"[{case_name}] 总面积: {player_area.area:.2f}")
        print(f"[{case_name}] 内部空洞数: {hole_count}")


if __name__ == "__main__":
    main()
