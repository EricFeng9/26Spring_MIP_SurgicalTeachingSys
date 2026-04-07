using UnityEngine;

// 这是一个纯数据逻辑类，不需要挂载到任何游戏物体上 (不需要继承 MonoBehaviour)
public class LaserPhysicsModel
{
    // 物理参数范围 (与你的 UI 滑条对应)
    public readonly float[] powerRange = { 50f, 400f };
    public readonly float[] spotRange = { 50f, 400f };
    public readonly float[] durationRange = { 10f, 500f };
    public readonly float[] wavelengths = { 532f, 577f, 672f };

    // 核心权重参数 (与 Python 保持一致)
    private float beta_E = 1.2f;
    private float beta_T = 0.5f;
    private float beta_0 = 0.0f; // 病例偏置

    // 渲染锚点
    public float render_z_min = -2.0f;
    public float render_z_max = 4.5f;

    // 分级阈值
    private float tau_0, tau_1, tau_2;

    // 构造函数：初始化时自动计算分布阈值
    public LaserPhysicsModel(float z_bias = 0.0f)
    {
        this.beta_0 = z_bias;
        InitializeThresholds();
    }

    private void InitializeThresholds()
    {
        // 这里为了 Unity 运行效率，我们使用你 Python 原本逻辑跑出来的近似统计均值
        // 避免在游戏启动时做巨大的 25x25x25 循环遍历
        float mu = 1.2f;   // 原始Z值的近似均值
        float sigma = 1.5f; // 原始Z值的近似标准差

        // 基于正态分布的四分位数近似计算 (Z-scores for 25%, 50%, 75%)
        // -0.674, 0.0, +0.674 对应正态分布的 25%, 50%, 75% 分位点
        tau_0 = mu + sigma * (-0.674f);
        tau_1 = mu;
        tau_2 = mu + sigma * (0.674f);

        Debug.Log($"物理引擎初始化完成. 阈值: t0={tau_0:F2}, t1={tau_1:F2}, t2={tau_2:F2}");
    }

    private float GetLambdaFactor(float wavelength)
    {
        if (Mathf.Approximately(wavelength, 532f)) return 0.0f;
        if (Mathf.Approximately(wavelength, 577f)) return 0.18f;
        if (Mathf.Approximately(wavelength, 672f)) return -0.35f;
        return 0.0f;
    }

    private float ComputeRawZ(float P, float S, float T, float lam)
    {
        if (S <= 0 || P <= 0 || T <= 0) return -999f;
        
        // 核心对数物理公式：z = beta_E * ln((P*T)/S^2) + beta_T * ln(P/S^2) + lam_factor
        float energyTerm = beta_E * Mathf.Log((P * T) / (S * S));
        float densityTerm = beta_T * Mathf.Log(P / (S * S));
        float lamTerm = GetLambdaFactor(lam);
        
        return energyTerm + densityTerm + lamTerm;
    }

    // ==========================================
    // 外部调用的核心接口
    // 返回值：(连续的Z值, 离散的光斑等级 1-4)
    // ==========================================
    public (float zValue, int grade) ComputeZAndGrade(float P, float S, float T, float lam)
    {
        float z = beta_0 + ComputeRawZ(P, S, T, lam);
        
        int grade = 1;
        if (z < tau_0) grade = 1;
        else if (z < tau_1) grade = 2;
        else if (z < tau_2) grade = 3;
        else grade = 4;

        return (z, grade);
    }

    public float GetRenderVisibility(float z)
    {
        if (render_z_max <= render_z_min) return 1.0f;
        float vis = (z - render_z_min) / (render_z_max - render_z_min);
        return Mathf.Clamp01(vis); // Clamp01 限制在 0.0 到 1.0 之间
    }
}