from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.optimize import minimize


st.set_page_config(
    page_title="激光四级约束拟合器",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 1.2rem;}
    .metric-card {
        background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(16,185,129,0.08));
        border: 1px solid rgba(59,130,246,0.12);
        border-radius: 18px;
        padding: 14px 16px;
        margin-bottom: 8px;
    }
    .small-note {color: rgba(100,116,139,1); font-size: 0.9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


EPS = 1e-9
COLOR_LABELS = ["绿光", "黄光", "红光"]
COLOR_KEY_MAP = {"绿光": "green", "黄光": "yellow", "红光": "red"}
REGION_LABELS = ["区域1", "区域2", "区域3", "区域4"]

DISPLAY_POWER_MIN = 50.0
DISPLAY_POWER_MAX = 500.0
DISPLAY_TIME_MIN = 50.0
DISPLAY_TIME_MAX = 500.0
DISPLAY_SPOT_MIN = 10.0
DISPLAY_SPOT_MAX = 500.0

PARAM_BOUNDS = {
    "beta": (0.01, 30.0),
    "gamma": (0.1, 3.0),
    "p0": (10.0, 500.0),
    "d0": (10.0, 500.0),
    "t0_ms": (10.0, 500.0),
}


@dataclass
class PointConstraint:
    power: float
    spot: float
    time_ms: float
    label: int
    source: str = "fixed"


@dataclass
class RangeConstraint:
    power_lo: float
    power_hi: float
    spot_lo: float
    spot_hi: float
    time_lo: float
    time_hi: float
    center_label: int
    source: str = "range"


# ------------------------------
# 默认数据（按你给的 577nm 预处理结果；2-3 已按 2 级处理）
# ------------------------------
def default_fixed_points_df() -> pd.DataFrame:
    # 按用户最终确认的 relaxed_points 数据写死为默认值
    # 注意：用户消息里写“18个数据点”，但实际贴出的清单是 13 个单点 + 4 个范围 = 17 条
    return pd.DataFrame(
        [
            {"power": 150.0, "spot": 200.0, "time_ms": 200.0, "label": 3},
            {"power": 100.0, "spot": 200.0, "time_ms": 200.0, "label": 3},
            {"power": 230.0, "spot": 300.0, "time_ms": 200.0, "label": 3},
            {"power": 130.0, "spot": 200.0, "time_ms": 200.0, "label": 3},
            {"power": 110.0, "spot": 200.0, "time_ms": 200.0, "label": 3},
            {"power": 110.0, "spot": 300.0, "time_ms": 200.0, "label": 2},
            {"power": 130.0, "spot": 300.0, "time_ms": 200.0, "label": 2},
            {"power": 180.0, "spot": 200.0, "time_ms": 200.0, "label": 3},
            {"power": 140.0, "spot": 300.0, "time_ms": 200.0, "label": 2},
            {"power": 180.0, "spot": 300.0, "time_ms": 200.0, "label": 2},
            {"power": 160.0, "spot": 200.0, "time_ms": 200.0, "label": 3},
            {"power": 180.0, "spot": 200.0, "time_ms": 250.0, "label": 3},
            {"power": 200.0, "spot": 300.0, "time_ms": 200.0, "label": 2},
        ]
    )


def default_range_df() -> pd.DataFrame:
    # 按用户最终确认的 relaxed_ranges 数据写死为默认值
    return pd.DataFrame(
        [
            {"power_lo": 100.0, "power_hi": 120.0, "spot_lo": 200.0, "spot_hi": 200.0, "time_lo": 200.0, "time_hi": 200.0, "center_label": 3},
            {"power_lo": 180.0, "power_hi": 200.0, "spot_lo": 300.0, "spot_hi": 300.0, "time_lo": 200.0, "time_hi": 200.0, "center_label": 2},
            {"power_lo": 160.0, "power_hi": 180.0, "spot_lo": 300.0, "spot_hi": 300.0, "time_lo": 200.0, "time_hi": 200.0, "center_label": 2},
            {"power_lo": 130.0, "power_hi": 200.0, "spot_lo": 200.0, "spot_hi": 200.0, "time_lo": 200.0, "time_hi": 200.0, "center_label": 3},
        ]
    )


# ------------------------------
# 参数映射 / 数学工具
# ------------------------------
def sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return np.where(x >= 0, 1.0 / (1.0 + np.exp(-x)), np.exp(x) / (1.0 + np.exp(x)))


def softplus(x: np.ndarray) -> np.ndarray:
    return np.logaddexp(0.0, x)


def inv_sigmoid_unit(y: float) -> float:
    y = float(np.clip(y, 1e-6, 1 - 1e-6))
    return float(np.log(y / (1 - y)))


def map_to_bounds(raw: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return lo + (hi - lo) * sigmoid(raw)


def inv_map_to_bounds(value: float, lo: float, hi: float) -> float:
    y = (float(value) - lo) / (hi - lo)
    return inv_sigmoid_unit(y)


def raw_to_params(raw: np.ndarray) -> dict[str, float]:
    return {
        "beta": float(map_to_bounds(raw[0], *PARAM_BOUNDS["beta"])),
        "gamma": float(map_to_bounds(raw[1], *PARAM_BOUNDS["gamma"])),
        "p0": float(map_to_bounds(raw[2], *PARAM_BOUNDS["p0"])),
        "d0": float(map_to_bounds(raw[3], *PARAM_BOUNDS["d0"])),
        "t0_ms": float(map_to_bounds(raw[4], *PARAM_BOUNDS["t0_ms"])),
    }


def params_to_raw(beta: float, gamma: float, p0: float, d0: float, t0_ms: float) -> np.ndarray:
    return np.array(
        [
            inv_map_to_bounds(beta, *PARAM_BOUNDS["beta"]),
            inv_map_to_bounds(gamma, *PARAM_BOUNDS["gamma"]),
            inv_map_to_bounds(p0, *PARAM_BOUNDS["p0"]),
            inv_map_to_bounds(d0, *PARAM_BOUNDS["d0"]),
            inv_map_to_bounds(t0_ms, *PARAM_BOUNDS["t0_ms"]),
        ],
        dtype=float,
    )


def raw_to_thresholds(raw_thr: np.ndarray) -> tuple[float, float, float]:
    t1 = float(raw_thr[0])
    t2 = float(t1 + softplus(raw_thr[1]) + 1e-3)
    t3 = float(t2 + softplus(raw_thr[2]) + 1e-3)
    return t1, t2, t3


def thresholds_to_raw(t1: float, t2: float, t3: float) -> np.ndarray:
    d12 = max(float(t2) - float(t1) - 1e-3, 1e-6)
    d23 = max(float(t3) - float(t2) - 1e-3, 1e-6)
    return np.array([float(t1), np.log(np.expm1(d12)), np.log(np.expm1(d23))], dtype=float)


# ------------------------------
# 目标公式（按第一页说明）
# z = k_color * beta * (P/P0) * (d0/d)^gamma * ln(t/t0)
# ------------------------------
def score_formula(power_mw, time_ms, spot_um, *, beta, gamma, p0, d0, t0_ms, color_factor):
    p = np.asarray(power_mw, dtype=float)
    t_ms = np.asarray(time_ms, dtype=float)
    d = np.asarray(spot_um, dtype=float)

    p0_safe = max(float(p0), EPS)
    d0_safe = max(float(d0), EPS)
    t0_safe = max(float(t0_ms), EPS)
    t_ms_safe = np.maximum(t_ms, EPS)
    d_safe = np.maximum(d, EPS)

    return color_factor * beta * (p / p0_safe) * (d0_safe / d_safe) ** gamma * np.log(t_ms_safe / t0_safe)


# ------------------------------
# 四级分区
# ------------------------------
def predict_region_from_score(score: np.ndarray, t1: float, t2: float, t3: float) -> np.ndarray:
    z = np.asarray(score, dtype=float)
    return np.select([z < t1, z < t2, z < t3], [1, 2, 3], default=4).astype(int)


def region_name(region: int) -> str:
    return REGION_LABELS[int(region) - 1]


def region_soft_memberships(z: np.ndarray, t1: float, t2: float, t3: float, k: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    z = np.asarray(z, dtype=float)
    s1 = sigmoid(k * (z - t1))
    s2 = sigmoid(k * (z - t2))
    s3 = sigmoid(k * (z - t3))
    p1 = 1.0 - s1
    p2 = s1 - s2
    p3 = s2 - s3
    p4 = s3
    return p1, p2, p3, p4


# ------------------------------
# 数据解析
# ------------------------------
def parse_fixed_points(df: pd.DataFrame) -> list[PointConstraint]:
    out = []
    for _, r in df.iterrows():
        label = int(r["label"])
        if label not in (1, 2, 3, 4):
            continue
        out.append(PointConstraint(float(r["power"]), float(r["spot"]), float(r["time_ms"]), label, source="fixed"))
    return out


def parse_ranges(df: pd.DataFrame) -> list[RangeConstraint]:
    out = []
    for _, r in df.iterrows():
        label = int(r["center_label"])
        if label not in (1, 2, 3, 4):
            continue
        out.append(
            RangeConstraint(
                power_lo=float(r["power_lo"]),
                power_hi=float(r["power_hi"]),
                spot_lo=float(r["spot_lo"]),
                spot_hi=float(r["spot_hi"]),
                time_lo=float(r["time_lo"]),
                time_hi=float(r["time_hi"]),
                center_label=label,
                source="range",
            )
        )
    return out


# ------------------------------
# 采样工具
# ------------------------------
def clip_box(x: np.ndarray, low: float = 0.0, high: float = 500.0) -> np.ndarray:
    return np.clip(x, low, high)


def sample_shell(center: Iterable[float], frac: float, n: int, rng: np.random.Generator) -> np.ndarray:
    center = np.asarray(list(center), dtype=float)
    scales = np.maximum(np.abs(center) * frac, 1.0)
    pts = center + rng.normal(size=(n, 3)) * scales
    return clip_box(pts)


def sample_range_center_and_cloud(r: RangeConstraint, n_soft: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    center = np.array(
        [
            0.5 * (r.power_lo + r.power_hi),
            0.5 * (r.spot_lo + r.spot_hi),
            0.5 * (r.time_lo + r.time_hi),
        ],
        dtype=float,
    )
    cloud = np.column_stack(
        [
            rng.uniform(r.power_lo, r.power_hi, size=n_soft),
            rng.uniform(r.spot_lo, r.spot_hi, size=n_soft),
            rng.uniform(r.time_lo, r.time_hi, size=n_soft),
        ]
    )
    return center, clip_box(cloud)


# ------------------------------
# 优化目标（硬约束优先：先满足硬约束，再谈其它约束）
# ------------------------------
def build_constraint_diagnostic_df(fixed_df: pd.DataFrame, range_df: pd.DataFrame) -> pd.DataFrame:
    fixed_rows = fixed_df.copy()
    if len(fixed_rows):
        fixed_rows = fixed_rows[["power", "spot", "time_ms", "label"]].copy()
        fixed_rows["record_type"] = "fixed"
        fixed_rows["record_id"] = np.arange(len(fixed_rows))
    else:
        fixed_rows = pd.DataFrame(columns=["power", "spot", "time_ms", "label", "record_type", "record_id"])

    range_rows = range_df.copy()
    if len(range_rows):
        range_rows = pd.DataFrame(
            {
                "power": 0.5 * (range_rows["power_lo"].astype(float) + range_rows["power_hi"].astype(float)),
                "spot": 0.5 * (range_rows["spot_lo"].astype(float) + range_rows["spot_hi"].astype(float)),
                "time_ms": 0.5 * (range_rows["time_lo"].astype(float) + range_rows["time_hi"].astype(float)),
                "label": range_rows["center_label"].astype(int),
                "record_type": "range",
                "record_id": np.arange(len(range_rows)),
            }
        )
    else:
        range_rows = pd.DataFrame(columns=["power", "spot", "time_ms", "label", "record_type", "record_id"])

    all_rows = pd.concat([fixed_rows, range_rows], ignore_index=True)
    if len(all_rows):
        all_rows["label"] = all_rows["label"].astype(int)
        all_rows["power"] = all_rows["power"].astype(float)
        all_rows["spot"] = all_rows["spot"].astype(float)
        all_rows["time_ms"] = all_rows["time_ms"].astype(float)
    return all_rows


def _dominates_more_severe(a: pd.Series, b: pd.Series) -> bool:
    return (
        float(a["power"]) >= float(b["power"])
        and float(a["time_ms"]) >= float(b["time_ms"])
        and float(a["spot"]) <= float(b["spot"])
        and (
            float(a["power"]) > float(b["power"])
            or float(a["time_ms"]) > float(b["time_ms"])
            or float(a["spot"]) < float(b["spot"])
        )
    )


def find_hard_contradictions(fixed_df: pd.DataFrame, range_df: pd.DataFrame) -> pd.DataFrame:
    all_rows = build_constraint_diagnostic_df(fixed_df, range_df)
    if not len(all_rows):
        return pd.DataFrame(
            columns=[
                "lower_record_type", "lower_record_id", "lower_label", "lower_power", "lower_spot", "lower_time_ms",
                "higher_record_type", "higher_record_id", "higher_label", "higher_power", "higher_spot", "higher_time_ms",
                "reason",
            ]
        )

    contradictions = []
    for i, lower in all_rows.iterrows():
        for j, higher in all_rows.iterrows():
            if i == j:
                continue
            if int(lower["label"]) >= int(higher["label"]):
                continue
            if _dominates_more_severe(lower, higher):
                contradictions.append(
                    {
                        "lower_record_type": lower["record_type"],
                        "lower_record_id": int(lower["record_id"]),
                        "lower_label": int(lower["label"]),
                        "lower_power": float(lower["power"]),
                        "lower_spot": float(lower["spot"]),
                        "lower_time_ms": float(lower["time_ms"]),
                        "higher_record_type": higher["record_type"],
                        "higher_record_id": int(higher["record_id"]),
                        "higher_label": int(higher["label"]),
                        "higher_power": float(higher["power"]),
                        "higher_spot": float(higher["spot"]),
                        "higher_time_ms": float(higher["time_ms"]),
                        "reason": "更强参数却更低等级，当前单调公式下无法同时满足",
                    }
                )
                break
    return pd.DataFrame(contradictions)


def make_loss_evaluator(
    fixed_points: list[PointConstraint],
    ranged: list[RangeConstraint],
    vol_samples: np.ndarray,
    *,
    color_factor: float,
    shell_frac: float,
    shell_n: int,
    range_soft_n: int,
    hard_margin: float,
    soft_margin: float,
    volume_weight: float,
    smooth_k: float,
    reg_weight: float,
    seed: int,
):
    rng = np.random.default_rng(seed)

    point_centers = np.array([[p.power, p.spot, p.time_ms] for p in fixed_points], dtype=float)
    point_labels = np.array([int(p.label) for p in fixed_points], dtype=int)
    point_shells = [sample_shell(c, shell_frac, shell_n, rng) for c in point_centers]

    range_centers = []
    range_clouds = []
    range_labels = []
    for r in ranged:
        center, cloud = sample_range_center_and_cloud(r, range_soft_n, rng)
        range_centers.append(center)
        range_clouds.append(cloud)
        range_labels.append(int(r.center_label))

    range_centers = np.array(range_centers, dtype=float) if range_centers else np.empty((0, 3), dtype=float)
    range_labels = np.array(range_labels, dtype=int) if range_labels else np.empty((0,), dtype=int)

    def barrier(gap: np.ndarray) -> np.ndarray:
        return softplus(smooth_k * gap) / smooth_k

    def interval_penalty(z: np.ndarray, label: int, t1: float, t2: float, t3: float, margin: float) -> np.ndarray:
        z = np.asarray(z, dtype=float)
        if int(label) == 1:
            hi = t1 - margin
            return np.square(barrier(z - hi))
        if int(label) == 2:
            lo = t1 + margin
            hi = max(t2 - margin, lo)
            return np.square(barrier(lo - z)) + np.square(barrier(z - hi))
        if int(label) == 3:
            lo = t2 + margin
            hi = max(t3 - margin, lo)
            return np.square(barrier(lo - z)) + np.square(barrier(z - hi))
        if int(label) == 4:
            lo = t3 + margin
            return np.square(barrier(lo - z))
        raise ValueError("Only labels 1~4 are supported in constraints.")

    def unpack(v: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float], dict[str, float]]:
        raw = np.asarray(v[:5], dtype=float)
        raw_thr = np.asarray(v[5:8], dtype=float)
        thr = raw_to_thresholds(raw_thr)
        prm = raw_to_params(raw)
        return raw, raw_thr, thr, prm

    def components(v: np.ndarray) -> dict[str, float]:
        raw, raw_thr, (t1, t2, t3), prm = unpack(v)

        loss_hard = 0.0
        loss_soft = 0.0

        if len(point_centers):
            z0 = score_formula(point_centers[:, 0], point_centers[:, 2], point_centers[:, 1], color_factor=color_factor, **prm)
            for zi, lab in zip(z0, point_labels):
                loss_hard += float(interval_penalty(np.array([zi]), int(lab), t1, t2, t3, hard_margin)[0])

            for shell, lab in zip(point_shells, point_labels):
                zs = score_formula(shell[:, 0], shell[:, 2], shell[:, 1], color_factor=color_factor, **prm)
                loss_soft += float(np.mean(interval_penalty(zs, int(lab), t1, t2, t3, soft_margin)))

        if len(range_centers):
            zc = score_formula(range_centers[:, 0], range_centers[:, 2], range_centers[:, 1], color_factor=color_factor, **prm)
            for zi, lab in zip(zc, range_labels):
                loss_hard += float(interval_penalty(np.array([zi]), int(lab), t1, t2, t3, hard_margin)[0])

            for cloud, lab in zip(range_clouds, range_labels):
                zs = score_formula(cloud[:, 0], cloud[:, 2], cloud[:, 1], color_factor=color_factor, **prm)
                loss_soft += float(np.mean(interval_penalty(zs, int(lab), t1, t2, t3, soft_margin)))

        zv = score_formula(vol_samples[:, 0], vol_samples[:, 2], vol_samples[:, 1], color_factor=color_factor, **prm)
        p1, p2, p3, p4 = region_soft_memberships(zv, t1, t2, t3, smooth_k)
        frac = np.array([p1.mean(), p2.mean(), p3.mean(), p4.mean()], dtype=float)
        loss_volume = float(np.sum((frac - 0.25) ** 2))

        raw_reg = reg_weight * float(np.sum(np.square(raw)))
        thr_reg = reg_weight * 0.1 * float(np.sum(np.square(raw_thr)))

        return {
            "loss_hard": float(loss_hard),
            "loss_soft": float(loss_soft),
            "loss_volume": float(loss_volume),
            "raw_reg": float(raw_reg),
            "thr_reg": float(thr_reg),
            "reg_total": float(raw_reg + thr_reg),
            "total_stage2_base": float(loss_soft + volume_weight * loss_volume + raw_reg + thr_reg),
        }

    def hard_only_loss(v: np.ndarray) -> float:
        c = components(v)
        return float(c["loss_hard"] + 1e-6 * c["reg_total"])

    def full_loss(v: np.ndarray, *, soft_weight: float, hard_weight: float) -> float:
        c = components(v)
        return float(
            hard_weight * c["loss_hard"]
            + soft_weight * c["loss_soft"]
            + volume_weight * c["loss_volume"]
            + c["reg_total"]
        )

    def stage2_loss(v: np.ndarray, *, soft_weight: float, hard_lock_tol: float, hard_barrier_weight: float) -> float:
        c = components(v)
        hard_excess = max(c["loss_hard"] - hard_lock_tol, 0.0)
        return float(
            soft_weight * c["loss_soft"]
            + volume_weight * c["loss_volume"]
            + c["reg_total"]
            + hard_barrier_weight * hard_excess * hard_excess
        )

    return components, hard_only_loss, full_loss, stage2_loss

def evaluate_solution(
    raw: np.ndarray,
    raw_thr: np.ndarray,
    fixed_points: list[PointConstraint],
    ranged: list[RangeConstraint],
    *,
    color_factor: float,
    shell_frac: float,
    shell_n: int,
    range_soft_n: int,
    volume_eval_n: int,
    seed: int,
    hard_margin: float = 0.0,
    soft_margin: float = 0.0,
    smooth_k: float = 25.0,
    reg_weight: float = 0.0,
    volume_weight: float = 1.0,
) -> dict:
    prm = raw_to_params(raw)
    t1, t2, t3 = raw_to_thresholds(raw_thr)
    rng = np.random.default_rng(seed)

    fixed_rows = []
    fixed_shell_rates = []
    for p in fixed_points:
        z = float(score_formula(np.array([p.power]), np.array([p.time_ms]), np.array([p.spot]), color_factor=color_factor, **prm)[0])
        pred = int(predict_region_from_score(np.array([z]), t1, t2, t3)[0])
        shell = sample_shell([p.power, p.spot, p.time_ms], shell_frac, shell_n, rng)
        z_shell = score_formula(shell[:, 0], shell[:, 2], shell[:, 1], color_factor=color_factor, **prm)
        pred_shell = predict_region_from_score(z_shell, t1, t2, t3)
        hit_rate = float(np.mean(pred_shell == int(p.label)))
        fixed_shell_rates.append(hit_rate)
        fixed_rows.append(
            {
                "source": p.source,
                "power": p.power,
                "spot": p.spot,
                "time_ms": p.time_ms,
                "target_label": int(p.label),
                "pred_label": pred,
                "score": z,
                "center_ok": pred == int(p.label),
                "shell_hit_rate": hit_rate,
            }
        )

    range_rows = []
    range_soft_rates = []
    for idx, r in enumerate(ranged, start=1):
        center, cloud = sample_range_center_and_cloud(r, range_soft_n, rng)
        zc = float(score_formula(center[None, 0], center[None, 2], center[None, 1], color_factor=color_factor, **prm)[0])
        pred_center = int(predict_region_from_score(np.array([zc]), t1, t2, t3)[0])
        z_cloud = score_formula(cloud[:, 0], cloud[:, 2], cloud[:, 1], color_factor=color_factor, **prm)
        pred_cloud = predict_region_from_score(z_cloud, t1, t2, t3)
        hit_rate = float(np.mean(pred_cloud == int(r.center_label)))
        range_soft_rates.append(hit_rate)
        range_rows.append(
            {
                "source": f"range_{idx}",
                "power": center[0],
                "spot": center[1],
                "time_ms": center[2],
                "target_label": int(r.center_label),
                "pred_label": pred_center,
                "score": zc,
                "center_ok": pred_center == int(r.center_label),
                "soft_cloud_hit_rate": hit_rate,
            }
        )

    vol = np.column_stack(
        [
            rng.uniform(0.0, 500.0, size=volume_eval_n),
            rng.uniform(0.0, 500.0, size=volume_eval_n),
            rng.uniform(0.0, 500.0, size=volume_eval_n),
        ]
    )
    zv = score_formula(vol[:, 0], vol[:, 2], vol[:, 1], color_factor=color_factor, **prm)
    pred_vol = predict_region_from_score(zv, t1, t2, t3)
    frac = {f"volume_frac_{k}": float(np.mean(pred_vol == k)) for k in (1, 2, 3, 4)}

    fixed_df = pd.DataFrame(fixed_rows)
    range_df = pd.DataFrame(range_rows)
    hard_ok_count = int(fixed_df["center_ok"].sum() + range_df["center_ok"].sum()) if len(fixed_df) or len(range_df) else 0
    hard_total = int(len(fixed_df) + len(range_df))

    # 用和训练一致的损失定义再评估一次，便于判断是否“先满足硬约束”
    eval_rng = np.random.default_rng(seed + 12345)
    vol_eval_samples = np.column_stack(
        [
            eval_rng.uniform(0.0, 500.0, size=max(volume_eval_n, 1000)),
            eval_rng.uniform(0.0, 500.0, size=max(volume_eval_n, 1000)),
            eval_rng.uniform(0.0, 500.0, size=max(volume_eval_n, 1000)),
        ]
    )
    components_fn, _, _, _ = make_loss_evaluator(
        fixed_points=fixed_points,
        ranged=ranged,
        vol_samples=vol_eval_samples,
        color_factor=color_factor,
        shell_frac=shell_frac,
        shell_n=shell_n,
        range_soft_n=range_soft_n,
        hard_margin=hard_margin,
        soft_margin=soft_margin,
        volume_weight=volume_weight,
        smooth_k=smooth_k,
        reg_weight=reg_weight,
        seed=seed + 54321,
    )
    comp = components_fn(np.concatenate([raw, raw_thr]))

    metrics = {
        "hard_ok_count": hard_ok_count,
        "hard_total": hard_total,
        "hard_ok_rate": float(hard_ok_count / max(hard_total, 1)),
        "hard_loss": float(comp["loss_hard"]),
        "soft_loss": float(comp["loss_soft"]),
        "volume_loss": float(comp["loss_volume"]),
        "fixed_shell_mean": float(np.mean(fixed_shell_rates)) if fixed_shell_rates else np.nan,
        "range_cloud_mean": float(np.mean(range_soft_rates)) if range_soft_rates else np.nan,
        **frac,
        "t1": t1,
        "t2": t2,
        "t3": t3,
    }
    return {"fixed_df": fixed_df, "range_df": range_df, "metrics": metrics, "params": prm}


def fit_parameters(
    fixed_points: list[PointConstraint],
    ranged: list[RangeConstraint],
    *,
    color_factor: float,
    shell_frac: float,
    shell_n: int,
    range_soft_n: int,
    volume_train_n: int,
    volume_eval_n: int,
    hard_margin: float,
    soft_margin: float,
    soft_weight: float,
    volume_weight: float,
    smooth_k: float,
    reg_weight: float,
    restarts: int,
    init_params: dict[str, float],
    seed: int,
    hard_loss_tol: float,
    hard_barrier_weight: float,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    rng = np.random.default_rng(seed)
    vol_samples = np.column_stack(
        [
            rng.uniform(0.0, 500.0, size=volume_train_n),
            rng.uniform(0.0, 500.0, size=volume_train_n),
            rng.uniform(0.0, 500.0, size=volume_train_n),
        ]
    )

    components_fn, hard_only_loss_fn, full_loss_fn, stage2_loss_fn = make_loss_evaluator(
        fixed_points=fixed_points,
        ranged=ranged,
        vol_samples=vol_samples,
        color_factor=color_factor,
        shell_frac=shell_frac,
        shell_n=shell_n,
        range_soft_n=range_soft_n,
        hard_margin=hard_margin,
        soft_margin=soft_margin,
        volume_weight=volume_weight,
        smooth_k=smooth_k,
        reg_weight=reg_weight,
        seed=seed,
    )

    base_raw = params_to_raw(**init_params)
    prm0 = raw_to_params(base_raw)
    threshold_raw0 = np.array([0.0, 0.0, 0.0], dtype=float)

    all_centers = []
    if fixed_points:
        all_centers.append(np.array([[p.power, p.spot, p.time_ms] for p in fixed_points], dtype=float))
    if ranged:
        all_centers.append(
            np.array(
                [
                    [0.5 * (r.power_lo + r.power_hi), 0.5 * (r.spot_lo + r.spot_hi), 0.5 * (r.time_lo + r.time_hi)]
                    for r in ranged
                ],
                dtype=float,
            )
        )
    if all_centers:
        centers = np.vstack(all_centers)
        scores0 = score_formula(centers[:, 0], centers[:, 2], centers[:, 1], color_factor=color_factor, **prm0)
        q1, q2, q3 = np.quantile(scores0, [0.20, 0.50, 0.80])
        threshold_raw0 = thresholds_to_raw(float(q1), float(max(q2, q1 + 0.01)), float(max(q3, q2 + 0.01)))

    # Stage 1: 只优化硬约束
    stage1_best = None
    for i in range(restarts):
        if progress_callback is not None:
            progress_callback(i, restarts * 2, "stage1_hard_only")

        raw0 = base_raw + rng.normal(0.0, 0.35, size=5)
        thr0 = threshold_raw0 + rng.normal(0.0, 0.30, size=3)
        x0 = np.concatenate([raw0, thr0])
        res = minimize(hard_only_loss_fn, x0, method="L-BFGS-B", options={"maxiter": 500})
        hard_obj = float(hard_only_loss_fn(res.x))
        hard_comp = components_fn(res.x)
        if stage1_best is None or hard_obj < stage1_best["hard_objective"]:
            stage1_best = {
                "res": res,
                "hard_objective": hard_obj,
                "components": hard_comp,
            }

    raw_stage1 = np.asarray(stage1_best["res"].x[:5], dtype=float)
    raw_thr_stage1 = np.asarray(stage1_best["res"].x[5:8], dtype=float)
    eval_stage1 = evaluate_solution(
        raw=raw_stage1,
        raw_thr=raw_thr_stage1,
        fixed_points=fixed_points,
        ranged=ranged,
        color_factor=color_factor,
        shell_frac=shell_frac,
        shell_n=shell_n,
        range_soft_n=range_soft_n,
        volume_eval_n=volume_eval_n,
        seed=seed + 10_000,
        hard_margin=hard_margin,
        soft_margin=soft_margin,
        smooth_k=smooth_k,
        reg_weight=reg_weight,
        volume_weight=volume_weight,
    )
    stage1_hard_feasible = (
        eval_stage1["metrics"]["hard_ok_count"] == eval_stage1["metrics"]["hard_total"]
        # and eval_stage1["metrics"]["hard_loss"] <= hard_loss_tol
    )

    # Stage 2: 只有在硬约束先满足后，才优化软约束/体积/正则
    if stage1_hard_feasible:
        stage2_best = None
        for i in range(restarts):
            if progress_callback is not None:
                progress_callback(restarts + i, restarts * 2, "stage2_soft_volume")

            if i == 0:
                x0 = np.asarray(stage1_best["res"].x, dtype=float)
            else:
                x0 = np.asarray(stage1_best["res"].x, dtype=float).copy()
                x0[:5] += rng.normal(0.0, 0.08, size=5)
                x0[5:8] += rng.normal(0.0, 0.05, size=3)

            res = minimize(
                lambda v: stage2_loss_fn(
                    v,
                    soft_weight=soft_weight,
                    hard_lock_tol=hard_loss_tol,
                    hard_barrier_weight=hard_barrier_weight,
                ),
                x0,
                method="L-BFGS-B",
                options={"maxiter": 350},
            )
            comp = components_fn(res.x)
            obj = float(
                stage2_loss_fn(
                    res.x,
                    soft_weight=soft_weight,
                    hard_lock_tol=hard_loss_tol,
                    hard_barrier_weight=hard_barrier_weight,
                )
            )
            if stage2_best is None or obj < stage2_best["objective"]:
                stage2_best = {
                    "res": res,
                    "objective": obj,
                    "components": comp,
                }

        raw_final = np.asarray(stage2_best["res"].x[:5], dtype=float)
        raw_thr_final = np.asarray(stage2_best["res"].x[5:8], dtype=float)
        evaluation = evaluate_solution(
            raw=raw_final,
            raw_thr=raw_thr_final,
            fixed_points=fixed_points,
            ranged=ranged,
            color_factor=color_factor,
            shell_frac=shell_frac,
            shell_n=shell_n,
            range_soft_n=range_soft_n,
            volume_eval_n=volume_eval_n,
            seed=seed + 10_000,
            hard_margin=hard_margin,
            soft_margin=soft_margin,
            smooth_k=smooth_k,
            reg_weight=reg_weight,
            volume_weight=volume_weight,
        )
        hard_preserved = (
            evaluation["metrics"]["hard_ok_count"] == evaluation["metrics"]["hard_total"]
            and evaluation["metrics"]["hard_loss"] <= hard_loss_tol
        )
        if not hard_preserved:
            raw_final = raw_stage1
            raw_thr_final = raw_thr_stage1
            evaluation = eval_stage1
            stage_name = "stage1_hard_only_fallback"
            final_objective = float(stage1_best["hard_objective"])
        else:
            stage_name = "stage2_soft_volume_after_hard"
            final_objective = float(stage2_best["objective"])
    else:
        raw_final = raw_stage1
        raw_thr_final = raw_thr_stage1
        evaluation = eval_stage1
        stage_name = "stage1_hard_only_infeasible"
        final_objective = float(stage1_best["hard_objective"])

    if progress_callback is not None:
        progress_callback(restarts * 2, restarts * 2, stage_name)

    return {
        "raw": raw_final,
        "raw_thr": raw_thr_final,
        "objective": final_objective,
        "evaluation": evaluation,
        "stage": stage_name,
        "stage1_hard_feasible": bool(stage1_hard_feasible),
        "stage1_hard_loss": float(eval_stage1["metrics"]["hard_loss"]),
        "stage1_hard_ok_count": int(eval_stage1["metrics"]["hard_ok_count"]),
        "stage1_hard_total": int(eval_stage1["metrics"]["hard_total"]),
        "stage1_evaluation": eval_stage1,
    }


# ------------------------------
# 可视化数据
# ------------------------------
# 可视化数据
# ------------------------------
@st.cache_data(show_spinner=False)
def make_volume_sample_df(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "power": rng.uniform(DISPLAY_POWER_MIN, DISPLAY_POWER_MAX, size=n),
            "spot": rng.uniform(DISPLAY_SPOT_MIN, DISPLAY_SPOT_MAX, size=n),
            "time_ms": rng.uniform(DISPLAY_TIME_MIN, DISPLAY_TIME_MAX, size=n),
        }
    )


def apply_pretty_scene(fig: go.Figure, *, title: str | None = None, height: int = 620) -> go.Figure:
    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=0, r=0, t=52, b=0),
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend_title_text="分区",
        scene=dict(
            xaxis=dict(
                title="功率 (mW)",
                range=[DISPLAY_POWER_MIN, DISPLAY_POWER_MAX],
                backgroundcolor="rgba(248,250,252,1)",
                gridcolor="rgba(148,163,184,0.22)",
                zerolinecolor="rgba(148,163,184,0.30)",
                showbackground=True,
            ),
            yaxis=dict(
                title="时间 (ms)",
                range=[DISPLAY_TIME_MIN, DISPLAY_TIME_MAX],
                backgroundcolor="rgba(248,250,252,1)",
                gridcolor="rgba(148,163,184,0.22)",
                zerolinecolor="rgba(148,163,184,0.30)",
                showbackground=True,
            ),
            zaxis=dict(
                title="光斑 (μm)",
                range=[DISPLAY_SPOT_MIN, DISPLAY_SPOT_MAX],
                backgroundcolor="rgba(248,250,252,1)",
                gridcolor="rgba(148,163,184,0.22)",
                zerolinecolor="rgba(148,163,184,0.30)",
                showbackground=True,
            ),
            aspectmode="manual",
            aspectratio=dict(x=1.15, y=1.05, z=0.95),
            camera=dict(eye=dict(x=1.55, y=1.35, z=0.80)),
        ),
    )
    return fig


def make_scatter_3d(sample_df: pd.DataFrame, constraints_df: pd.DataFrame) -> go.Figure:
    plot_df = sample_df.copy()
    smin = float(plot_df["score"].min())
    smax = float(plot_df["score"].max())
    if smax - smin < 1e-12:
        plot_df["marker_size"] = 4.0
    else:
        plot_df["marker_size"] = 3.0 + 6.0 * (plot_df["score"] - smin) / (smax - smin)

    plot_df["region_name"] = plot_df["region"].map(region_name)
    fig = px.scatter_3d(
        plot_df,
        x="power",
        y="time_ms",
        z="spot",
        color="region_name",
        size="marker_size",
        opacity=0.22,
        size_max=8,
        title="三维参数空间四级分区采样",
        category_orders={"region_name": REGION_LABELS},
        labels={"power": "功率 (mW)", "time_ms": "时间 (ms)", "spot": "光斑 (μm)", "region_name": "分区"},
        hover_data={"score": ":.4f", "marker_size": False, "region": False},
    )
    if len(constraints_df):
        fig.add_trace(
            go.Scatter3d(
                x=constraints_df["power"],
                y=constraints_df["time_ms"],
                z=constraints_df["spot"],
                mode="markers+text",
                marker=dict(size=7, symbol="diamond", color=np.where(constraints_df["target_label"] == 3, "red", "blue")),
                text=constraints_df["target_label"].astype(str),
                textposition="top center",
                name="约束中心(仅2/3级)",
                hovertemplate="P=%{x:.1f}<br>T=%{y:.1f}<br>S=%{z:.1f}<br>目标=%{text}<extra></extra>",
            )
        )
    apply_pretty_scene(fig, title="三维参数空间四级分区采样", height=620)
    return fig


def make_histogram(sample_df: pd.DataFrame, t1: float, t2: float, t3: float) -> go.Figure:
    plot_df = sample_df.copy()
    plot_df["region_name"] = plot_df["region"].map(region_name)
    fig = px.histogram(
        plot_df,
        x="score",
        color="region_name",
        nbins=80,
        opacity=0.80,
        title="公式值分布与四级阈值",
        category_orders={"region_name": REGION_LABELS},
        labels={"score": "公式值 z", "count": "样本数", "region_name": "分区"},
    )
    for value, name in [(t1, "阈值1"), (t2, "阈值2"), (t3, "阈值3")]:
        fig.add_vline(x=value, line_width=2, line_dash="dash", annotation_text=name)
    fig.update_layout(height=420)
    return fig


def make_isosurfaces(params: dict[str, float], color_factor: float, t1: float, t2: float, t3: float, grid_n: int) -> go.Figure:
    p = np.linspace(DISPLAY_POWER_MIN, DISPLAY_POWER_MAX, grid_n)
    tm = np.linspace(DISPLAY_TIME_MIN, DISPLAY_TIME_MAX, grid_n)
    d = np.linspace(DISPLAY_SPOT_MIN, DISPLAY_SPOT_MAX, grid_n)
    P, T, D = np.meshgrid(p, tm, d, indexing="ij")
    Z = score_formula(P, T, D, color_factor=color_factor, **params)

    fig = go.Figure()
    iso_specs = [
        (t1, "阈值1等值面", [[0.0, "rgba(59,130,246,0.22)"], [1.0, "rgba(59,130,246,0.22)"]]),
        (t2, "阈值2等值面", [[0.0, "rgba(16,185,129,0.20)"], [1.0, "rgba(16,185,129,0.20)"]]),
        (t3, "阈值3等值面", [[0.0, "rgba(239,68,68,0.20)"], [1.0, "rgba(239,68,68,0.20)"]]),
    ]
    for value, name, cs in iso_specs:
        fig.add_trace(
            go.Isosurface(
                x=P.flatten(),
                y=T.flatten(),
                z=D.flatten(),
                value=Z.flatten(),
                isomin=value,
                isomax=value,
                surface_count=1,
                opacity=0.16,
                caps=dict(x_show=False, y_show=False, z_show=False),
                colorscale=cs,
                showscale=False,
                name=name,
                hovertemplate="P=%{x:.1f}<br>T=%{y:.1f}<br>S=%{z:.1f}<extra>" + name + "</extra>",
            )
        )
    apply_pretty_scene(fig, title="四级分区的三张等值面", height=620)
    return fig


def make_iso_slice_plot(params: dict[str, float], color_factor: float, t1: float, t2: float, t3: float, fixed_spot: float, grid_n: int) -> go.Figure:
    p = np.linspace(DISPLAY_POWER_MIN, DISPLAY_POWER_MAX, grid_n)
    tm = np.linspace(DISPLAY_TIME_MIN, DISPLAY_TIME_MAX, grid_n)
    P, T = np.meshgrid(p, tm, indexing="xy")
    Z = score_formula(P, T, fixed_spot, color_factor=color_factor, **params)
    R = predict_region_from_score(Z, t1, t2, t3)

    fig = go.Figure()
    fig.add_trace(
        go.Contour(
            x=p,
            y=tm,
            z=R,
            contours=dict(start=1, end=4, size=1, coloring="heatmap", showlabels=True),
            colorscale=[
                [0.00, "rgba(59,130,246,0.25)"],
                [0.24, "rgba(59,130,246,0.25)"],
                [0.25, "rgba(6,182,212,0.25)"],
                [0.49, "rgba(6,182,212,0.25)"],
                [0.50, "rgba(16,185,129,0.25)"],
                [0.74, "rgba(16,185,129,0.25)"],
                [0.75, "rgba(239,68,68,0.25)"],
                [1.00, "rgba(239,68,68,0.25)"],
            ],
            colorbar=dict(title="区域", tickvals=[1, 2, 3, 4], ticktext=REGION_LABELS),
            opacity=0.9,
            showscale=True,
            line=dict(width=0),
            hovertemplate="P=%{x:.1f}<br>T=%{y:.1f}<br>区域=%{z}<extra></extra>",
            name="区域分区",
        )
    )
    for val, label, line_color in [
        (t1, "阈值1", "rgba(59,130,246,1)"),
        (t2, "阈值2", "rgba(16,185,129,1)"),
        (t3, "阈值3", "rgba(239,68,68,1)"),
    ]:
        fig.add_trace(
            go.Contour(
                x=p,
                y=tm,
                z=Z,
                contours=dict(coloring="none", showlines=True, start=val, end=val, size=1),
                line=dict(width=3, color=line_color),
                showscale=False,
                name=label,
                hoverinfo="skip",
            )
        )
    fig.update_layout(
        title=f"等值切面图：固定光斑 = {fixed_spot:.1f} μm 时的功率-时间平面",
        xaxis=dict(title="功率 (mW)", range=[DISPLAY_POWER_MIN, DISPLAY_POWER_MAX], showgrid=True, gridcolor="rgba(148,163,184,0.20)"),
        yaxis=dict(title="时间 (ms)", range=[DISPLAY_TIME_MIN, DISPLAY_TIME_MAX], showgrid=True, gridcolor="rgba(148,163,184,0.20)"),
        height=520,
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=0, r=0, t=55, b=0),
        legend_title_text="阈值线",
    )
    return fig


# ------------------------------
# Sidebar
# ------------------------------
st.sidebar.header("拟合设置")

with st.sidebar.expander("颜色设置", expanded=True):
    color_label = st.selectbox("激光颜色", COLOR_LABELS, index=1)
    green_k = st.slider("绿光系数 k_green", 0.10, 3.00, 1.00, 0.01)
    yellow_k = st.slider("黄光系数 k_yellow", 0.10, 3.00, 1.35, 0.01)
    red_k = st.slider("红光系数 k_red", 0.10, 3.00, 0.70, 0.01)
    color_factors = {"green": green_k, "yellow": yellow_k, "red": red_k}
    color_factor = color_factors[COLOR_KEY_MAP[color_label]]
    st.caption(f"当前使用：{color_label}，k_color = {color_factor:.2f}。默认数据为 577nm relaxed 数据，因此默认选中黄光。")

with st.sidebar.expander("初始参数（只作优化起点）", expanded=True):
    init_beta = st.slider("β 初始值", *PARAM_BOUNDS["beta"], 4.0, 0.01)
    init_gamma = st.slider("γ 初始值", *PARAM_BOUNDS["gamma"], 2.0, 0.01)
    init_p0 = st.slider("P₀ 初始值（mW）", *PARAM_BOUNDS["p0"], 100.0, 1.0)
    init_d0 = st.slider("d₀ 初始值（μm）", *PARAM_BOUNDS["d0"], 100.0, 1.0)
    init_t0 = st.slider("t₀ 初始值（ms）", *PARAM_BOUNDS["t0_ms"], 100.0, 1.0)

with st.sidebar.expander("约束与优化设置", expanded=True):
    shell_frac = st.slider("中心周围采样半径比例", 0.01, 0.20, 0.05, 0.01)
    shell_n = st.slider("每个固定点软约束采样数", 8, 128, 24, 8)
    range_soft_n = st.slider("每个范围点云采样数", 8, 128, 24, 8)
    hard_margin = st.slider("硬约束安全边距", 0.00, 1.00, 0.00, 0.01)
    soft_margin = st.slider("软约束安全边距", 0.00, 0.50, 0.02, 0.01)
    hard_loss_tol = st.number_input("硬约束达标容差", min_value=0.0, max_value=1.0, value=1e-8, step=1e-6, format="%.8f")
    soft_weight = st.slider("软约束权重", 1.0, 1000.0, 60.0, 1.0)
    volume_weight = st.slider("四区体积均衡权重", 0.0, 1000.0, 80.0, 1.0)
    hard_barrier_weight = st.slider("二阶段硬约束保护权重", 1e3, 1e7, 1e5, 1e3, format="%.0f")
    reg_weight = st.slider("参数正则权重", 0.0, 10.0, 0.001, 0.001)
    smooth_k = st.slider("平滑近似强度", 1.0, 100.0, 25.0, 1.0)
    restarts = st.slider("每阶段多起点次数", 1, 12, 6, 1)

with st.sidebar.expander("体积采样与可视化", expanded=False):
    volume_train_n = st.slider("训练体积采样数", 1000, 50000, 5000, 500)
    volume_eval_n = st.slider("评估体积采样数", 1000, 50000, 6000, 500)
    display_sample_n = st.slider("显示采样点数", 1000, 20000, 6000, 500)
    iso_grid_n = st.slider("等值面网格密度", 8, 24, 14, 1)
    slice_grid_n = st.slider("切面网格密度", 40, 200, 100, 10)
    fixed_spot = st.slider("切面固定光斑（μm）", 0.0, 500.0, 200.0, 1.0)
    random_seed = st.number_input("随机种子", min_value=0, value=42, step=1)

fit_button = st.sidebar.button("开始拟合", type="primary")

st.sidebar.markdown("---")
st.sidebar.caption("当前逻辑改为：先只做硬约束可行性搜索；只有硬约束全部满足后，才进入软约束、体积均衡和正则化优化。默认数据按你最后贴出的 relaxed_points + relaxed_ranges 写入。")


# ------------------------------
# Main
# ------------------------------
st.title("公式拟合目的：输入特定范围参数，得到正确等级光斑")
st.caption("将连续的公式得分 z 通过三个阈值 (t1, t2, t3) 映射到四个离散等级。当前默认数据使用你最终确认的 relaxed 数据；优化顺序是：先硬约束，后其它约束。")

st.latex(r"z = k_{\mathrm{color}} \cdot \beta \cdot \left(\frac{P}{P_0}\right) \cdot \left(\frac{d_0}{d}\right)^{\gamma} \cdot \ln\left(\frac{t}{t_0}\right)")
st.latex(r"\text{Stage 1: } \min \mathcal{L}_{hard} \qquad \text{Stage 2: 在 }\mathcal{L}_{hard}\text{达标后，再优化 } w_{soft}\mathcal{L}_{soft}+w_{vol}\mathcal{L}_{vol}+\lambda R")

left, right = st.columns(2)
with left:
    st.subheader("固定点约束")
    fixed_df = st.data_editor(default_fixed_points_df(), use_container_width=True, num_rows="dynamic", key="fixed_df_simple")
    st.caption("当前默认固定点使用你最终确认的 relaxed_points 数据：13 个单点。")
with right:
    st.subheader("范围约束（中心硬约束，点云软约束）")
    range_df = st.data_editor(default_range_df(), use_container_width=True, num_rows="dynamic", key="range_df_simple")
    st.markdown(
        "<div class='small-note'>范围记录会在长方体/线段范围内采样点云；中心点用于硬约束，点云用于软约束。当前默认范围数据使用你最终确认的 relaxed_ranges：4 条；2-3 已统一按 2 级处理。</div>",
        unsafe_allow_html=True,
    )

if fit_button:
    fixed_points = parse_fixed_points(fixed_df)
    ranged = parse_ranges(range_df)
    init_params = {
        "beta": init_beta,
        "gamma": init_gamma,
        "p0": init_p0,
        "d0": init_d0,
        "t0_ms": init_t0,
    }

    contradictions_df = find_hard_contradictions(fixed_df, range_df)

    progress_bar = st.progress(0.0, text="准备开始拟合…")
    status = st.empty()

    def _progress(i: int, total: int, stage_name: str) -> None:
        frac = min(max(i / max(total, 1), 0.0), 1.0)
        stage_text = "阶段1：硬约束搜索" if "stage1" in stage_name else "阶段2：其它约束优化"
        if i >= total:
            stage_text = "拟合完成"
        progress_bar.progress(frac, text=f"{stage_text}（进度 {min(i, total)}/{total}）")
        status.caption("当前策略：只有硬约束全部达标后，才会继续优化软约束、体积均衡和正则项。")

    result = fit_parameters(
        fixed_points=fixed_points,
        ranged=ranged,
        color_factor=color_factor,
        shell_frac=shell_frac,
        shell_n=shell_n,
        range_soft_n=range_soft_n,
        volume_train_n=volume_train_n,
        volume_eval_n=volume_eval_n,
        hard_margin=hard_margin,
        soft_margin=soft_margin,
        soft_weight=soft_weight,
        volume_weight=volume_weight,
        smooth_k=smooth_k,
        reg_weight=reg_weight,
        restarts=restarts,
        init_params=init_params,
        seed=int(random_seed),
        hard_loss_tol=float(hard_loss_tol),
        hard_barrier_weight=float(hard_barrier_weight),
        progress_callback=_progress,
    )
    progress_bar.progress(1.0, text="拟合完成")
    status.empty()
    st.session_state["fit_result_simple_formula"] = result
    st.session_state["fit_fixed_df"] = fixed_df.copy()
    st.session_state["fit_range_df"] = range_df.copy()
    st.session_state["fit_contradictions_df"] = contradictions_df.copy()


result = st.session_state.get("fit_result_simple_formula")
used_fixed_df = st.session_state.get("fit_fixed_df")
used_range_df = st.session_state.get("fit_range_df")
contradictions_df = st.session_state.get("fit_contradictions_df")

if result is not None:
    metrics = result["evaluation"]["metrics"]
    params = result["evaluation"]["params"]
    t1, t2, t3 = metrics["t1"], metrics["t2"], metrics["t3"]

    if result.get("stage1_hard_feasible", False):
        st.success("阶段1已经先把硬约束全部满足，阶段2才继续优化软约束和体积均衡。")
    else:
        st.error("阶段1未能把硬约束全部满足，所以脚本已停止在“硬约束优先”阶段，没有继续优化其它约束。")

    if contradictions_df is not None and len(contradictions_df):
        st.warning(f"检测到 {len(contradictions_df)} 组单调性冲突：在当前公式下，存在“参数更强但标签更低”的硬约束，这会导致 100% 硬约束命中在数学上不可行。")
        with st.expander("查看冲突约束"):
            st.dataframe(contradictions_df, use_container_width=True)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(f'<div class="metric-card"><b>硬约束命中</b><br><span style="font-size:1.4rem">{metrics["hard_ok_count"]}/{metrics["hard_total"]}</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><b>固定点软命中率</b><br><span style="font-size:1.4rem">{metrics["fixed_shell_mean"]:.1%}</span></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><b>范围点云软命中率</b><br><span style="font-size:1.4rem">{metrics["range_cloud_mean"]:.1%}</span></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><b>区域1/2</b><br><span style="font-size:1.15rem">{metrics["volume_frac_1"]:.1%} / {metrics["volume_frac_2"]:.1%}</span></div>', unsafe_allow_html=True)
    with c5:
        st.markdown(f'<div class="metric-card"><b>区域3/4</b><br><span style="font-size:1.15rem">{metrics["volume_frac_3"]:.1%} / {metrics["volume_frac_4"]:.1%}</span></div>', unsafe_allow_html=True)
    with c6:
        st.markdown(f'<div class="metric-card"><b>硬损失 / 阈值</b><br><span style="font-size:1.0rem">{metrics["hard_loss"]:.3e}<br>{t1:.3f} / {t2:.3f} / {t3:.3f}</span></div>', unsafe_allow_html=True)

    st.markdown(
        f"<div class='small-note'>当前阶段：{result['stage']}。拟合结果：β={params['beta']:.4f}，γ={params['gamma']:.4f}，P₀={params['p0']:.2f}mW，d₀={params['d0']:.2f}μm，t₀={params['t0_ms']:.2f}ms，k_color={color_factor:.3f}。四级阈值：t1={t1:.4f}，t2={t2:.4f}，t3={t3:.4f}</div>",
        unsafe_allow_html=True,
    )

    volume_df = make_volume_sample_df(display_sample_n, int(random_seed) + 2026)
    volume_df["score"] = score_formula(
        volume_df["power"].to_numpy(),
        volume_df["time_ms"].to_numpy(),
        volume_df["spot"].to_numpy(),
        color_factor=color_factor,
        **params,
    )
    volume_df["region"] = predict_region_from_score(volume_df["score"].to_numpy(), t1, t2, t3)
    volume_df["region_name"] = volume_df["region"].map(region_name)

    constraint_centers = pd.concat(
        [
            result["evaluation"]["fixed_df"][["power", "spot", "time_ms", "target_label"]],
            result["evaluation"]["range_df"][["power", "spot", "time_ms", "target_label"]],
        ],
        ignore_index=True,
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["3D 采样", "等值面", "等值切面图", "约束结果", "采样数据"])
    with tab1:
        st.plotly_chart(make_scatter_3d(volume_df, constraint_centers), use_container_width=True)
        st.plotly_chart(make_histogram(volume_df, t1, t2, t3), use_container_width=True)
    with tab2:
        st.plotly_chart(make_isosurfaces(params, color_factor, t1, t2, t3, iso_grid_n), use_container_width=True)
        st.caption("这里显示的是三张分界等值面，分别对应四级分区的三个阈值。")
    with tab3:
        st.plotly_chart(make_iso_slice_plot(params, color_factor, t1, t2, t3, fixed_spot, slice_grid_n), use_container_width=True)
        st.caption("这是你要的等值切面图：固定一个光斑后，在功率-时间平面上同时显示四个区域和三条等值线。")
    with tab4:
        st.subheader("拟合时实际使用的固定点")
        if used_fixed_df is not None:
            st.dataframe(used_fixed_df, use_container_width=True)
        st.subheader("拟合时实际使用的范围约束")
        if used_range_df is not None:
            st.dataframe(used_range_df, use_container_width=True)
        st.subheader("固定点命中结果")
        st.dataframe(result["evaluation"]["fixed_df"], use_container_width=True)
        st.subheader("范围中心命中结果")
        st.dataframe(result["evaluation"]["range_df"], use_container_width=True)
    with tab5:
        st.dataframe(volume_df.head(2000), use_container_width=True, height=420)
        csv = volume_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("下载当前采样 CSV", csv, file_name="laser_fit_samples_simple_formula.csv", mime="text/csv")
else:
    st.info("先在左侧调整约束和权重，然后点击“开始拟合”。")
