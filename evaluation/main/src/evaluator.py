import json
import math
import os
import traceback
from typing import Any

import numpy as np
import shapely
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
        return raw_shots

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


def _build_player_treatment_area(valid_shots: list[dict[str, Any]]):
    """
    基于玩家打点中心重建覆盖区域（不直接使用 spot_size 的物理单位）。
    使用 concave hull 且允许内部空洞，以支持环形靶区。
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
        # 两点时退化为细长区域，避免出现零面积线段
        return MultiPoint(points).convex_hull.buffer(1.0)

    # ratio 越小越贴点集边界；下调到 0.3 以减少区域外扩
    area = shapely.concave_hull(MultiPoint(points), ratio=0.3, allow_holes=True)
    if area.is_valid and area.area > 0:
        return area

    # 兜底为凸包，确保评分流程不中断
    fallback = MultiPoint(points).convex_hull
    return fallback if fallback.is_valid and fallback.area > 0 else None


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
        if not config_json_path:
            config_json_path = os.path.join(os.path.dirname(question_json_path), "config.json")
        config_data = _load_json(config_json_path)

        scoring_policy = config_data.get("scoring_policy", {})
        param_tol = scoring_policy.get("param_tolerance_tau", {})
        spacing_th = scoring_policy.get("spacing_thresholds", {})
        penalty_rules = scoring_policy.get("penalty_rules", {})

        tau_power = float(param_tol.get("power", 0.20))
        tau_spot = float(param_tol.get("spot_size", 0.15))
        tau_time = float(param_tol.get("exposure_time", 0.25))
        tau_wave = float(param_tol.get("wavelength", 0.10))
        sigma_good_sq = float(spacing_th.get("sigma_good_sq", 25.0))
        sigma_max_sq = float(spacing_th.get("sigma_max_sq", 100.0))
        r_excellent = float(spacing_th.get("r_value_excellent", 1.2))
        r_pass = float(spacing_th.get("r_value_pass", 0.8))
        points_per_overlap = float(penalty_rules.get("points_per_overlap", 1.0))

        # 2) 基础数据抽取
        all_shots = _normalize_shots(player_data)
        if not isinstance(all_shots, list):
            raise ValueError("player.shots 必须是数组")
        valid_shots = [s for s in all_shots if not s.get("is_trial", False)]

        target_zone = question_data.get("target_zone", {})
        target_poly = _safe_polygon(
            target_zone.get("outer_boundary", []),
            target_zone.get("inner_holes", []),
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

            # 重叠按光斑中心距离是否小于平均直径统计
            shot_params = shot.get("params", {})
            d1 = float(shot_params.get("spot_size", 0.0))
            for j in range(i + 1, len(all_shots)):
                shot2 = all_shots[j]
                pos2 = shot2.get("pos", [None, None])
                if not isinstance(pos2, list) or len(pos2) < 2:
                    continue
                d2 = float(shot2.get("params", {}).get("spot_size", 0.0))
                dist = float(np.linalg.norm(np.array(pos, dtype=float) - np.array(pos2, dtype=float)))
                if dist < (d1 + d2) / 2.0:
                    overlap_count += 1

        # 4) 维度一：位置与范围（IoU）
        iou = 0.0
        dim1_score = 0.0
        if target_poly is not None and len(valid_shots) >= 1:
            player_area = _build_player_treatment_area(valid_shots)
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

        # 5) 维度二：强度与能量
        gt = question_data.get("gt_parameters", {})
        gt_power = float(gt.get("power", 200.0))
        gt_spot = float(gt.get("spot_size", 200.0))
        gt_time = float(gt.get("exposure_time", 100.0))
        gt_wave = float(gt.get("wavelength", 532.0))

        if valid_shots:
            avg_power = float(np.mean([float(s.get("params", {}).get("power", 0.0)) for s in valid_shots]))
            avg_spot = float(np.mean([float(s.get("params", {}).get("spot_size", 0.0)) for s in valid_shots]))
            avg_time = float(np.mean([float(s.get("params", {}).get("exposure_time", 0.0)) for s in valid_shots]))
            avg_wave = float(np.mean([float(s.get("params", {}).get("wavelength", 0.0)) for s in valid_shots]))
        else:
            avg_power, avg_spot, avg_time, avg_wave = 0.0, 0.0, 0.0, 0.0

        s_power, e_power = _param_score(avg_power, gt_power, tau_power, 11.0)
        s_spot, e_spot = _param_score(avg_spot, gt_spot, tau_spot, 8.0)
        s_time, e_time = _param_score(avg_time, gt_time, tau_time, 8.0)
        s_wave, e_wave = _param_score(avg_wave, gt_wave, tau_wave, 8.0)
        dim2_score = s_power + s_spot + s_time + s_wave
        dim2_eval_msg = "已完成参数偏差计算，可根据子项进行针对性训练。"

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

        output_data = {
            "session_id": player_data.get("session_id", ""),
            "_session_id": "关联的玩家操作会话ID",
            "task_id": question_data.get("task_id", ""),
            "_task_id": "关联的题目ID",
            "is_fatal_error": is_fatal_error,
            "_is_fatal_error": "是否触发医疗事故红线（一票否决）",
            "fatal_error_reason": fatal_error_reason,
            "_fatal_error_reason": "红线失败原因，例如：打到黄斑中心凹",
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
                    "score": round(dim2_score, 2),
                    "max_score": 35.0,
                    "sub_scores": {
                        "power": {
                            "score": round(s_power, 2),
                            "max_score": 11.0,
                            "player_avg": round(avg_power, 2),
                            "gt": gt_power,
                            "deviation_ratio": round(e_power, 4),
                        },
                        "spot_size": {
                            "score": round(s_spot, 2),
                            "max_score": 8.0,
                            "player_avg": round(avg_spot, 2),
                            "gt": gt_spot,
                            "deviation_ratio": round(e_spot, 4),
                        },
                        "exposure_time": {
                            "score": round(s_time, 2),
                            "max_score": 8.0,
                            "player_avg": round(avg_time, 2),
                            "gt": gt_time,
                            "deviation_ratio": round(e_time, 4),
                        },
                        "wavelength": {
                            "score": round(s_wave, 2),
                            "max_score": 8.0,
                            "player_avg": round(avg_wave, 2),
                            "gt": gt_wave,
                            "deviation_ratio": round(e_wave, 4),
                        },
                    },
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
