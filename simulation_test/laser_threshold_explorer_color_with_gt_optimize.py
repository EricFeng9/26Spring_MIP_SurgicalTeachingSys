import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="激光热作用阈值探索器（颜色版+GT拟合）",
    page_icon="🌈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.1rem; padding-bottom: 1.4rem;}
    .metric-card {
        background: linear-gradient(135deg, rgba(99,102,241,0.08), rgba(16,185,129,0.08));
        border: 1px solid rgba(99,102,241,0.12);
        border-radius: 18px;
        padding: 14px 16px;
        margin-bottom: 8px;
    }
    .small-note {color: rgba(100,116,139,1); font-size: 0.9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


COLOR_LABELS = ["绿光", "黄光", "红光"]
COLOR_KEY_MAP = {"绿光": "green", "黄光": "yellow", "红光": "red"}
REGION_ORDER = ["区域1", "区域2", "区域3", "区域4"]


@dataclass
class Range3D:
    power_min: float = 50.0
    power_max: float = 500.0
    time_min: float = 50.0
    time_max: float = 500.0
    spot_min: float = 10.0
    spot_max: float = 500.0


@dataclass
class GTBox:
    name: str
    label: str
    power_min: float
    power_max: float
    time_min: float
    time_max: float
    spot_min: float
    spot_max: float
    color_nm: float | None = None
    note: str = ""


GT_BOXES = [
    GTBox(
        name="GT1 / I级",
        label="区域1",
        power_min=0.0,
        power_max=100.0,
        time_min=50.0,
        time_max=100.0,
        spot_min=50.0,
        spot_max=100.0,
        color_nm=None,
        note="对应早前整理的一级光斑规则：50–100 μm, 0.05–0.1 s, ≤100 mW",
    ),
    GTBox(
        name="GT2 / II级",
        label="区域2",
        power_min=80.0,
        power_max=150.0,
        time_min=200.0,
        time_max=200.0,
        spot_min=200.0,
        spot_max=200.0,
        color_nm=532.0,
        note="对应 532 nm, 200 μm, 0.2 s, 80–150 mW, II级",
    ),
    GTBox(
        name="GT4 / III级",
        label="区域3",
        power_min=150.0,
        power_max=350.0,
        time_min=100.0,
        time_max=200.0,
        spot_min=500.0,
        spot_max=500.0,
        color_nm=532.0,
        note="对应 532 nm, 500 μm, 0.1–0.2 s, 150–350 mW；当前按区域3处理",
    ),
]


# ------------------------------
# Core formula
# ------------------------------
def score_formula(power_mw, time_ms, spot_um, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor):
    t_s = np.asarray(time_ms, dtype=float) / 1000.0
    p = np.asarray(power_mw, dtype=float)
    d = np.asarray(spot_um, dtype=float)
    t_term = np.log(np.maximum(np.asarray(time_ms, dtype=float), 1e-9) / t0_ms)
    heat_term = beta * color_factor * (p / p0) * (d0 / d) ** gamma * (1.0 - np.exp(-t_s / tau_s))
    return t_term + heat_term


def score_min_max(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor):
    z_min = score_formula(
        rng.power_min, rng.time_min, rng.spot_max,
        beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor
    )
    z_max = score_formula(
        rng.power_max, rng.time_max, rng.spot_min,
        beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor
    )
    return float(z_min), float(z_max)


def equal_volume_thresholds(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor, n_samples, seed):
    rng_np = np.random.default_rng(seed)
    power = rng_np.uniform(rng.power_min, rng.power_max, size=n_samples)
    time_ms = rng_np.uniform(rng.time_min, rng.time_max, size=n_samples)
    spot_um = rng_np.uniform(rng.spot_min, rng.spot_max, size=n_samples)
    score = score_formula(
        power, time_ms, spot_um,
        beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor
    )
    t1, t2, t3 = np.quantile(score, [0.25, 0.50, 0.75])
    return float(t1), float(t2), float(t3)


def classify_scores(z, t1, t2, t3):
    labels = np.empty_like(z, dtype=object)
    labels[z < t1] = "区域1"
    labels[(z >= t1) & (z < t2)] = "区域2"
    labels[(z >= t2) & (z < t3)] = "区域3"
    labels[z >= t3] = "区域4"
    return labels


def sample_gt_boxes(gt_boxes, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor, n_each, seed):
    rng_np = np.random.default_rng(seed)
    rows = []
    for box in gt_boxes:
        power = rng_np.uniform(box.power_min, box.power_max, size=n_each)
        time_ms = rng_np.uniform(box.time_min, box.time_max, size=n_each)
        spot_um = rng_np.uniform(box.spot_min, box.spot_max, size=n_each)
        score = score_formula(
            power,
            time_ms,
            spot_um,
            beta=beta,
            tau_s=tau_s,
            gamma=gamma,
            p0=p0,
            d0=d0,
            t0_ms=t0_ms,
            color_factor=color_factor,
        )
        rows.append(pd.DataFrame({
            "gt_name": box.name,
            "target_region": box.label,
            "power_mW": power,
            "time_ms": time_ms,
            "spot_um": spot_um,
            "score": score,
            "note": box.note,
        }))
    return pd.concat(rows, ignore_index=True)


def prepare_gt_random_boxes(gt_boxes, n_each, seed):
    rng_np = np.random.default_rng(seed)
    prepared = []
    for box in gt_boxes:
        prepared.append({
            "box": box,
            "u_p": rng_np.random(n_each),
            "u_t": rng_np.random(n_each),
            "u_d": rng_np.random(n_each),
        })
    return prepared


def evaluate_gt_hit_rate(prepared_boxes, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor, t1, t2, t3):
    total = 0
    correct = 0
    per_box = []
    for item in prepared_boxes:
        box = item["box"]
        power = box.power_min + (box.power_max - box.power_min) * item["u_p"]
        time_ms = box.time_min + (box.time_max - box.time_min) * item["u_t"]
        spot_um = box.spot_min + (box.spot_max - box.spot_min) * item["u_d"]
        score = score_formula(
            power, time_ms, spot_um,
            beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor
        )
        pred = classify_scores(np.asarray(score), t1, t2, t3)
        ok = pred == box.label
        hit = float(np.mean(ok))
        per_box.append((box.name, box.label, hit))
        total += len(pred)
        correct += int(np.sum(ok))
    overall = correct / total if total else 0.0
    box_mean = float(np.mean([x[2] for x in per_box])) if per_box else 0.0
    return overall, box_mean, per_box


def random_search_formula_params(prepared_boxes, *, color_factor, t1, t2, t3,
                                 beta_bounds, tau_bounds, gamma_bounds,
                                 p0_bounds, d0_bounds, t0_bounds,
                                 n_trials, seed, optimize_norms):
    rng_np = np.random.default_rng(seed)
    best = None
    for _ in range(n_trials):
        beta = rng_np.uniform(*beta_bounds)
        tau_s = 10 ** rng_np.uniform(np.log10(tau_bounds[0]), np.log10(tau_bounds[1]))
        gamma = rng_np.uniform(*gamma_bounds)
        if optimize_norms:
            p0 = rng_np.uniform(*p0_bounds)
            d0 = rng_np.uniform(*d0_bounds)
            t0_ms = rng_np.uniform(*t0_bounds)
        else:
            p0 = p0_bounds[0]
            d0 = d0_bounds[0]
            t0_ms = t0_bounds[0]

        overall, box_mean, per_box = evaluate_gt_hit_rate(
            prepared_boxes,
            beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms,
            color_factor=color_factor, t1=t1, t2=t2, t3=t3,
        )
        score_tuple = (box_mean, overall)
        if best is None or score_tuple > best["score_tuple"]:
            best = {
                "beta": float(beta),
                "tau_s": float(tau_s),
                "gamma": float(gamma),
                "p0": float(p0),
                "d0": float(d0),
                "t0_ms": float(t0_ms),
                "overall": float(overall),
                "box_mean": float(box_mean),
                "per_box": per_box,
                "score_tuple": score_tuple,
            }
    return best


def make_histogram(df, t1, t2, t3):
    fig = px.histogram(
        df, x="score", nbins=70, color="region", opacity=0.8,
        title="公式值分布与阈值",
        labels={"score": "公式值 z", "count": "样本数", "region": "分区"},
    )
    for value, name in [(t1, "阈值1"), (t2, "阈值2"), (t3, "阈值3")]:
        fig.add_vline(x=value, line_width=2, line_dash="dash", annotation_text=name)
    fig.update_layout(height=400, legend_title_text="分区")
    return fig


def make_scatter_3d(df):
    plot_df = df.copy()
    smin = float(plot_df["score"].min())
    smax = float(plot_df["score"].max())
    if smax - smin < 1e-12:
        plot_df["marker_size"] = 5.0
    else:
        plot_df["marker_size"] = 3.0 + 6.0 * (plot_df["score"] - smin) / (smax - smin)
    fig = px.scatter_3d(
        plot_df,
        x="power_mW", y="time_ms", z="spot_um", color="region", size="marker_size", size_max=9,
        opacity=0.65, title="3D 参数空间随机采样（按阈值分区）",
        labels={"power_mW": "功率 (mW)", "time_ms": "时间 (ms)", "spot_um": "光斑 (μm)", "region": "分区", "marker_size": "点大小"},
        hover_data={"score": ':.4f', "marker_size": False, "color_name": True},
    )
    fig.update_layout(height=620, legend_title_text="分区")
    return fig


def make_isosurfaces(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor, t1, t2, t3, grid_n):
    p = np.linspace(rng.power_min, rng.power_max, grid_n)
    tm = np.linspace(rng.time_min, rng.time_max, grid_n)
    d = np.linspace(rng.spot_min, rng.spot_max, grid_n)
    P, T, D = np.meshgrid(p, tm, d, indexing="ij")
    Z = score_formula(P, T, D, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor)
    fig = go.Figure()
    for v, name, cs in zip([t1, t2, t3], ["阈值1等值面", "阈值2等值面", "阈值3等值面"], ["Blues", "Viridis", "Reds"]):
        fig.add_trace(go.Isosurface(
            x=P.flatten(), y=T.flatten(), z=D.flatten(), value=Z.flatten(),
            isomin=v, isomax=v, surface_count=1, opacity=0.22,
            caps=dict(x_show=False, y_show=False, z_show=False), colorscale=cs,
            showscale=False, name=name,
        ))
    fig.update_layout(
        title="阈值对应的三张等值面", height=620,
        scene=dict(xaxis_title="功率 (mW)", yaxis_title="时间 (ms)", zaxis_title="光斑 (μm)"),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig


def make_slice_heatmap(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor, t1, t2, t3, fixed_spot, grid_n):
    p = np.linspace(rng.power_min, rng.power_max, grid_n)
    tm = np.linspace(rng.time_min, rng.time_max, grid_n)
    P, T = np.meshgrid(p, tm, indexing="xy")
    Z = score_formula(P, T, fixed_spot, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor)
    fig = go.Figure(data=go.Contour(x=p, y=tm, z=Z, contours=dict(showlabels=True), colorbar=dict(title="z")))
    for val, label in [(t1, "阈值1"), (t2, "阈值2"), (t3, "阈值3")]:
        fig.add_trace(go.Contour(
            x=p, y=tm, z=Z,
            contours=dict(coloring="none", showlines=True, start=val, end=val, size=1),
            line=dict(width=3), showscale=False, name=label,
        ))
    fig.update_layout(
        title=f"固定光斑 = {fixed_spot:.1f} μm 时的功率-时间切片",
        xaxis_title="功率 (mW)", yaxis_title="时间 (ms)", height=500,
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig


def make_gt_fit_figure(gt_df, t1, t2, t3):
    fig = px.box(
        gt_df, x="gt_name", y="score", color="target_region", points="all",
        hover_data={"power_mW": ':.1f', "time_ms": ':.1f', "spot_um": ':.1f', "target_region": True},
        title="GT盒子采样后的 score 分布（带阈值线）",
        labels={"gt_name": "GT盒子", "score": "公式值 z", "target_region": "目标区域"},
    )
    for value, name in [(t1, "阈值1"), (t2, "阈值2"), (t3, "阈值3")]:
        fig.add_hline(y=value, line_width=2, line_dash="dash", annotation_text=name)
    fig.update_layout(height=560, xaxis_title="GT盒子", yaxis_title="公式值 z")
    return fig


def make_gt_confusion_heatmap(summary_df):
    counts = summary_df.pivot(index="GT盒子", columns="预测区域", values="占比").reindex(columns=REGION_ORDER).fillna(0)
    text = (counts * 100).round(1).astype(str) + "%"
    fig = px.imshow(
        counts.values, x=counts.columns, y=counts.index, text_auto=False, aspect="auto",
        color_continuous_scale="Blues", labels=dict(x="预测区域", y="GT盒子", color="占比"),
        title="GT盒子 → 预测区域 占比热图",
    )
    for i in range(counts.shape[0]):
        for j in range(counts.shape[1]):
            fig.add_annotation(x=j, y=i, text=text.iloc[i, j], showarrow=False, font=dict(size=12))
    fig.update_layout(height=420)
    return fig


# ------------------------------
# Sidebar controls
# ------------------------------
st.sidebar.header("参数设置")

ranges = Range3D(power_min=50.0, power_max=500.0, time_min=50.0, time_max=500.0, spot_min=10.0, spot_max=500.0)
st.sidebar.markdown("**参数范围（固定）**")
st.sidebar.write(f"功率：{ranges.power_min:.0f}–{ranges.power_max:.0f} mW")
st.sidebar.write(f"时间：{ranges.time_min:.0f}–{ranges.time_max:.0f} ms")
st.sidebar.write(f"光斑：{ranges.spot_min:.0f}–{ranges.spot_max:.0f} μm")

for key, val in {
    "beta": 4.0,
    "tau_s": 0.08,
    "gamma": 2.0,
    "p0": 100.0,
    "d0": 100.0,
    "t0_ms": 100.0,
}.items():
    st.session_state.setdefault(key, val)

with st.sidebar.expander("光颜色设置", expanded=True):
    color_label = st.selectbox("激光颜色", COLOR_LABELS, index=0)
    green_k = st.slider("绿光系数 k_green", 0.10, 3.00, 1.00, 0.01)
    yellow_k = st.slider("黄光系数 k_yellow", 0.10, 3.00, 1.35, 0.01)
    red_k = st.slider("红光系数 k_red", 0.10, 3.00, 0.70, 0.01)
    color_factors = {"green": green_k, "yellow": yellow_k, "red": red_k}
    color_factor = color_factors[COLOR_KEY_MAP[color_label]]
    st.caption(f"当前使用：{color_label}，k_color = {color_factor:.2f}")

with st.sidebar.expander("公式参数", expanded=True):
    beta = st.slider("β（热损伤权重）", 0.01, 30.0, float(st.session_state.beta), 0.01)
    tau_s = st.slider("τ（热弛豫时间，秒）", 0.001, 1.0, float(st.session_state.tau_s), 0.001)
    gamma = st.slider("γ（光斑指数）", 0.1, 3.0, float(st.session_state.gamma), 0.1)
    p0 = st.slider("P₀（功率归一化，mW）", 10.0, 500.0, float(st.session_state.p0), 5.0)
    d0 = st.slider("d₀（光斑归一化，μm）", 10.0, 500.0, float(st.session_state.d0), 5.0)
    t0_ms = st.slider("t₀（时间归一化，ms）", 10.0, 500.0, float(st.session_state.t0_ms), 5.0)

st.session_state.beta = beta
st.session_state.tau_s = tau_s
st.session_state.gamma = gamma
st.session_state.p0 = p0
st.session_state.d0 = d0
st.session_state.t0_ms = t0_ms

z_min, z_max = score_min_max(ranges, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor)

st.sidebar.markdown("---")
st.sidebar.markdown("**阈值设置**")
st.sidebar.caption("三个阈值的范围自动限定为当前公式在参数范围内的最小值到最大值。")
auto_equal_n = st.sidebar.slider("自动均分采样数", 2000, 200000, 50000, 2000)
auto_equal = st.sidebar.button("自动求解：四区等体积")


def default_thresholds(zmin, zmax):
    span = zmax - zmin
    return zmin + 0.25 * span, zmin + 0.5 * span, zmin + 0.75 * span


if z_max <= z_min:
    z_max = z_min + 1e-6

_t1, _t2, _t3 = default_thresholds(z_min, z_max)
st.session_state.setdefault("t1", _t1)
st.session_state.setdefault("t2", _t2)
st.session_state.setdefault("t3", _t3)

st.session_state.t1 = float(np.clip(st.session_state.t1, z_min, z_max))
st.session_state.t2 = float(np.clip(st.session_state.t2, st.session_state.t1 + 1e-6, z_max))
st.session_state.t3 = float(np.clip(st.session_state.t3, st.session_state.t2 + 1e-6, z_max))

if auto_equal:
    q1, q2, q3 = equal_volume_thresholds(
        ranges, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms,
        color_factor=color_factor, n_samples=auto_equal_n, seed=int(np.random.randint(0, 1_000_000_000))
    )
    st.session_state.t1 = float(np.clip(q1, z_min, z_max))
    st.session_state.t2 = float(np.clip(q2, st.session_state.t1 + 1e-6, z_max))
    st.session_state.t3 = float(np.clip(q3, st.session_state.t2 + 1e-6, z_max))

t1 = st.sidebar.slider("阈值 1", float(z_min), float(z_max), float(st.session_state.t1), 0.001)
t2 = st.sidebar.slider("阈值 2", float(t1 + 0.001), float(z_max), float(max(st.session_state.t2, t1 + 0.001)), 0.001)
t3 = st.sidebar.slider("阈值 3", float(t2 + 0.001), float(z_max), float(max(st.session_state.t3, t2 + 0.001)), 0.001)
st.session_state.t1, st.session_state.t2, st.session_state.t3 = t1, t2, t3

st.sidebar.markdown("---")
with st.sidebar.expander("自动拟合公式参数（固定当前阈值）", expanded=False):
    opt_trials = st.slider("搜索次数", 100, 5000, 1200, 100)
    opt_gt_each = st.slider("每个GT盒子用于拟合的采样数", 100, 3000, 600, 100)
    optimize_norms = st.checkbox("同时优化 P₀ / d₀ / t₀", value=False)
    beta_bounds = st.slider("β搜索范围", 0.01, 30.0, (0.5, 12.0), 0.01)
    tau_bounds = st.slider("τ搜索范围（秒）", 0.001, 1.0, (0.005, 0.2), 0.001)
    gamma_bounds = st.slider("γ搜索范围", 0.1, 3.0, (0.5, 2.5), 0.1)
    if optimize_norms:
        p0_bounds = st.slider("P₀搜索范围", 10.0, 500.0, (50.0, 200.0), 5.0)
        d0_bounds = st.slider("d₀搜索范围", 10.0, 500.0, (50.0, 200.0), 5.0)
        t0_bounds = st.slider("t₀搜索范围", 10.0, 500.0, (50.0, 200.0), 5.0)
    else:
        p0_bounds = (float(p0), float(p0))
        d0_bounds = (float(d0), float(d0))
        t0_bounds = (float(t0_ms), float(t0_ms))
    auto_fit_params = st.button("自动修改公式参数，让GT命中尽可能多")

st.sidebar.markdown("---")
with st.sidebar.expander("可视化精度", expanded=False):
    sample_n = st.slider("随机采样点数", 1000, 40000, 8000, 500)
    iso_grid_n = st.slider("等值面网格密度", 8, 28, 16, 1)
    slice_grid_n = st.slider("切片网格密度", 30, 180, 90, 10)
    fixed_spot = st.slider("切片固定光斑（μm）", ranges.spot_min, ranges.spot_max, 100.0, 1.0)
    gt_n_each = st.slider("每个GT盒子采样数", 200, 5000, 1000, 100)

reseed = st.sidebar.button("重新随机采样")
if reseed or "seed" not in st.session_state:
    st.session_state.seed = np.random.randint(0, 1_000_000_000)

if auto_fit_params:
    prepared = prepare_gt_random_boxes(GT_BOXES, n_each=opt_gt_each, seed=st.session_state.seed + 12345)
    best = random_search_formula_params(
        prepared,
        color_factor=color_factor,
        t1=t1, t2=t2, t3=t3,
        beta_bounds=beta_bounds, tau_bounds=tau_bounds, gamma_bounds=gamma_bounds,
        p0_bounds=p0_bounds, d0_bounds=d0_bounds, t0_bounds=t0_bounds,
        n_trials=opt_trials, seed=st.session_state.seed + 54321,
        optimize_norms=optimize_norms,
    )
    st.session_state.beta = best["beta"]
    st.session_state.tau_s = best["tau_s"]
    st.session_state.gamma = best["gamma"]
    st.session_state.p0 = best["p0"]
    st.session_state.d0 = best["d0"]
    st.session_state.t0_ms = best["t0_ms"]
    st.session_state["last_fit_result"] = best
    st.rerun()

# Use last fit result for display if available
last_fit_result = st.session_state.get("last_fit_result")

# ------------------------------
# Sample the space uniformly
# ------------------------------
rng = np.random.default_rng(st.session_state.seed)
power = rng.uniform(ranges.power_min, ranges.power_max, size=sample_n)
time_ms = rng.uniform(ranges.time_min, ranges.time_max, size=sample_n)
spot_um = rng.uniform(ranges.spot_min, ranges.spot_max, size=sample_n)
score = score_formula(power, time_ms, spot_um, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor)
region = classify_scores(score, t1, t2, t3)
df = pd.DataFrame({"power_mW": power, "time_ms": time_ms, "spot_um": spot_um, "score": score, "region": region, "color_name": color_label})
region_counts = df["region"].value_counts().reindex(REGION_ORDER).fillna(0).astype(int)

gt_df = sample_gt_boxes(GT_BOXES, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor, n_each=gt_n_each, seed=st.session_state.seed + 7)
gt_df["pred_region"] = classify_scores(gt_df["score"].to_numpy(), t1, t2, t3)
gt_df["fit_ok"] = gt_df["pred_region"] == gt_df["target_region"]

gt_summary = gt_df.groupby(["gt_name", "target_region", "pred_region"], as_index=False).size().rename(columns={"size": "样本数", "gt_name": "GT盒子", "pred_region": "预测区域"})
total_per_gt = gt_df.groupby("gt_name").size().rename("总数")
gt_summary = gt_summary.merge(total_per_gt, left_on="GT盒子", right_index=True)
gt_summary["占比"] = gt_summary["样本数"] / gt_summary["总数"]
gt_fit_rate = gt_df.groupby(["gt_name", "target_region"], as_index=False)["fit_ok"].mean().rename(columns={"gt_name": "GT盒子", "target_region": "目标区域", "fit_ok": "命中率"})
overall_gt_fit = float(gt_df["fit_ok"].mean()) if len(gt_df) else 0.0
mean_box_fit = float(gt_fit_rate["命中率"].mean()) if len(gt_fit_rate) else 0.0

# ------------------------------
# Main layout
# ------------------------------
st.title("激光热作用阈值探索器（颜色版）")
st.caption("在原有颜色版基础上，新增 GT 盒子拟合展示；当前保留 GT1、GT2、GT4，其中 GT4 目标区域已改为区域3。")

st.latex(r"""
z = \, \ln\left(\frac{t}{t_0}\right)
+ \beta \, k_{\mathrm{color}}
\left(\frac{P}{P_0}\right)
\left(\frac{d_0}{d}\right)^{\gamma}
\left(1-e^{-\frac{t/1000}{\tau}}\right)
""")

c1, c2, c3, c4, c5, c6 = st.columns(6)
for col, title, value in [
    (c1, "当前颜色", color_label),
    (c2, "颜色系数", f"{color_factor:.3f}"),
    (c3, "公式最小值", f"{z_min:.4f}"),
    (c4, "公式最大值", f"{z_max:.4f}"),
    (c5, "阈值", f"{t1:.3f} / {t2:.3f} / {t3:.3f}"),
    (c6, "GT总命中率", f"{overall_gt_fit:.1%}"),
]:
    with col:
        st.markdown(f'<div class="metric-card"><b>{title}</b><br><span style="font-size:1.2rem">{value}</span></div>', unsafe_allow_html=True)

spread = np.percentile(score, 95) - np.percentile(score, 5)
st.markdown(
    f"<div class='small-note'>当前参数：颜色={color_label}，k_color={color_factor:.3f}，β={beta:.3f}，τ={tau_s:.3f} s，γ={gamma:.3f}，P₀={p0:.1f} mW，d₀={d0:.1f} μm，t₀={t0_ms:.1f} ms，P95-P5={spread:.4f}，GT盒子平均命中率={mean_box_fit:.1%}</div>",
    unsafe_allow_html=True,
)
if last_fit_result:
    st.info(
        "最近一次自动拟合结果："
        f"GT盒子平均命中率={last_fit_result['box_mean']:.1%}，总体命中率={last_fit_result['overall']:.1%}；"
        f"β={last_fit_result['beta']:.3f}，τ={last_fit_result['tau_s']:.4f}，γ={last_fit_result['gamma']:.3f}"
        + (f"，P₀={last_fit_result['p0']:.1f}，d₀={last_fit_result['d0']:.1f}，t₀={last_fit_result['t0_ms']:.1f}" if optimize_norms else "")
    )

stat_cols = st.columns(4)
for idx, lab in enumerate(REGION_ORDER):
    with stat_cols[idx]:
        st.metric(lab, f"{region_counts[lab]}", f"{region_counts[lab] / sample_n:.1%}")

fit_cols = st.columns(len(GT_BOXES))
fit_rate_map = dict(zip(gt_fit_rate["GT盒子"], gt_fit_rate["命中率"]))
for idx, box in enumerate(GT_BOXES):
    with fit_cols[idx]:
        st.metric(box.name, f"{fit_rate_map.get(box.name, 0.0):.1%}", box.label)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["3D 采样", "等值面", "切片", "GT拟合", "数据表"])
with tab1:
    st.plotly_chart(make_scatter_3d(df.sample(min(len(df), 6000), random_state=42)), use_container_width=True)
    st.plotly_chart(make_histogram(df, t1, t2, t3), use_container_width=True)
with tab2:
    st.plotly_chart(make_isosurfaces(ranges, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor, t1=t1, t2=t2, t3=t3, grid_n=iso_grid_n), use_container_width=True)
    st.caption("这里显示的是 3 个阈值对应的等值面；它们不是严格意义上的平面，而是由公式值决定的三张分界曲面。")
with tab3:
    st.plotly_chart(make_slice_heatmap(ranges, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor, t1=t1, t2=t2, t3=t3, fixed_spot=fixed_spot, grid_n=slice_grid_n), use_container_width=True)
    st.caption("切片图更适合观察功率-时间平面上，给定光斑直径时各阈值线的位置。")
with tab4:
    st.plotly_chart(make_gt_fit_figure(gt_df, t1, t2, t3), use_container_width=True)
    st.plotly_chart(make_gt_confusion_heatmap(gt_summary), use_container_width=True)
    st.dataframe(gt_fit_rate, use_container_width=True)
    gt_notes = pd.DataFrame({"GT盒子": [b.name for b in GT_BOXES], "目标区域": [b.label for b in GT_BOXES], "说明": [b.note for b in GT_BOXES]})
    st.dataframe(gt_notes, use_container_width=True)
    st.caption("命中率 = 在对应 GT 盒子里均匀采样后，落入目标区域的比例。自动拟合按钮会固定当前阈值，搜索公式参数，让这些命中率尽量升高。")
with tab5:
    summary = pd.DataFrame({
        "区域": REGION_ORDER,
        "样本数": [int(region_counts[x]) for x in REGION_ORDER],
        "占比": [float(region_counts[x] / sample_n) for x in REGION_ORDER],
        "score_均值": [float(df.loc[df["region"] == x, "score"].mean()) if (df["region"] == x).any() else np.nan for x in REGION_ORDER],
    })
    st.dataframe(summary, use_container_width=True)
    st.dataframe(df.head(1000), use_container_width=True, height=320)
    st.dataframe(gt_df.head(1000), use_container_width=True, height=320)
    st.download_button("下载当前随机样本 CSV", df.to_csv(index=False).encode("utf-8-sig"), file_name="laser_threshold_samples_color.csv", mime="text/csv")
    st.download_button("下载 GT 采样 CSV", gt_df.to_csv(index=False).encode("utf-8-sig"), file_name="laser_threshold_gt_fit.csv", mime="text/csv")

st.markdown("---")
st.markdown(
    """
    **使用建议**
    - 先固定颜色，只拖动 3 个阈值，观察 4 个区域在 3D 参数空间里是否分层自然。
    - GT4 现在按 **区域3** 统计，不再保留 GT3 / II-III级 盒子。
    - 需要提高 GT 命中率时，优先点左侧 **自动修改公式参数**。它固定当前阈值，只搜索公式参数。
    - GT拟合图用于看“当前物理计算层是否接住已知参考点”；视觉形态是否像真实光斑，仍由你的渲染层负责。
    """
)
