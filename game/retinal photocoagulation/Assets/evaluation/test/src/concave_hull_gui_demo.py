"""
凹包算法 GUI 动画演示脚本

功能：
1. 同时展示四类点集：环形、矩形、十字型、退化型（易退化到凸包）
2. 通过 GUI 滑条实时调整 ratio，观察 concave hull 形状变化
3. 支持播放/暂停动画，自动扫过 ratio=0~1
"""

import math
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import shapely
from matplotlib.widgets import Button, Slider
from shapely.geometry import GeometryCollection, MultiPoint, MultiPolygon, Point, Polygon
from shapely.ops import triangulate

# macOS 常见中文字体兜底，避免标题/按钮乱码
plt.rcParams["font.sans-serif"] = [
    "PingFang SC",
    "Hiragino Sans GB",
    "STHeiti",
    "Heiti SC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False


@dataclass
class HullResult:
    geom: Polygon | MultiPolygon | Point | GeometryCollection
    used_fallback: bool
    reason: str


def generate_ring_points() -> np.ndarray:
    """生成不规则环形散点：带角度缺口、半径抖动、点分布不均匀。"""
    rng = np.random.default_rng(20260405)
    center = np.array([50.0, 50.0])

    # 留出一个明显缺口（约 35°~75°）
    gap_min = np.deg2rad(35)
    gap_max = np.deg2rad(75)

    pts = []
    for _ in range(360):
        theta = rng.uniform(0, 2 * np.pi)
        if gap_min <= theta <= gap_max:
            continue

        # 让环形厚度有变化：角度相关起伏 + 随机噪声
        base_radius = 21.0 + 3.5 * np.sin(2.7 * theta) + 1.8 * np.cos(5.2 * theta)
        jitter = rng.normal(0, 1.8)
        radius = np.clip(base_radius + jitter, 13.0, 30.0)

        x = center[0] + radius * np.cos(theta)
        y = center[1] + radius * np.sin(theta)
        pts.append([x, y])

    return np.array(pts, dtype=float)


def generate_rectangle_points() -> np.ndarray:
    """生成矩形边界点集。"""
    pts = []
    for x in np.linspace(15, 85, 100):
        pts.append([x, 20])
        pts.append([x, 80])
    for y in np.linspace(20, 80, 80):
        pts.append([15, y])
        pts.append([85, y])
    return np.array(pts, dtype=float)


def generate_cross_points() -> np.ndarray:
    """生成十字型点集（中心纵横两条臂）。"""
    pts = []
    for y in np.linspace(15, 85, 140):
        pts.append([50, y])
        pts.append([47, y])
        pts.append([53, y])
    for x in np.linspace(15, 85, 140):
        pts.append([x, 50])
        pts.append([x, 47])
        pts.append([x, 53])
    return np.array(pts, dtype=float)


def generate_degenerate_points() -> np.ndarray:
    """生成退化点集：大部分点几乎共线，触发凹包退化风险。"""
    pts = []
    for x in np.linspace(10, 90, 140):
        pts.append([x, 35 + 0.08 * math.sin(x)])
    # 少量离散点，仍可能导致 concave hull 在某些 ratio 下不稳定
    pts.extend([[20, 65], [80, 65], [50, 66]])
    return np.array(pts, dtype=float)


def generate_chaotic_points() -> np.ndarray:
    """生成混乱无序点集：多团簇 + 噪声点。"""
    rng = np.random.default_rng(20260404)
    c1 = rng.normal(loc=(25, 25), scale=(6.5, 5.0), size=(220, 2))
    c2 = rng.normal(loc=(70, 30), scale=(7.0, 6.0), size=(220, 2))
    c3 = rng.normal(loc=(48, 72), scale=(8.0, 7.5), size=(260, 2))
    noise = rng.uniform(low=8, high=92, size=(120, 2))
    pts = np.vstack([c1, c2, c3, noise])
    pts[:, 0] = np.clip(pts[:, 0], 0, 100)
    pts[:, 1] = np.clip(pts[:, 1], 0, 100)
    return pts.astype(float)


def compute_concave_hull(points: np.ndarray, ratio: float) -> HullResult:
    """
    计算凹包，必要时退化到凸包。
    退化条件：
    - 结果不是面（Polygon/MultiPolygon）
    - 结果无效（invalid）或面积接近 0
    """
    mp = MultiPoint(points.tolist())
    raw = shapely.concave_hull(mp, ratio=ratio, allow_holes=True)

    if isinstance(raw, (Polygon, MultiPolygon)) and raw.is_valid and raw.area > 1e-8:
        return HullResult(geom=raw, used_fallback=False, reason="concave_hull")

    convex = mp.convex_hull
    if isinstance(convex, (Polygon, MultiPolygon)) and convex.is_valid and convex.area > 1e-8:
        return HullResult(geom=convex, used_fallback=True, reason="fallback_to_convex_hull")

    # 极端情况下兜底返回原几何
    return HullResult(geom=raw, used_fallback=True, reason="fallback_failed_keep_raw")


def build_triangle_mesh(points: np.ndarray) -> list[Polygon]:
    """基于点集构建 Delaunay 三角网（用于演示小三角拼图）。"""
    mp = MultiPoint(points.tolist())
    tris = triangulate(mp)
    return [t for t in tris if isinstance(t, Polygon) and t.is_valid and t.area > 0]


def _draw_geom(ax, geom, face_color: str, edge_color: str, alpha: float) -> None:
    """在坐标轴上绘制 shapely 几何（支持洞）。"""
    if isinstance(geom, Polygon):
        x, y = geom.exterior.xy
        ax.fill(x, y, facecolor=face_color, edgecolor=edge_color, alpha=alpha, linewidth=2)
        for hole in geom.interiors:
            hx, hy = hole.xy
            ax.fill(hx, hy, color="white", alpha=1.0)
            ax.plot(hx, hy, color=edge_color, linewidth=1.5, linestyle="--")
        return

    if isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            _draw_geom(ax, poly, face_color, edge_color, alpha)
        return

    # 非面几何只画边界提示
    try:
        x, y = geom.xy
        ax.plot(x, y, color=edge_color, linewidth=2)
    except Exception:
        pass


def build_gui() -> None:
    datasets = {
        "环形点集": generate_ring_points(),
        "矩形点集": generate_rectangle_points(),
        "十字型点集": generate_cross_points(),
        "退化型点集(易回退)": generate_degenerate_points(),
        "混乱无序点集": generate_chaotic_points(),
    }

    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    axes = axes.flatten()
    plt.subplots_adjust(left=0.06, right=0.98, top=0.92, bottom=0.2, wspace=0.2, hspace=0.25)
    fig.suptitle("Concave Hull 可视化演示（拖动 ratio 观察形状变化）", fontsize=14)

    # ratio 滑条
    slider_ax = fig.add_axes([0.12, 0.10, 0.62, 0.04])
    ratio_slider = Slider(slider_ax, "ratio", 0.0, 1.0, valinit=0.5, valstep=0.01)

    # 播放/暂停按钮
    btn_ax = fig.add_axes([0.78, 0.10, 0.12, 0.05])
    play_button = Button(btn_ax, "播放")
    is_playing = {"value": False, "dir": 1}

    # 三角网显示开关
    mesh_btn_ax = fig.add_axes([0.78, 0.03, 0.12, 0.05])
    mesh_button = Button(mesh_btn_ax, "三角网:开")
    show_mesh = {"value": True}

    # 定时器实现动画
    timer = fig.canvas.new_timer(interval=70)

    def redraw(ratio: float) -> None:
        for ax, (title, points) in zip(axes, datasets.items()):
            ax.clear()
            ax.scatter(points[:, 0], points[:, 1], s=12, c="#1f77b4", alpha=0.85, label="点集")

            # 凸包始终画出来用于对比
            convex = MultiPoint(points.tolist()).convex_hull
            _draw_geom(ax, convex, face_color="#cccccc", edge_color="#666666", alpha=0.22)

            # 凹包（失败时内部自动回退到凸包）
            result = compute_concave_hull(points, ratio)

            # 演示三角拼图：灰色=全部三角网，绿色=落在当前凹包内的三角片
            if show_mesh["value"]:
                triangles = build_triangle_mesh(points)
                for tri in triangles:
                    tx, ty = tri.exterior.xy
                    ax.plot(tx, ty, color="#9e9e9e", linewidth=0.45, alpha=0.45)
                    centroid = tri.representative_point()
                    if hasattr(result.geom, "contains") and result.geom.contains(centroid):
                        ax.fill(tx, ty, color="#2ca02c", alpha=0.12)

            _draw_geom(ax, result.geom, face_color="#ff8c42", edge_color="#cc3d00", alpha=0.45)

            area_text = f"{result.geom.area:.2f}" if hasattr(result.geom, "area") else "N/A"
            status = "已回退到凸包" if result.used_fallback else "凹包成功"
            ax.set_title(f"{title}\n{status} | area={area_text}")
            ax.set_xlim(0, 100)
            ax.set_ylim(0, 100)
            ax.set_aspect("equal")
            ax.grid(alpha=0.2)

        # 最后一个空白子图隐藏（因为 2x3 放 5 组数据）
        for ax in axes[len(datasets) :]:
            ax.clear()
            ax.axis("off")

        fig.canvas.draw_idle()

    def on_slider_change(val: float) -> None:
        redraw(val)

    def on_timer() -> None:
        if not is_playing["value"]:
            return

        current = ratio_slider.val
        step = 0.01 * is_playing["dir"]
        nxt = current + step
        if nxt >= 1.0:
            nxt = 1.0
            is_playing["dir"] = -1
        elif nxt <= 0.0:
            nxt = 0.0
            is_playing["dir"] = 1
        ratio_slider.set_val(round(nxt, 2))

    def on_play_clicked(_event) -> None:
        is_playing["value"] = not is_playing["value"]
        play_button.label.set_text("暂停" if is_playing["value"] else "播放")
        if is_playing["value"]:
            timer.start()

    def on_mesh_clicked(_event) -> None:
        show_mesh["value"] = not show_mesh["value"]
        mesh_button.label.set_text("三角网:开" if show_mesh["value"] else "三角网:关")
        redraw(ratio_slider.val)

    timer.add_callback(on_timer)
    ratio_slider.on_changed(on_slider_change)
    play_button.on_clicked(on_play_clicked)
    mesh_button.on_clicked(on_mesh_clicked)

    redraw(ratio_slider.val)
    plt.show()


if __name__ == "__main__":
    build_gui()
