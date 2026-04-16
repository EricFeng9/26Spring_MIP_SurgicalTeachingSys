import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Arrhenius 物理模型 3D 验证", layout="wide")
st.title("🔥 阿伦尼乌斯热损伤积分 (Arrhenius Integral) 空间切分")
st.markdown("真正的生物物理引擎！拖动左侧滑块，调节蛋白质变性的 $\\log(\\Omega)$ 阈值。")

# ================= 1. 物理常数与生成 GT 点云 =================
KAPPA_CONST = 2240.0  # 16 * 0.14 * 1000
E_EFF = 40.0          # 吸收效率
BASE_TEMP = 37.0      # 基础体温

@st.cache_data
def generate_gt_data():
    gt_definitions = [
        ('P1 (Grade II - Standard)', 80, 150, 150, 250, 200, 200, '#2ecc71'), # 绿点
        ('P2 (Grade I - Light)',  50, 100,  50, 100,  50, 100, '#3498db'), # 蓝点
        ('P4 (Grade III - Intense)', 150, 350, 450, 550, 100, 200, '#e74c3c'), # 红点
        ('P5 (Grade III - Broad)', 100, 500, 50, 500, 50, 500, '#e74c3c')   # 红点 (大范围)
    ]
    
    np.random.seed(42)
    samples = []
    for row in gt_definitions:
        name, p_min, p_max, s_min, s_max, t_min, t_max, color = row
        num_samples = 300 
        P = np.random.uniform(p_min, p_max, num_samples)
        S = np.random.uniform(s_min, s_max, num_samples) if s_min != s_max else np.full(num_samples, s_min)
        T = np.random.uniform(t_min, t_max, num_samples) if t_min != t_max else np.full(num_samples, t_min)
        
        for i in range(num_samples):
            samples.append({'Protocol': name, 'Power': P[i], 'SpotSize': S[i], 'Time': T[i], 'Color': color})
            
    return pd.DataFrame(samples)

df = generate_gt_data()

# ================= 2. 侧边栏 UI 滑块 =================
st.sidebar.header("🎛️ 损伤指数 $\\log(\\Omega)$ 阈值")
st.sidebar.markdown("寻找切分真实点云的完美物理边界：")

# 根据真实计算推测，合理的范围在 0 到 30 之间
t1 = st.sidebar.slider("T1 (I / II 刚泛白)", min_value=-5.0, max_value=15.0, value=5.0, step=0.5)
t2 = st.sidebar.slider("T2 (II / III 强水肿)", min_value=5.0, max_value=25.0, value=15.0, step=0.5)
t3 = st.sidebar.slider("T3 (III / IV 碳化/破裂)", min_value=15.0, max_value=40.0, value=25.0, step=0.5)

# ================= 3. 构建 Plotly 3D =================
fig = go.Figure()

# A. 绘制极小数据散点，避免遮挡
for name, group in df.groupby('Protocol'):
    fig.add_trace(go.Scatter3d(
        x=group['Power'], y=group['Time'], z=group['SpotSize'],
        mode='markers', name=name,
        marker=dict(size=1.5, color=group['Color'].iloc[0], opacity=0.7, line=dict(width=0)),
        hovertemplate='<b>%{name}</b><br>P: %{x:.1f} mW<br>T: %{y:.1f} ms<br>S: %{z:.1f} μm<extra></extra>'
    ))

# B. 解析物理公式生成曲面 (以 T 和 S 为底，求 P)
T_grid, S_grid = np.meshgrid(np.linspace(10, 500, 40), np.linspace(50, 550, 40))
tau_grid = (S_grid ** 2) / KAPPA_CONST

def add_physics_surface(threshold, name, colorscale):
    # 1. 目标峰值温度 (开尔文)
    denom = 120.0 + np.log(T_grid) - threshold
    denom[denom <= 0] = 1e-6 # 防止除零
    T_peak_k = 40000.0 / denom
    
    # 2. 目标温升 (摄氏度)
    T_rise = T_peak_k - 273.15 - BASE_TEMP
    T_rise[T_rise < 0] = np.nan # 达不到阈值的区域掏空
    
    # 3. 反推所需功率 P
    P_surf = (T_rise * S_grid) / (E_EFF * (1.0 - np.exp(-T_grid / tau_grid)))
    
    # 将功率限制在物理范围内
    P_surf[P_surf < 50] = np.nan
    P_surf[P_surf > 600] = np.nan
    
    # 注意：这里的 x, y, z 映射要与散点云对应 (X=Power, Y=Time, Z=SpotSize)
    fig.add_trace(go.Surface(
        x=P_surf, y=T_grid, z=S_grid,
        name=name, opacity=0.4,
        colorscale=colorscale, showscale=False, hoverinfo='skip'
    ))

add_physics_surface(t1, 'T1 (I/II 边界)', 'Blues')
add_physics_surface(t2, 'T2 (II/III 边界)', 'Greens')
add_physics_surface(t3, 'T3 (III/IV 边界)', 'Reds')

# C. 场景设置
fig.update_layout(
    scene=dict(
        xaxis_title='功率 Power (mW)',
        yaxis_title='时间 Time (ms)',
        zaxis_title='光斑 Spot Size (μm)',
        xaxis=dict(backgroundcolor="rgb(240, 240, 240)", range=[50, 600]),
        yaxis=dict(backgroundcolor="rgb(240, 240, 240)", range=[10, 500]),
        zaxis=dict(backgroundcolor="rgb(240, 240, 240)", range=[50, 550]),
        camera=dict(eye=dict(x=1.5, y=-1.8, z=0.6))
    ),
    margin=dict(l=0, r=0, b=0, t=0),
    height=750,
    legend=dict(x=0.02, y=0.98, bgcolor='rgba(255, 255, 255, 0.8)')
)

st.plotly_chart(fig, use_container_width=True)