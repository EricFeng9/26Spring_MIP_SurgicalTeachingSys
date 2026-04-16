import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ------------------------------
# Page config and lightweight styling
# ------------------------------
st.set_page_config(
    page_title="激光热作用阈值探索器",
    page_icon="🧪",
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


# ------------------------------
# Core formula
# ------------------------------
def score_formula(power_mw, time_ms, spot_um, *, beta, tau_s, gamma, p0, d0, t0_ms):
    """
    Simplified thermo-bio interaction score.

    z = ln(t/t0) + beta * (P/P0) * (d0/d)^gamma * (1 - exp(-(t/1000)/tau))

    Inputs:
      power_mw : mW
      time_ms  : ms
      spot_um  : um
    """
    t_s = np.asarray(time_ms, dtype=float) / 1000.0
    p = np.asarray(power_mw, dtype=float)
    d = np.asarray(spot_um, dtype=float)

    # Guard against any accidental zero values.
    t_term = np.log(np.maximum(np.asarray(time_ms, dtype=float), 1e-9) / t0_ms)
    heat_term = beta * (p / p0) * (d0 / d) ** gamma * (1.0 - np.exp(-t_s / tau_s))
    return t_term + heat_term


@dataclass
class Range3D:
    power_min: float = 50.0
    power_max: float = 500.0
    time_min: float = 50.0
    time_max: float = 500.0
    spot_min: float = 10.0
    spot_max: float = 500.0


def score_min_max(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms):
    # Under this monotonic model:
    # z increases with power and time, decreases with spot diameter.
    z_min = score_formula(
        rng.power_min, rng.time_min, rng.spot_max,
        beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms
    )
    z_max = score_formula(
        rng.power_max, rng.time_max, rng.spot_min,
        beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms
    )
    return float(z_min), float(z_max)




def equal_volume_thresholds(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms, n_samples, seed):
    """Monte Carlo estimate of thresholds that split the 3D parameter space into four equal-volume regions.
    Since sampling is uniform over the box, score quartiles approximate equal volume partitions.
    """
    rng_np = np.random.default_rng(seed)
    power = rng_np.uniform(rng.power_min, rng.power_max, size=n_samples)
    time_ms = rng_np.uniform(rng.time_min, rng.time_max, size=n_samples)
    spot_um = rng_np.uniform(rng.spot_min, rng.spot_max, size=n_samples)
    score = score_formula(power, time_ms, spot_um, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms)
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
        # Plotly 的 marker.size 不能为负，因此把 score 线性映射到一个正区间。
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
        hover_data={"score": ':.4f', "marker_size": False},
    )
    fig.update_layout(height=620, legend_title_text="分区")
    return fig


def make_isosurfaces(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms, t1, t2, t3, grid_n):
    p = np.linspace(rng.power_min, rng.power_max, grid_n)
    tm = np.linspace(rng.time_min, rng.time_max, grid_n)
    d = np.linspace(rng.spot_min, rng.spot_max, grid_n)
    P, T, D = np.meshgrid(p, tm, d, indexing="ij")
    Z = score_formula(P, T, D, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms)

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


def make_slice_heatmap(rng: Range3D, *, beta, tau_s, gamma, p0, d0, t0_ms, t1, t2, t3, fixed_spot, grid_n):
    p = np.linspace(rng.power_min, rng.power_max, grid_n)
    tm = np.linspace(rng.time_min, rng.time_max, grid_n)
    P, T = np.meshgrid(p, tm, indexing="xy")
    Z = score_formula(P, T, fixed_spot, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms)

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

with st.sidebar.expander("公式参数", expanded=True):
    beta = st.slider("β（热损伤权重）", 0.01, 30.0, 4.0, 0.01)
    tau_s = st.slider("τ（热弛豫时间，秒）", 0.001, 1.0, 0.08, 0.001)
    gamma = st.slider("γ（光斑指数）", 0.1, 3.0, 2.0, 0.1)
    p0 = st.slider("P₀（功率归一化，mW）", 10.0, 500.0, 100.0, 5.0)
    d0 = st.slider("d₀（光斑归一化，μm）", 10.0, 500.0, 100.0, 5.0)
    t0_ms = st.slider("t₀（时间归一化，ms）", 10.0, 500.0, 100.0, 5.0)

z_min, z_max = score_min_max(
    ranges,
    beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms
)

st.sidebar.markdown("---")
st.sidebar.markdown("**阈值设置**")
st.sidebar.caption("三个阈值的范围自动限定为当前公式在参数范围内的最小值到最大值。")
auto_equal_n = st.sidebar.slider("自动均分采样数", 2000, 200000, 50000, 2000)
auto_equal = st.sidebar.button("自动求解：四区等体积")

# Create ordered threshold sliders.
def default_thresholds(zmin, zmax):
    span = zmax - zmin
    return zmin + 0.25 * span, zmin + 0.5 * span, zmin + 0.75 * span

if z_max <= z_min:
    z_max = z_min + 1e-6

_t1, _t2, _t3 = default_thresholds(z_min, z_max)

# Persist values across reruns while keeping them valid.
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
        beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms,
        n_samples=auto_equal_n, seed=auto_seed
    )
    st.session_state.t1 = float(np.clip(q1, z_min, z_max))
    st.session_state.t2 = float(np.clip(q2, st.session_state.t1 + 1e-6, z_max))
    st.session_state.t3 = float(np.clip(q3, st.session_state.t2 + 1e-6, z_max))

t1 = st.sidebar.slider("阈值 1", float(z_min), float(z_max), float(st.session_state.t1), 0.001)
t2 = st.sidebar.slider("阈值 2", float(t1 + 0.001), float(z_max), float(max(st.session_state.t2, t1 + 0.001)), 0.001)
t3 = st.sidebar.slider("阈值 3", float(t2 + 0.001), float(z_max), float(max(st.session_state.t3, t2 + 0.001)), 0.001)

st.session_state.t1 = t1
st.session_state.t2 = t2
st.session_state.t3 = t3

st.sidebar.markdown("---")
with st.sidebar.expander("可视化精度", expanded=False):
    sample_n = st.slider("随机采样点数", 1000, 40000, 8000, 500)
    iso_grid_n = st.slider("等值面网格密度", 8, 28, 16, 1)
    slice_grid_n = st.slider("切片网格密度", 30, 180, 90, 10)
    fixed_spot = st.slider("切片固定光斑（μm）", ranges.spot_min, ranges.spot_max, 100.0, 1.0)

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
score = score_formula(power, time_ms, spot_um, beta=beta, tau_s=tau_s, gamma=gamma, p0=p0, d0=d0, t0_ms=t0_ms)
region = classify_scores(score, t1, t2, t3)

df = pd.DataFrame(
    {
        "power_mW": power,
        "time_ms": time_ms,
        "spot_um": spot_um,
        "score": score,
        "region": region,
    }
)

region_counts = df["region"].value_counts().reindex(["区域1", "区域2", "区域3", "区域4"]).fillna(0).astype(int)


# ------------------------------
# Main layout
# ------------------------------
st.title("激光热作用阈值探索器")
st.caption("使用简化热相互作用公式，在功率/时间/光斑三维参数空间里手动调整 3 个阈值，观察分区边界是否“好看”。")

formula_text = r"""
z = \, \ln\left(\frac{t}{t_0}\right)
+ \beta \left(\frac{P}{P_0}\right)
\left(\frac{d_0}{d}\right)^{\gamma}
\left(1-e^{-\frac{t/1000}{\tau}}\right)
"""
st.latex(formula_text)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="metric-card"><b>公式最小值</b><br><span style="font-size:1.5rem">{z_min:.4f}</span></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="metric-card"><b>公式最大值</b><br><span style="font-size:1.5rem">{z_max:.4f}</span></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="metric-card"><b>阈值</b><br><span style="font-size:1.2rem">{t1:.3f} / {t2:.3f} / {t3:.3f}</span></div>', unsafe_allow_html=True)
with c4:
    spread = np.percentile(score, 95) - np.percentile(score, 5)
    st.markdown(f'<div class="metric-card"><b>P95-P5</b><br><span style="font-size:1.5rem">{spread:.4f}</span></div>', unsafe_allow_html=True)

st.markdown(
    f"<div class='small-note'>当前参数：β={beta:.3f}，τ={tau_s:.3f} s，γ={gamma:.3f}，P₀={p0:.1f} mW，d₀={d0:.1f} μm，t₀={t0_ms:.1f} ms</div>",
    unsafe_allow_html=True,
)

st.caption("点击左侧“自动求解：四区等体积”后，会用均匀随机采样估计 score 的 25% / 50% / 75% 分位数，将三维参数盒子近似均分成四块。")

stat_cols = st.columns(4)
for idx, lab in enumerate(["区域1", "区域2", "区域3", "区域4"]):
    with stat_cols[idx]:
        st.metric(lab, f"{region_counts[lab]}", f"{region_counts[lab] / sample_n:.1%}")

tab1, tab2, tab3, tab4 = st.tabs(["3D 采样", "等值面", "切片", "数据表"])

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
    summary = pd.DataFrame(
        {
            "区域": ["区域1", "区域2", "区域3", "区域4"],
            "样本数": [int(region_counts[x]) for x in ["区域1", "区域2", "区域3", "区域4"]],
            "占比": [float(region_counts[x] / sample_n) for x in ["区域1", "区域2", "区域3", "区域4"]],
            "score_均值": [
                float(df.loc[df["region"] == x, "score"].mean()) if (df["region"] == x).any() else np.nan
                for x in ["区域1", "区域2", "区域3", "区域4"]
            ],
        }
    )
    st.dataframe(summary, use_container_width=True)
    st.dataframe(df.head(1000), use_container_width=True, height=420)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("下载当前随机样本 CSV", csv, file_name="laser_threshold_samples.csv", mime="text/csv")

st.markdown("---")
st.markdown(
    """
    **使用建议**
    - 先固定公式参数，只拖动 3 个阈值，观察 4 个区域在 3D 参数空间里是否分层自然。
    - 如果等值面弯曲过强或几乎挤在一起，优先调 `β`、`τ`、`γ`。
    - 如果你只想手动“切得好看”，最直观的是同时看 **等值面** 和 **固定光斑切片** 两个标签页。
    """
)
