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


# ------------------------------
# GT boxes from earlier discussion
# Mapping: I->区域1, II->区域2, II-III->区域3, III->区域4
# ------------------------------
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
        name="GT3 / III级",
        label="区域3",
        power_min=150.0,
        power_max=350.0,
        time_min=100.0,
        time_max=200.0,
        spot_min=500.0,
        spot_max=500.0,
        color_nm=532.0,
        note="对应 532 nm, 500 μm, 0.1–0.2 s, 150–350 mW, III级",
    ),
]


# ------------------------------
# Core formula
# ------------------------------
def score_formula(power_mw, time_ms, spot_um, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor):
    """
    z = ln(t/t0) + beta * k_color * (P/P0) * (d0/d)^gamma * (1 - exp(-(t/1000)/tau))

    Inputs:
      power_mw : mW
      time_ms  : ms
      spot_um  : um
      color_factor : scalar multiplier for green/yellow/red
    """
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



def make_histogram(df, t1, t2, t3):
    fig = px.histogram(
        df,
        x="score",
        nbins=70,
        color="region",
        opacity=0.8,
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
        x="power_mW",
        y="time_ms",
        z="spot_um",
        color="region",
        size="marker_size",
        size_max=9,
        opacity=0.65,
        title="3D 参数空间随机采样（按阈值分区）",
        labels={
            "power_mW": "功率 (mW)",
            "time_ms": "时间 (ms)",
            "spot_um": "光斑 (μm)",
            "region": "分区",
            "marker_size": "点大小",
        },
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
    values = [t1, t2, t3]
    names = ["阈值1等值面", "阈值2等值面", "阈值3等值面"]
    colors = ["Blues", "Viridis", "Reds"]

    for v, name, cs in zip(values, names, colors):
        fig.add_trace(
            go.Isosurface(
                x=P.flatten(),
                y=T.flatten(),
                z=D.flatten(),
                value=Z.flatten(),
                isomin=v,
                isomax=v,
                surface_count=1,
                opacity=0.22,
                caps=dict(x_show=False, y_show=False, z_show=False),
                colorscale=cs,
                showscale=False,
                name=name,
            )
        )

    fig.update_layout(
        title="阈值对应的三张等值面",
        height=620,
        scene=dict(
            xaxis_title="功率 (mW)",
            yaxis_title="时间 (ms)",
            zaxis_title="光斑 (μm)",
        ),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig



def make_slice_heatmap(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor, t1, t2, t3, fixed_spot, grid_n):
    p = np.linspace(rng.power_min, rng.power_max, grid_n)
    tm = np.linspace(rng.time_min, rng.time_max, grid_n)
    P, T = np.meshgrid(p, tm, indexing="xy")
    Z = score_formula(P, T, fixed_spot, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor)

    fig = go.Figure(
        data=go.Contour(
            x=p,
            y=tm,
            z=Z,
            contours=dict(showlabels=True),
            colorbar=dict(title="z"),
        )
    )
    for val, label in [(t1, "阈值1"), (t2, "阈值2"), (t3, "阈值3")]:
        fig.add_trace(
            go.Contour(
                x=p,
                y=tm,
                z=Z,
                contours=dict(coloring="none", showlines=True, start=val, end=val, size=1),
                line=dict(width=3),
                showscale=False,
                name=label,
            )
        )
    fig.update_layout(
        title=f"固定光斑 = {fixed_spot:.1f} μm 时的功率-时间切片",
        xaxis_title="功率 (mW)",
        yaxis_title="时间 (ms)",
        height=500,
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig



def sample_gt_boxes(gt_boxes, *, beta, tau_s, gamma, p0, d0, t0_ms, color_factor, n_each, seed):
    rng_np = np.random.default_rng(seed)
    rows = []
    summary_rows = []

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
        gt_df = pd.DataFrame(
            {
                "gt_name": box.name,
                "target_region": box.label,
                "power_mW": power,
                "time_ms": time_ms,
                "spot_um": spot_um,
                "score": score,
                "note": box.note,
            }
        )
        rows.append(gt_df)

    gt_all = pd.concat(rows, ignore_index=True)
    return gt_all



def make_gt_fit_figure(gt_df, t1, t2, t3):
    fig = px.box(
        gt_df,
        x="gt_name",
        y="score",
        color="target_region",
        points="all",
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
        counts.values,
        x=counts.columns,
        y=counts.index,
        text_auto=False,
        aspect="auto",
        color_continuous_scale="Blues",
        labels=dict(x="预测区域", y="GT盒子", color="占比"),
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

ranges = Range3D(
    power_min=50.0,
    power_max=500.0,
    time_min=50.0,
    time_max=500.0,
    spot_min=10.0,
    spot_max=500.0,
)

st.sidebar.markdown("**参数范围（固定）**")
st.sidebar.write(f"功率：{ranges.power_min:.0f}–{ranges.power_max:.0f} mW")
st.sidebar.write(f"时间：{ranges.time_min:.0f}–{ranges.time_max:.0f} ms")
st.sidebar.write(f"光斑：{ranges.spot_min:.0f}–{ranges.spot_max:.0f} μm")

with st.sidebar.expander("光颜色设置", expanded=True):
    color_label = st.selectbox("激光颜色", COLOR_LABELS, index=0)
    green_k = st.slider("绿光系数 k_green", 0.10, 3.00, 1.00, 0.01)
    yellow_k = st.slider("黄光系数 k_yellow", 0.10, 3.00, 1.35, 0.01)
    red_k = st.slider("红光系数 k_red", 0.10, 3.00, 0.70, 0.01)
    color_factors = {"green": green_k, "yellow": yellow_k, "red": red_k}
    color_key = COLOR_KEY_MAP[color_label]
    color_factor = color_factors[color_key]
    st.caption(f"当前使用：{color_label}，k_color = {color_factor:.2f}")

with st.sidebar.expander("公式参数", expanded=True):
    beta = st.slider("β（热损伤权重）", 0.01, 30.0, 4.0, 0.01)
    tau_s = st.slider("τ（热弛豫时间，秒）", 0.001, 1.0, 0.08, 0.001)
    gamma = st.slider("γ（光斑指数）", 0.1, 3.0, 2.0, 0.1)
    p0 = st.slider("P₀（功率归一化，mW）", 10.0, 500.0, 100.0, 5.0)
    d0 = st.slider("d₀（光斑归一化，μm）", 10.0, 500.0, 100.0, 5.0)
    t0_ms = st.slider("t₀（时间归一化，ms）", 10.0, 500.0, 100.0, 5.0)

z_min, z_max = score_min_max(
    ranges,
    beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor
)

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

if "t1" not in st.session_state:
    st.session_state.t1 = _t1
if "t2" not in st.session_state:
    st.session_state.t2 = _t2
if "t3" not in st.session_state:
    st.session_state.t3 = _t3

st.session_state.t1 = float(np.clip(st.session_state.t1, z_min, z_max))
st.session_state.t2 = float(np.clip(st.session_state.t2, st.session_state.t1 + 1e-6, z_max))
st.session_state.t3 = float(np.clip(st.session_state.t3, st.session_state.t2 + 1e-6, z_max))

if auto_equal:
    auto_seed = int(np.random.randint(0, 1_000_000_000))
    q1, q2, q3 = equal_volume_thresholds(
        ranges,
        beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor,
        n_samples=auto_equal_n, seed=auto_seed
    )
    st.session_state.t1 = float(np.clip(q1, z_min, z_max))
    st.session_state.t2 = float(np.clip(q2, st.session_state.t1 + 1e-6, z_max))
    st.session_state.t3 = float(np.clip(q3, st.session_state.t2 + 1e-6, z_max))

# Bind sliders directly to session_state keys so auto-solve writes are not overridden by stale widget state.
st.session_state.t1 = float(np.clip(st.session_state.t1, z_min, z_max))
st.session_state.t2 = float(np.clip(st.session_state.t2, st.session_state.t1 + 0.001, z_max))
st.session_state.t3 = float(np.clip(st.session_state.t3, st.session_state.t2 + 0.001, z_max))

st.sidebar.slider("阈值 1", float(z_min), float(z_max), float(st.session_state.t1), 0.001, key="t1")
st.sidebar.slider("阈值 2", float(st.session_state.t1 + 0.001), float(z_max), float(st.session_state.t2), 0.001, key="t2")
st.sidebar.slider("阈值 3", float(st.session_state.t2 + 0.001), float(z_max), float(st.session_state.t3), 0.001, key="t3")

t1 = float(st.session_state.t1)
t2 = float(st.session_state.t2)
t3 = float(st.session_state.t3)

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


# ------------------------------
# Sample the space uniformly
# ------------------------------
rng = np.random.default_rng(st.session_state.seed)
power = rng.uniform(ranges.power_min, ranges.power_max, size=sample_n)
time_ms = rng.uniform(ranges.time_min, ranges.time_max, size=sample_n)
spot_um = rng.uniform(ranges.spot_min, ranges.spot_max, size=sample_n)
score = score_formula(
    power, time_ms, spot_um,
    beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms, color_factor=color_factor
)
region = classify_scores(score, t1, t2, t3)

df = pd.DataFrame(
    {
        "power_mW": power,
        "time_ms": time_ms,
        "spot_um": spot_um,
        "score": score,
        "region": region,
        "color_name": color_label,
    }
)

region_counts = df["region"].value_counts().reindex(REGION_ORDER).fillna(0).astype(int)

# GT evaluation
# power lower bound 0 in GT1 is allowed for fitting display; formula handles it.
gt_df = sample_gt_boxes(
    GT_BOXES,
    beta=beta,
    tau_s=tau_s,
    gamma=gamma,
    p0=p0,
    d0=d0,
    t0_ms=t0_ms,
    color_factor=color_factor,
    n_each=gt_n_each,
    seed=st.session_state.seed + 7,
)
gt_df["pred_region"] = classify_scores(gt_df["score"].to_numpy(), t1, t2, t3)
gt_df["fit_ok"] = gt_df["pred_region"] == gt_df["target_region"]

gt_summary = (
    gt_df.groupby(["gt_name", "target_region", "pred_region"], as_index=False)
    .size()
    .rename(columns={"size": "样本数", "gt_name": "GT盒子", "pred_region": "预测区域"})
)

total_per_gt = gt_df.groupby("gt_name").size().rename("总数")
gt_summary = gt_summary.merge(total_per_gt, left_on="GT盒子", right_index=True)
gt_summary["占比"] = gt_summary["样本数"] / gt_summary["总数"]

gt_fit_rate = (
    gt_df.groupby(["gt_name", "target_region"], as_index=False)["fit_ok"].mean()
    .rename(columns={"gt_name": "GT盒子", "target_region": "目标区域", "fit_ok": "命中率"})
)


# ------------------------------
# Main layout
# ------------------------------
st.title("激光热作用阈值探索器（颜色版）")
st.caption("在原有颜色版基础上，新增 GT 盒子拟合展示：查看早前整理的几个 GT 参数盒子在当前阈值下是否落入目标区域。")

formula_text = r"""
z = \, \ln\left(\frac{t}{t_0}\right)
+ \beta \, k_{\mathrm{color}}
\left(\frac{P}{P_0}\right)
\left(\frac{d_0}{d}\right)^{\gamma}
\left(1-e^{-\frac{t/1000}{\tau}}\right)
"""
st.latex(formula_text)

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(f'<div class="metric-card"><b>当前颜色</b><br><span style="font-size:1.2rem">{color_label}</span></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="metric-card"><b>颜色系数</b><br><span style="font-size:1.5rem">{color_factor:.3f}</span></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="metric-card"><b>公式最小值</b><br><span style="font-size:1.5rem">{z_min:.4f}</span></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="metric-card"><b>公式最大值</b><br><span style="font-size:1.5rem">{z_max:.4f}</span></div>', unsafe_allow_html=True)
with c5:
    st.markdown(f'<div class="metric-card"><b>阈值</b><br><span style="font-size:1.2rem">{t1:.3f} / {t2:.3f} / {t3:.3f}</span></div>', unsafe_allow_html=True)

spread = np.percentile(score, 95) - np.percentile(score, 5)
st.markdown(
    f"<div class='small-note'>当前参数：颜色={color_label}，k_color={color_factor:.3f}，β={beta:.3f}，τ={tau_s:.3f} s，γ={gamma:.3f}，P₀={p0:.1f} mW，d₀={d0:.1f} μm，t₀={t0_ms:.1f} ms，P95-P5={spread:.4f}</div>",
    unsafe_allow_html=True,
)

st.caption("点击左侧“自动求解：四区等体积”后，会用均匀随机采样估计 score 的 25% / 50% / 75% 分位数，将三维参数盒子近似均分成四块。GT拟合图用于检查早前几个参考参数盒子是否能被当前阈值和区域定义合理接住。")

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
    fig_scatter = make_scatter_3d(df.sample(min(len(df), 6000), random_state=42))
    st.plotly_chart(fig_scatter, use_container_width=True)
    fig_hist = make_histogram(df, t1, t2, t3)
    st.plotly_chart(fig_hist, use_container_width=True)

with tab2:
    st.plotly_chart(
        make_isosurfaces(
            ranges,
            beta=beta,
            tau_s=tau_s,
            gamma=gamma,
            p0=p0,
            d0=d0,
            t0_ms=t0_ms,
            color_factor=color_factor,
            t1=t1,
            t2=t2,
            t3=t3,
            grid_n=iso_grid_n,
        ),
        use_container_width=True,
    )
    st.caption("这里显示的是 3 个阈值对应的等值面；它们不是严格意义上的平面，而是由公式值决定的三张分界曲面。")

with tab3:
    st.plotly_chart(
        make_slice_heatmap(
            ranges,
            beta=beta,
            tau_s=tau_s,
            gamma=gamma,
            p0=p0,
            d0=d0,
            t0_ms=t0_ms,
            color_factor=color_factor,
            t1=t1,
            t2=t2,
            t3=t3,
            fixed_spot=fixed_spot,
            grid_n=slice_grid_n,
        ),
        use_container_width=True,
    )
    st.caption("切片图更适合观察功率-时间平面上，给定光斑直径时各阈值线的位置。")

with tab4:
    st.plotly_chart(make_gt_fit_figure(gt_df, t1, t2, t3), use_container_width=True)
    st.plotly_chart(make_gt_confusion_heatmap(gt_summary), use_container_width=True)
    st.dataframe(gt_fit_rate, use_container_width=True)
    gt_notes = pd.DataFrame(
        {"GT盒子": [b.name for b in GT_BOXES], "目标区域": [b.label for b in GT_BOXES], "说明": [b.note for b in GT_BOXES]}
    )
    st.dataframe(gt_notes, use_container_width=True)
    st.caption("命中率 = 在对应 GT 盒子里均匀采样后，落入目标区域的比例。若某个 GT 盒子大量跨越多条阈值线，说明当前公式或阈值对它拟合较差。")

with tab5:
    summary = pd.DataFrame(
        {
            "区域": REGION_ORDER,
            "样本数": [int(region_counts[x]) for x in REGION_ORDER],
            "占比": [float(region_counts[x] / sample_n) for x in REGION_ORDER],
            "score_均值": [
                float(df.loc[df["region"] == x, "score"].mean()) if (df["region"] == x).any() else np.nan
                for x in REGION_ORDER
            ],
        }
    )
    st.dataframe(summary, use_container_width=True)
    st.dataframe(df.head(1000), use_container_width=True, height=360)
    st.dataframe(gt_df.head(1000), use_container_width=True, height=360)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("下载当前随机样本 CSV", csv, file_name="laser_threshold_samples_color.csv", mime="text/csv")
    gt_csv = gt_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("下载 GT 采样 CSV", gt_csv, file_name="laser_threshold_gt_fit.csv", mime="text/csv")

st.markdown("---")
st.markdown(
    """
    **使用建议**
    - 先固定颜色，只拖动 3 个阈值，观察 4 个区域在 3D 参数空间里是否分层自然。
    - 切到 **GT拟合** 标签页，看 4 个 GT 盒子的 score 分布是否分别落在目标区域附近。
    - 如果某个 GT 盒子的命中率始终很低，优先检查：颜色系数、γ（光斑指数）、τ（时间饱和）、阈值位置。
    - GT拟合图用于看“当前物理计算层是否接住已知参考点”；视觉形态是否像真实光斑，仍由你的渲染层负责。
    """
)
