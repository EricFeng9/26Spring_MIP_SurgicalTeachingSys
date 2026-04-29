import json
import math
import os
import tarfile
import traceback
from io import BytesIO
from typing import Any

import numpy as np
import shapely
from PIL import Image, ImageDraw
from shapely.geometry import MultiPoint, Point, Polygon

def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return data


def _safe_polygon(coords: list, holes: list | None = None) -> Polygon | None:
    if not isinstance(coords, list) or len(coords) < 3:
        return None
    polygon = Polygon(coords, holes=holes if holes else None)
    if not polygon.is_valid or polygon.area <= 0:
        return None
    return polygon


def _param_score(player_avg: float, gt: float, tau: float, max_score: float) -> tuple[float, float]:
    deviation = abs(player_avg - gt) / (abs(gt) + 1e-6)
    score = max_score * max(0.0, 1.0 - min(deviation / max(tau, 1e-6), 1.0))
    return score, deviation


def _normalize_shots(player_data: dict[str, Any]) -> list[dict[str, Any]]:
    """兼容不同玩家日志格式，统一到 shots 结构。"""
    raw_shots = player_data.get("shots")
    if isinstance(raw_shots, list):
        normalized = []
        for item in raw_shots:
            params = dict(item.get("params", {}))
            if "spot_size" not in params and "spot_size_set" in params:
                params["spot_size"] = params.get("spot_size_set")
            normalized.append(
                {
                    "id": item.get("id"),
                    "pos": item.get("pos", [None, None]),
                    "is_trial": bool(item.get("is_trial", False)),
                    "params": params,
                }
            )
        return normalized

    # 兼容 sample_data/player.json 使用的 actions 字段
    raw_actions = player_data.get("actions")
    if not isinstance(raw_actions, list):
        return []

    normalized = []
    for item in raw_actions:
        normalized.append(
            {
                "id": item.get("id"),
                "pos": item.get("pos", [None, None]),
                # actions 中没有 is_trial 时默认按有效光斑处理
                "is_trial": bool(item.get("is_trial", False)),
                "params": item.get("params", {}),
            }
        )
    return normalized


def _is_labelme_annotation(data: dict[str, Any]) -> bool:
    return isinstance(data.get("shapes"), list) and "target_zone" not in data


def _shape_label(shape: dict[str, Any]) -> str:
    return str(shape.get("label", "")).strip()


def _shape_points(shape: dict[str, Any]) -> list[list[float]]:
    points = shape.get("points", [])
    if not isinstance(points, list):
        return []
    out = []
    for p in points:
        if not isinstance(p, list) or len(p) < 2:
            continue
        out.append([float(p[0]), float(p[1])])
    return out


def _guess_before_json_path(after_json_path: str) -> str | None:
    folder = os.path.dirname(after_json_path)
    candidates = []
    for fn in os.listdir(folder):
        if not fn.endswith(".json"):
            continue
        if "_before_" in fn:
            candidates.append(os.path.join(folder, fn))
    return sorted(candidates)[0] if candidates else None


def _guess_vessel_mask_tar_path(after_json_path: str) -> str | None:
    folder = os.path.dirname(after_json_path)
    candidates = []
    for fn in os.listdir(folder):
        if fn.endswith(".tar"):
            candidates.append(os.path.join(folder, fn))
    return sorted(candidates)[0] if candidates else None


def _load_vessel_mask_from_tar(tar_path: str) -> np.ndarray | None:
    try:
        with tarfile.open(tar_path, "r") as tar:
            names = tar.getnames()
            npy_names = [n for n in names if n.endswith(".npy")]
            if not npy_names:
                return None
            raw = tar.extractfile(npy_names[0]).read()
            arr = np.load(BytesIO(raw))
            if not isinstance(arr, np.ndarray) or arr.ndim != 2:
                return None
            return arr
    except Exception:
        return None


def _point_hits_mask(mask: np.ndarray | None, x: float, y: float) -> bool:
    if mask is None:
        return False
    h, w = mask.shape[:2]
    xi = int(round(x))
    yi = int(round(y))
    if xi < 0 or yi < 0 or xi >= w or yi >= h:
        return False
    return bool(mask[yi, xi] > 0)


def _convert_labelme_to_question(question_json_path: str, question_data: dict[str, Any]) -> tuple[dict[str, Any], np.ndarray | None]:
    shapes = question_data.get("shapes", [])
    if not isinstance(shapes, list):
        raise ValueError("LabelMe question 的 shapes 字段缺失或格式错误")

    outer_boundary: list[list[float]] = []
    inner_holes: list[list[list[float]]] = []
    for shape in shapes:
        label = _shape_label(shape).lower()
        points = _shape_points(shape)
        if not points:
            continue
        if label == "gt_outer":
            outer_boundary = points
        elif label.startswith("gt_inner_"):
            inner_holes.append(points)

    if len(outer_boundary) < 3:
        raise ValueError("LabelMe question 中未找到有效的 gt_outer 多边形")

    danger_zones: list[dict[str, Any]] = []
    before_json_path = _guess_before_json_path(question_json_path)
    if before_json_path:
        before_data = _load_json(before_json_path)
        for shape in before_data.get("shapes", []):
            label = _shape_label(shape).lower()
            if label in {"optic", "macula", "fovea"}:
                points = _shape_points(shape)
                if len(points) >= 3:
                    danger_zones.append({"id": label, "polygon": points})

    vessel_mask = None
    tar_path = _guess_vessel_mask_tar_path(question_json_path)
    if tar_path:
        vessel_mask = _load_vessel_mask_from_tar(tar_path)

    converted = {
        "task_id": "",
        "target_zone": {
            "outer_boundary": outer_boundary,
            "inner_holes": inner_holes,
        },
        "danger_zones": danger_zones,
        "gt_parameters": {},
    }
    return converted, vessel_mask


def _count_holes(geom) -> int:
    if geom is None:
        return 0
    if geom.geom_type == "Polygon":
        return len(geom.interiors)
    if geom.geom_type == "MultiPolygon":
        return sum(len(p.interiors) for p in geom.geoms)
    return 0


def _best_concave_hull(points: list[tuple[float, float]], prefer_hole: bool, ratio_candidates: list[float]):
    candidates = []
    for ratio in ratio_candidates:
        geom = shapely.concave_hull(MultiPoint(points), ratio=ratio, allow_holes=True)
        if geom.is_valid and geom.area > 0:
            candidates.append((ratio, geom))
    if not candidates:
        return None

    if prefer_hole:
        with_hole = [(r, g) for r, g in candidates if _count_holes(g) >= 1]
        if with_hole:
            # 环形期望：优先 1 个孔洞，其次面积更大（覆盖更完整）
            with_hole.sort(key=lambda x: (abs(_count_holes(x[1]) - 1), -x[1].area))
            return with_hole[0][1]

    # 默认路径：取面积最大的有效凹包
    return max(candidates, key=lambda x: x[1].area)[1]


def _build_player_treatment_area(
    valid_shots: list[dict[str, Any]],
    ratio_candidates: list[float],
    inner_iqr_k: float,
    inner_ratio_limit: float,
    inner_abs_limit: int,
    min_outer_points: int,
):
    """
    基于玩家打点中心重建覆盖区域（Concave Hull, allow_holes=True）。
    修复点：
    1) 保持原 Concave Hull 主流程；
    2) 当检测到“疑似环形 + 少量内侧离群点”时，先剔除这些内侧点再重建，
       减少桥接长边把环形孔洞填死的问题。
    """
    points = []
    for shot in valid_shots:
        pos = shot.get("pos", [None, None])
        if not isinstance(pos, list) or len(pos) < 2:
            continue
        points.append((float(pos[0]), float(pos[1])))

    if not points:
        return None
    if len(points) == 1:
        return Point(points[0]).buffer(1.0)
    if len(points) == 2:
        return MultiPoint(points).convex_hull.buffer(1.0)

    # 先尝试全量点重建
    base_area = _best_concave_hull(points, prefer_hole=False, ratio_candidates=ratio_candidates)

    # 识别“少量内侧离群点”场景：这类点会把环形凹包桥接成实心
    arr = np.array(points, dtype=float)
    center = np.mean(arr, axis=0)
    radii = np.linalg.norm(arr - center, axis=1)
    q25 = float(np.percentile(radii, 25))
    q75 = float(np.percentile(radii, 75))
    iqr = max(q75 - q25, 1e-6)
    # 内点过滤阈值：k 越大过滤越弱
    inner_cut = q25 - inner_iqr_k * iqr
    inner_mask = radii < inner_cut
    inner_count = int(np.sum(inner_mask))
    n = len(points)
    # 仅当内点占比较低时触发过滤，避免过度修剪
    likely_ring_with_inner_outliers = (
        0 < inner_count <= max(inner_abs_limit, int(inner_ratio_limit * n))
        and (n - inner_count) >= min_outer_points
    )

    if likely_ring_with_inner_outliers:
        outer_points = [pt for idx, pt in enumerate(points) if not inner_mask[idx]]
        repaired_area = _best_concave_hull(outer_points, prefer_hole=True, ratio_candidates=ratio_candidates)
        if repaired_area is not None and _count_holes(repaired_area) >= 1:
            return repaired_area

    if base_area is not None:
        return base_area

    # 兜底为凸包，确保评分流程不中断
    fallback = MultiPoint(points).convex_hull
    return fallback if fallback.is_valid and fallback.area > 0 else None


def _resolve_base_image_path(question_json_path: str, question_data: dict[str, Any]) -> str | None:
    # Temp 样本优先：simgt.json 同名 png（after 图）
    sibling_png = os.path.splitext(question_json_path)[0] + ".png"
    if os.path.exists(sibling_png):
        return sibling_png

    image_path = question_data.get("imagePath")
    if isinstance(image_path, str) and image_path:
        if os.path.isabs(image_path) and os.path.exists(image_path):
            return image_path
        candidate = os.path.join(os.path.dirname(question_json_path), image_path)
        if os.path.exists(candidate):
            return candidate

    preop_path = question_data.get("preop_image_path")
    if isinstance(preop_path, str) and preop_path:
        if os.path.isabs(preop_path) and os.path.exists(preop_path):
            return preop_path
        candidate = os.path.join(os.path.dirname(question_json_path), preop_path)
        if os.path.exists(candidate):
            return candidate

    folder = os.path.dirname(question_json_path)
    pngs = [fn for fn in os.listdir(folder) if fn.lower().endswith(".png")]
    preferred_after = [fn for fn in pngs if "_after_" in fn]
    if preferred_after:
        return os.path.join(folder, sorted(preferred_after)[0])
    return os.path.join(folder, sorted(pngs)[0]) if pngs else None


def _resolve_player_image_path(player_json_path: str) -> str | None:
    sibling_png = os.path.splitext(player_json_path)[0] + ".png"
    if os.path.exists(sibling_png):
        return sibling_png
    return None


def _iter_polygons(geom):
    if geom is None:
        return
    if isinstance(geom, Polygon):
        yield geom
        return
    if geom.geom_type == "MultiPolygon":
        for p in geom.geoms:
            yield p


def _draw_shapely_polygon(draw: ImageDraw.ImageDraw, polygon: Polygon, fill: tuple[int, int, int, int], outline: tuple[int, int, int, int]) -> None:
    ext = [(float(x), float(y)) for x, y in polygon.exterior.coords]
    draw.polygon(ext, fill=fill, outline=outline, width=2)
    for hole in polygon.interiors:
        pts = [(float(x), float(y)) for x, y in hole.coords]
        draw.polygon(pts, fill=(0, 0, 0, 0), outline=outline, width=1)


def _draw_legend(draw: ImageDraw.ImageDraw, show_player: bool, show_gt: bool) -> None:
    x0, y0 = 20, 20
    line_h = 24
    pad = 10
    items = []
    if show_player:
        items.append(("Player: 橙色区域+橙色点", (255, 90, 0, 255)))
    if show_gt:
        items.append(("GT: 绿色区域", (20, 150, 60, 255)))
    if not items:
        return
    box_w = 320
    box_h = pad * 2 + line_h * len(items)
    draw.rectangle((x0, y0, x0 + box_w, y0 + box_h), fill=(0, 0, 0, 140), outline=(255, 255, 255, 180), width=1)
    for i, (text, color) in enumerate(items):
        yy = y0 + pad + i * line_h
        draw.rectangle((x0 + 10, yy + 4, x0 + 24, yy + 18), fill=color, outline=(255, 255, 255, 220), width=1)
        draw.text((x0 + 34, yy), text, fill=(255, 255, 255, 255))


def _draw_player_layer(draw: ImageDraw.ImageDraw, player_area, valid_shots: list[dict[str, Any]]) -> None:
    for poly in _iter_polygons(player_area):
        _draw_shapely_polygon(draw, poly, fill=(255, 140, 40, 90), outline=(255, 90, 0, 230))
    for shot in valid_shots:
        pos = shot.get("pos", [None, None])
        if not isinstance(pos, list) or len(pos) < 2:
            continue
        x = float(pos[0])
        y = float(pos[1])
        r = 3.0
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 90, 0, 255), outline=(255, 90, 0, 255))


def _draw_gt_layer(draw: ImageDraw.ImageDraw, target_poly) -> None:
    for poly in _iter_polygons(target_poly):
        _draw_shapely_polygon(draw, poly, fill=(30, 200, 80, 80), outline=(20, 150, 60, 220))


def _save_overlay_visualization(
    base_image_path: str | None,
    target_poly,
    player_area,
    valid_shots: list[dict[str, Any]],
    output_json_path: str,
) -> dict[str, str]:
    if not base_image_path or not os.path.exists(base_image_path):
        return {}
    if target_poly is None and player_area is None:
        return {}

    stem = os.path.splitext(output_json_path)[0]
    output_paths = {
        "player_only": stem + "_player_overlay.png",
        "gt_only": stem + "_gt_overlay.png",
        "combined": stem + "_combined_overlay.png",
    }

    base_img = Image.open(base_image_path).convert("RGBA")

    # 1) Player only
    player_overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    player_draw = ImageDraw.Draw(player_overlay, "RGBA")
    _draw_player_layer(player_draw, player_area, valid_shots)
    _draw_legend(player_draw, show_player=True, show_gt=False)
    Image.alpha_composite(base_img, player_overlay).save(output_paths["player_only"])

    # 2) GT only
    gt_overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    gt_draw = ImageDraw.Draw(gt_overlay, "RGBA")
    _draw_gt_layer(gt_draw, target_poly)
    _draw_legend(gt_draw, show_player=False, show_gt=True)
    Image.alpha_composite(base_img, gt_overlay).save(output_paths["gt_only"])

    # 3) Combined
    combined_overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    combined_draw = ImageDraw.Draw(combined_overlay, "RGBA")
    _draw_gt_layer(combined_draw, target_poly)
    _draw_player_layer(combined_draw, player_area, valid_shots)
    _draw_legend(combined_draw, show_player=True, show_gt=True)
    Image.alpha_composite(base_img, combined_overlay).save(output_paths["combined"])
    return output_paths


def _param_value(params: dict[str, Any], key: str) -> float:
    if key == "spot_size":
        return float(params.get("spot_size", params.get("spot_size_set", 0.0)))
    return float(params.get(key, 0.0))


def _image_size_from_context(base_image_path: str | None, geoms: list[Any]) -> tuple[int, int]:
    if base_image_path and os.path.exists(base_image_path):
        with Image.open(base_image_path) as img:
            return img.size

    max_x = 1.0
    max_y = 1.0
    for geom in geoms:
        if geom is None:
            continue
        minx, miny, gx, gy = geom.bounds
        max_x = max(max_x, gx)
        max_y = max(max_y, gy)
    return int(math.ceil(max_x)) + 10, int(math.ceil(max_y)) + 10


def _rasterize_geom_crop(geom, bbox: tuple[int, int, int, int]) -> np.ndarray:
    minx, miny, maxx, maxy = bbox
    width = maxx - minx + 1
    height = maxy - miny + 1
    mask_img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask_img)
    for poly in _iter_polygons(geom):
        ext = [(float(x) - minx, float(y) - miny) for x, y in poly.exterior.coords]
        draw.polygon(ext, fill=255)
        for hole in poly.interiors:
            pts = [(float(x) - minx, float(y) - miny) for x, y in hole.coords]
            draw.polygon(pts, fill=0)
    return np.array(mask_img, dtype=np.uint8) > 0


def _valid_param_shots(shots: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    out = []
    for shot in shots:
        pos = shot.get("pos", [None, None])
        params = shot.get("params", {})
        if not isinstance(pos, list) or len(pos) < 2:
            continue
        try:
            _param_value(params, key)
            float(pos[0])
            float(pos[1])
        except (TypeError, ValueError):
            continue
        out.append(shot)
    return out


def _build_continuous_param_field(
    shots: list[dict[str, Any]],
    key: str,
    bbox: tuple[int, int, int, int],
    mask: np.ndarray,
    sigma_px: float,
) -> np.ndarray:
    minx, miny, maxx, maxy = bbox
    yy, xx = np.mgrid[miny : maxy + 1, minx : maxx + 1]
    sum_w = np.zeros(mask.shape, dtype=float)
    sum_v = np.zeros(mask.shape, dtype=float)
    sigma_sq = max(sigma_px, 1e-6) ** 2

    for shot in _valid_param_shots(shots, key):
        x, y = float(shot["pos"][0]), float(shot["pos"][1])
        value = _param_value(shot.get("params", {}), key)
        dist_sq = (xx - x) ** 2 + (yy - y) ** 2
        weight = np.exp(-dist_sq / (2.0 * sigma_sq))
        sum_w += weight
        sum_v += weight * value

    field = np.full(mask.shape, np.nan, dtype=float)
    valid = mask & (sum_w > 1e-9)
    field[valid] = sum_v[valid] / sum_w[valid]
    return field


def _build_nearest_param_field(
    shots: list[dict[str, Any]],
    key: str,
    bbox: tuple[int, int, int, int],
    mask: np.ndarray,
) -> np.ndarray:
    minx, miny, maxx, maxy = bbox
    yy, xx = np.mgrid[miny : maxy + 1, minx : maxx + 1]
    best_dist = np.full(mask.shape, np.inf, dtype=float)
    field = np.full(mask.shape, np.nan, dtype=float)

    for shot in _valid_param_shots(shots, key):
        x, y = float(shot["pos"][0]), float(shot["pos"][1])
        value = _param_value(shot.get("params", {}), key)
        dist_sq = (xx - x) ** 2 + (yy - y) ** 2
        update = mask & (dist_sq < best_dist)
        best_dist[update] = dist_sq[update]
        field[update] = value
    return field


def _blend_rgba(base: tuple[int, int, int, int], overlay: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    alpha = overlay[3] / 255.0
    return (
        int(base[0] * (1 - alpha) + overlay[0] * alpha),
        int(base[1] * (1 - alpha) + overlay[1] * alpha),
        int(base[2] * (1 - alpha) + overlay[2] * alpha),
        255,
    )


def _lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _heat_color(t: float, error_mode: bool) -> tuple[int, int, int, int]:
    t = max(0.0, min(1.0, t))
    if error_mode:
        stops = [
            (0.0, (40, 180, 80)),
            (0.35, (245, 215, 65)),
            (0.65, (245, 135, 35)),
            (1.0, (220, 40, 35)),
        ]
    else:
        stops = [
            (0.0, (45, 90, 210)),
            (0.35, (40, 190, 210)),
            (0.70, (245, 215, 70)),
            (1.0, (220, 45, 35)),
        ]
    for idx in range(len(stops) - 1):
        left_t, left_c = stops[idx]
        right_t, right_c = stops[idx + 1]
        if left_t <= t <= right_t:
            return (*_lerp_color(left_c, right_c, (t - left_t) / (right_t - left_t)), 165)
    return (*stops[-1][1], 165)


def _save_field_heatmap(
    base_image_path: str | None,
    image_size: tuple[int, int],
    field: np.ndarray,
    bbox: tuple[int, int, int, int],
    output_path: str,
    vmin: float,
    vmax: float,
    error_mode: bool,
) -> str:
    if base_image_path and os.path.exists(base_image_path):
        base_img = Image.open(base_image_path).convert("RGBA")
    else:
        base_img = Image.new("RGBA", image_size, (20, 20, 20, 255))

    overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    pix = overlay.load()
    minx, miny, _, _ = bbox
    denom = max(vmax - vmin, 1e-9)

    for row in range(field.shape[0]):
        for col in range(field.shape[1]):
            value = field[row, col]
            if np.isnan(value):
                continue
            pix[minx + col, miny + row] = _heat_color((float(value) - vmin) / denom, error_mode)

    combined = Image.alpha_composite(base_img, overlay)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    combined.save(output_path)
    return output_path


def _main_error_regions(error_field: np.ndarray, bbox: tuple[int, int, int, int], label: str) -> list[str]:
    valid = ~np.isnan(error_field)
    if not np.any(valid):
        return []
    high = valid & (error_field >= 0.6)
    if not np.any(high):
        return []

    rows, cols = np.where(high)
    minx, miny, maxx, maxy = bbox
    cx = minx + float(np.mean(cols))
    cy = miny + float(np.mean(rows))
    midx = (minx + maxx) / 2.0
    midy = (miny + maxy) / 2.0
    vertical = "上方" if cy < midy else "下方"
    horizontal = "左侧" if cx < midx else "右侧"
    return [f"{vertical}{horizontal}{label}偏差较高"]


def _score_param_field(error_field: np.ndarray, max_score: float) -> tuple[float, float]:
    valid = ~np.isnan(error_field)
    if not np.any(valid):
        return 0.0, 1.0
    mean_error = float(np.mean(error_field[valid]))
    return max_score * (1.0 - mean_error), mean_error


def _score_spatial_parameters(
    gt_shots: list[dict[str, Any]],
    player_shots: list[dict[str, Any]],
    scoring_geom,
    base_image_path: str | None,
    output_json_path: str,
    tolerance_abs: dict[str, float],
    field_sigma_px: float,
) -> tuple[float, dict[str, Any], dict[str, str]]:
    if scoring_geom is None or scoring_geom.area <= 0:
        empty_subscores = {}
        for key, max_score in {"power": 11.0, "spot_size": 8.0, "exposure_time": 8.0, "wavelength": 8.0}.items():
            empty_subscores[key] = {
                "score": 0.0,
                "max_score": max_score,
                "mean_error": 1.0,
                "main_error_regions": ["无有效评分区域"],
            }
        return 0.0, empty_subscores, {}

    image_size = _image_size_from_context(base_image_path, [scoring_geom])
    width, height = image_size
    minx, miny, maxx, maxy = scoring_geom.bounds
    bbox = (
        max(0, int(math.floor(minx))),
        max(0, int(math.floor(miny))),
        min(width - 1, int(math.ceil(maxx))),
        min(height - 1, int(math.ceil(maxy))),
    )
    mask = _rasterize_geom_crop(scoring_geom, bbox)
    heatmap_dir = os.path.join(os.path.dirname(os.path.abspath(output_json_path)), "heatmaps")

    field_pairs: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    error_fields: dict[str, np.ndarray] = {}
    sub_scores: dict[str, Any] = {}
    param_specs = {
        "power": ("power", 11.0, "功率"),
        "spot_size": ("spot_size", 8.0, "光斑大小"),
        "exposure_time": ("exposure_time", 8.0, "曝光时间"),
    }

    for key, (field_key, max_score, cn_label) in param_specs.items():
        gt_field = _build_continuous_param_field(gt_shots, field_key, bbox, mask, field_sigma_px)
        player_field = _build_continuous_param_field(player_shots, field_key, bbox, mask, field_sigma_px)
        valid = mask & ~np.isnan(gt_field) & ~np.isnan(player_field)
        error = np.full(mask.shape, np.nan, dtype=float)
        tol = max(float(tolerance_abs.get(key, 1.0)), 1e-6)
        error[valid] = np.minimum(1.0, np.abs(player_field[valid] - gt_field[valid]) / tol)
        score, mean_error = _score_param_field(error, max_score)

        field_pairs[key] = (gt_field, player_field)
        error_fields[key] = error
        sub_scores[key] = {
            "score": round(score, 2),
            "max_score": max_score,
            "mean_error": round(mean_error, 4),
            "main_error_regions": _main_error_regions(error, bbox, cn_label),
        }

    gt_wave = _build_nearest_param_field(gt_shots, "wavelength", bbox, mask)
    player_wave = _build_nearest_param_field(player_shots, "wavelength", bbox, mask)
    wave_valid = mask & ~np.isnan(gt_wave) & ~np.isnan(player_wave)
    wave_error = np.full(mask.shape, np.nan, dtype=float)
    wave_error[wave_valid] = (gt_wave[wave_valid] != player_wave[wave_valid]).astype(float)
    wave_score, wave_mean_error = _score_param_field(wave_error, 8.0)
    field_pairs["wavelength"] = (gt_wave, player_wave)
    error_fields["wavelength"] = wave_error
    sub_scores["wavelength"] = {
        "score": round(wave_score, 2),
        "max_score": 8.0,
        "mean_error": round(wave_mean_error, 4),
        "main_error_regions": _main_error_regions(wave_error, bbox, "波长"),
    }

    total_error = np.full(mask.shape, np.nan, dtype=float)
    weighted_sum = np.zeros(mask.shape, dtype=float)
    valid_any = np.zeros(mask.shape, dtype=bool)
    weights = {"power": 11.0 / 35.0, "spot_size": 8.0 / 35.0, "exposure_time": 8.0 / 35.0, "wavelength": 8.0 / 35.0}
    for key, weight in weights.items():
        err = error_fields[key]
        valid = ~np.isnan(err)
        weighted_sum[valid] += err[valid] * weight
        valid_any |= valid
    total_error[valid_any] = weighted_sum[valid_any]

    visualization: dict[str, str] = {}
    filename_map = {
        "power": ("gt_power_heatmap", "player_power_heatmap", "error_power_heatmap"),
        "spot_size": ("gt_spot_size_heatmap", "player_spot_size_heatmap", "error_spot_size_heatmap"),
        "exposure_time": ("gt_exposure_time_heatmap", "player_exposure_time_heatmap", "error_exposure_time_heatmap"),
        "wavelength": ("gt_wavelength_map", "player_wavelength_map", "error_wavelength_map"),
    }

    for key, (gt_name, player_name, error_name) in filename_map.items():
        gt_field, player_field = field_pairs[key]
        raw_values = np.concatenate([gt_field[~np.isnan(gt_field)], player_field[~np.isnan(player_field)]])
        if raw_values.size == 0:
            raw_min, raw_max = 0.0, 1.0
        else:
            raw_min, raw_max = float(np.min(raw_values)), float(np.max(raw_values))
            if raw_min == raw_max:
                raw_max = raw_min + 1.0
        visualization[gt_name] = _save_field_heatmap(
            base_image_path, image_size, gt_field, bbox, os.path.join(heatmap_dir, f"{gt_name}.png"), raw_min, raw_max, False
        )
        visualization[player_name] = _save_field_heatmap(
            base_image_path, image_size, player_field, bbox, os.path.join(heatmap_dir, f"{player_name}.png"), raw_min, raw_max, False
        )
        visualization[error_name] = _save_field_heatmap(
            base_image_path, image_size, error_fields[key], bbox, os.path.join(heatmap_dir, f"{error_name}.png"), 0.0, 1.0, True
        )

    visualization["total_error_heatmap"] = _save_field_heatmap(
        base_image_path,
        image_size,
        total_error,
        bbox,
        os.path.join(heatmap_dir, "error_total_heatmap.png"),
        0.0,
        1.0,
        True,
    )

    total_score = sum(float(item["score"]) for item in sub_scores.values())
    return total_score, sub_scores, visualization


def _spot_diameter_in_px(params: dict[str, Any], spot_um_to_px: float) -> float:
    spot_px = params.get("spot_size_px")
    if spot_px is not None:
        return max(0.0, float(spot_px))

    spot = float(params.get("spot_size", 0.0))
    if spot <= 0:
        return 0.0
    # 约定：大于 50 的 spot_size 按 um 解释并转换；否则按像素值直用
    return spot * spot_um_to_px if spot > 50.0 else spot


def evaluate(
    question_json_path: str,
    player_json_path: str,
    scoring_output_json_path: str,
    config_json_path: str | None = None,
) -> tuple[int, str]:
    """供游戏调用的统一评估入口。"""
    try:
        # 1) 读取输入与配置
        question_data = _load_json(question_json_path)
        player_data = _load_json(player_json_path)
        vessel_mask = None
        if _is_labelme_annotation(question_data):
            question_data, vessel_mask = _convert_labelme_to_question(question_json_path, question_data)

        if not config_json_path:
            config_json_path = os.path.join(os.path.dirname(question_json_path), "config.json")
        config_data = _load_json(config_json_path)

        scoring_policy = config_data.get("scoring_policy", {})
        spacing_th = scoring_policy.get("spacing_thresholds", {})
        penalty_rules = scoring_policy.get("penalty_rules", {})
        area_rebuild = scoring_policy.get("player_area_rebuild", {})
        param_tolerance_abs = scoring_policy.get("param_tolerance_abs", {})
        field_generation = scoring_policy.get("spatial_parameter_field", {})

        sigma_good_sq = float(spacing_th.get("sigma_good_sq", 25.0))
        sigma_max_sq = float(spacing_th.get("sigma_max_sq", 100.0))
        r_excellent = float(spacing_th.get("r_value_excellent", 1.2))
        r_pass = float(spacing_th.get("r_value_pass", 0.8))
        points_per_overlap = float(penalty_rules.get("points_per_overlap", 1.0))
        spot_um_to_px = float(penalty_rules.get("spot_size_um_to_px", 0.03))
        overlap_ratio = float(penalty_rules.get("overlap_distance_ratio", 1.0))
        field_sigma_px = float(field_generation.get("field_sigma_px", 25.0))
        dim2_tolerance_abs = {
            "power": float(param_tolerance_abs.get("power", 25.0)),
            "spot_size": float(param_tolerance_abs.get("spot_size", 30.0)),
            "exposure_time": float(param_tolerance_abs.get("exposure_time", 10.0)),
        }

        raw_ratio_candidates = area_rebuild.get("ratio_candidates", [0.35, 0.30, 0.25, 0.20, 0.15, 0.10])
        if not isinstance(raw_ratio_candidates, list):
            raise ValueError("player_area_rebuild.ratio_candidates 必须是数组")
        ratio_candidates = [float(v) for v in raw_ratio_candidates if 0.0 < float(v) <= 1.0]
        if not ratio_candidates:
            raise ValueError("player_area_rebuild.ratio_candidates 不能为空，且元素需在 (0, 1] 范围")
        inner_iqr_k = float(area_rebuild.get("inner_iqr_k", 0.75))
        inner_ratio_limit = float(area_rebuild.get("inner_ratio_limit", 0.20))
        inner_abs_limit = int(area_rebuild.get("inner_abs_limit", 3))
        min_outer_points = int(area_rebuild.get("min_outer_points", 8))

        # 2) 基础数据抽取
        all_shots = _normalize_shots(player_data)
        if not isinstance(all_shots, list):
            raise ValueError("player.shots 必须是数组")
        valid_shots = [s for s in all_shots if not s.get("is_trial", False)]
        gt_all_shots = _normalize_shots(question_data)
        gt_valid_shots = [s for s in gt_all_shots if not s.get("is_trial", False)]

        target_zone = question_data.get("target_zone", {})
        target_poly = _safe_polygon(
            target_zone.get("outer_boundary", []),
            target_zone.get("inner_holes", []),
        )
        if target_poly is None and gt_valid_shots:
            target_poly = _build_player_treatment_area(
                valid_shots=gt_valid_shots,
                ratio_candidates=ratio_candidates,
                inner_iqr_k=inner_iqr_k,
                inner_ratio_limit=inner_ratio_limit,
                inner_abs_limit=inner_abs_limit,
                min_outer_points=min_outer_points,
            )

        # 3) 危险区检测与附加惩罚统计
        is_fatal_error = False
        fatal_error_reason = None
        vessel_hit_count = 0
        overlap_count = 0

        danger_polygons: list[tuple[str, Polygon]] = []
        for zone in question_data.get("danger_zones", []):
            zone_id = str(zone.get("id", ""))
            poly = _safe_polygon(zone.get("polygon", []))
            if poly:
                danger_polygons.append((zone_id, poly))

        for i, shot in enumerate(all_shots):
            pos = shot.get("pos", [None, None])
            if not isinstance(pos, list) or len(pos) < 2:
                continue
            point = Point(float(pos[0]), float(pos[1]))

            for zone_id, zone_poly in danger_polygons:
                if not zone_poly.contains(point):
                    continue
                zone_id_lower = zone_id.lower()
                if (
                    "macula" in zone_id_lower
                    or "fovea" in zone_id_lower
                    or "optic" in zone_id_lower
                    or "黄斑" in zone_id
                    or "视盘" in zone_id
                ):
                    is_fatal_error = True
                    fatal_error_reason = f"触发严重医疗事故：光斑打入危险区({zone_id})"
                elif "vessel" in zone_id_lower or "血管" in zone_id:
                    vessel_hit_count += 1
            if _point_hits_mask(vessel_mask, float(pos[0]), float(pos[1])):
                vessel_hit_count += 1

            # 重叠按光斑中心距离是否小于平均直径统计
            shot_params = shot.get("params", {})
            d1_px = _spot_diameter_in_px(shot_params, spot_um_to_px)
            for j in range(i + 1, len(all_shots)):
                shot2 = all_shots[j]
                pos2 = shot2.get("pos", [None, None])
                if not isinstance(pos2, list) or len(pos2) < 2:
                    continue
                d2_px = _spot_diameter_in_px(shot2.get("params", {}), spot_um_to_px)
                dist = float(np.linalg.norm(np.array(pos, dtype=float) - np.array(pos2, dtype=float)))
                if dist < ((d1_px + d2_px) / 2.0) * overlap_ratio:
                    overlap_count += 1

        # 4) 维度一：位置与范围（IoU）
        iou = 0.0
        dim1_score = 0.0
        player_area = None
        if target_poly is not None and len(valid_shots) >= 1:
            player_area = _build_player_treatment_area(
                valid_shots=valid_shots,
                ratio_candidates=ratio_candidates,
                inner_iqr_k=inner_iqr_k,
                inner_ratio_limit=inner_ratio_limit,
                inner_abs_limit=inner_abs_limit,
                min_outer_points=min_outer_points,
            )
            if player_area is not None:
                inter_area = player_area.intersection(target_poly).area
                union_area = player_area.union(target_poly).area
                if union_area > 0:
                    iou = inter_area / union_area

        if iou >= 0.85:
            dim1_score = 35.0
            dim1_eval_msg = "靶区覆盖完整，越界控制良好。"
        elif iou >= 0.50:
            dim1_score = 17.5 + ((iou - 0.50) / 0.35) * 17.5
            dim1_eval_msg = "靶区覆盖基本完成，但仍存在漏打或越界。"
        else:
            dim1_score = 0.0
            dim1_eval_msg = "覆盖不足，存在明显漏打或偏离靶区。"

        base_image_path = _resolve_base_image_path(question_json_path, question_data)
        heatmap_base_image_path = _resolve_player_image_path(player_json_path) or base_image_path

        # 5) 维度二：激光参数空间适配度
        scoring_region = target_poly.intersection(player_area) if target_poly is not None and player_area is not None else None
        dim2_score, dim2_sub_scores, dim2_visualization = _score_spatial_parameters(
            gt_shots=gt_valid_shots,
            player_shots=valid_shots,
            scoring_geom=scoring_region,
            base_image_path=heatmap_base_image_path,
            output_json_path=scoring_output_json_path,
            tolerance_abs=dim2_tolerance_abs,
            field_sigma_px=field_sigma_px,
        )
        dim2_eval_msg = "已完成 GT 与玩家参数空间场对比，可结合热力图定位局部参数偏差。"

        # 6) 维度三：密度与均匀度
        r_value = 0.0
        spacing_variance = 0.0
        r_score = 0.0
        spacing_score = 0.0

        n = len(valid_shots)
        area = target_poly.area if target_poly is not None else 0.0
        if n >= 2 and area > 0:
            pts = np.array([[float(s["pos"][0]), float(s["pos"][1])] for s in valid_shots], dtype=float)
            delta = pts[:, np.newaxis, :] - pts[np.newaxis, :, :]
            dist_matrix = np.sqrt(np.sum(delta * delta, axis=2))
            np.fill_diagonal(dist_matrix, np.inf)
            min_dists = np.min(dist_matrix, axis=1)

            r1 = float(np.mean(min_dists))
            density = n / area
            r_expected = 1.0 / (2.0 * math.sqrt(density)) if density > 0 else 0.0
            if r_expected > 0:
                r_value = r1 / r_expected

            if r_value > r_excellent:
                r_score = 15.0
            elif r_value >= r_pass:
                r_score = 8.0
            else:
                r_score = 0.0

            spacing_variance = float(np.var(min_dists, ddof=1))
            if spacing_variance <= sigma_good_sq:
                spacing_score = 15.0
            elif spacing_variance <= sigma_max_sq and sigma_max_sq > sigma_good_sq:
                spacing_score = 15.0 * (
                    (sigma_max_sq - spacing_variance) / (sigma_max_sq - sigma_good_sq)
                )
            else:
                spacing_score = 0.0

        dim3_score = r_score + spacing_score
        dim3_eval_msg = "已完成密度和间距稳定性评估。"

        # 7) 惩罚与总分
        overlap_deduct = overlap_count * points_per_overlap
        vessel_deduct = vessel_hit_count * 5.0
        total_score = dim1_score + dim2_score + dim3_score - overlap_deduct - vessel_deduct
        total_score = max(0.0, total_score)

        # 红线触发时按一票否决处理
        if is_fatal_error:
            total_score = 0.0

        vis_paths = _save_overlay_visualization(
            base_image_path=base_image_path,
            target_poly=target_poly,
            player_area=player_area,
            valid_shots=valid_shots,
            output_json_path=scoring_output_json_path,
        )

        output_data = {
            "session_id": player_data.get("session_id", ""),
            "_session_id": "关联的玩家操作会话ID",
            "task_id": question_data.get("task_id", "") or player_data.get("task_id", ""),
            "_task_id": "关联的题目ID",
            "is_fatal_error": is_fatal_error,
            "_is_fatal_error": "是否触发医疗事故红线（一票否决）",
            "fatal_error_reason": fatal_error_reason,
            "_fatal_error_reason": "红线失败原因，例如：打到黄斑中心凹",
            "debug_visualization_paths": vis_paths,
            "_debug_visualization_paths": "可视化图路径：player_only / gt_only / combined",
            "debug_visualization_path": vis_paths.get("combined"),
            "_debug_visualization_path": "combined 可视化图路径（兼容字段）",
            "total_score": round(total_score, 2),
            "_total_score": "最终总分（百分制，扣除所有惩罚项后）",
            "dimensions": {
                "dim1_position": {
                    "score": round(dim1_score, 2),
                    "max_score": 35.0,
                    "iou": round(iou, 4),
                    "_iou": "玩家实际治疗面积与标准靶区的交并比",
                    "eval_msg": dim1_eval_msg,
                },
                "dim2_energy": {
                    "name": "激光参数空间适配度",
                    "score": round(dim2_score, 2),
                    "max_score": 35.0,
                    "scoring_region": "intersection_of_target_and_player_area",
                    "sub_scores": dim2_sub_scores,
                    "visualization": dim2_visualization,
                    "eval_msg": dim2_eval_msg,
                },
                "dim3_density": {
                    "score": round(dim3_score, 2),
                    "max_score": 30.0,
                    "sub_scores": {
                        "r_value": {
                            "score": round(r_score, 2),
                            "max_score": 15.0,
                            "value": round(r_value, 4),
                            "_value": "最近邻离散指数R，>1.2为优",
                        },
                        "spacing_variance": {
                            "score": round(spacing_score, 2),
                            "max_score": 15.0,
                            "value": round(spacing_variance, 4),
                            "_value": "光斑间距方差，越小手越稳",
                        },
                    },
                    "eval_msg": dim3_eval_msg,
                },
            },
            "penalties": {
                "overlap_penalty": {
                    "count": overlap_count,
                    "deducted_points": round(overlap_deduct, 2),
                    "_desc": "光斑物理重叠次数及扣分",
                },
                "vessel_hit_penalty": {
                    "count": vessel_hit_count,
                    "deducted_points": round(vessel_deduct, 2),
                    "_desc": "触碰视网膜大血管次数及扣分（每处扣5分，从维1中扣除，此处仅作记录和最终汇总扣除）",
                },
            },
        }

        # 先确保目录存在，再写文件；写完即视为成功
        os.makedirs(os.path.dirname(os.path.abspath(scoring_output_json_path)), exist_ok=True)
        with open(scoring_output_json_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        return 1, "success"
    except Exception:
        return 0, f"评估计算过程发生异常：\n{traceback.format_exc()}"
