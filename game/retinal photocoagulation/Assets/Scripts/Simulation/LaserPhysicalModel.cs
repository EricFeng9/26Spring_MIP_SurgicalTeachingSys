using UnityEngine;
using System;

// 对应你 JSON 里的 gt_parameters
[Serializable]
public class TaskParams
{
    public float power = 200.0f;
    public float spot_size = 200.0f;
    public float exposure_time = 100.0f;
    public float wavelength = 532.0f;
}

public class LaserPhysicalModel
{
    public TaskParams gt;
    
    // 物理参数常量
    private float beta_E = 1.2f;
    private float beta_T = 0.5f;
    private float T_ref = 100.0f;
    
    // 分级阈值
    private float tau_0 = 1.0f;
    private float tau_1 = 2.0f;
    private float tau_2 = 3.0f;
    
    private float z_target;
    private float beta_0; 

    public LaserPhysicalModel(TaskParams gtParams)
    {
        this.gt = gtParams ?? new TaskParams();
        
        this.z_target = (this.tau_1 + this.tau_2) / 2.0f;
        float raw_z_gt = ComputeRawZ(gt.power, gt.spot_size, gt.exposure_time, gt.wavelength);
        this.beta_0 = this.z_target - raw_z_gt;
    }

    private float GetLambdaFactor(float wavelength)
    {
        return Mathf.Approximately(wavelength, 532.0f) ? 0.0f : -0.4f;
    }

    private float ComputeRawZ(float P, float S, float T, float lam)
    {
        if (S <= 0 || P <= 0 || T <= 0) return -999f;
        
        // C# 中的 Mathf.Log 默认就是以 e 为底的自然对数 (对应 math.log)
        float energy_term = beta_E * Mathf.Log((P * T) / (S * S));
        float time_term = beta_T * Mathf.Log(T / T_ref);
        float lam_term = GetLambdaFactor(lam);
        
        return energy_term + time_term + lam_term;
    }

    public (float z, int grade) ComputeZAndGrade(float P, float S, float T, float lam)
    {
        float z = beta_0 + ComputeRawZ(P, S, T, lam);
        
        if (z < tau_0) return (z, 1);
        else if (z < tau_1) return (z, 2);
        else if (z < tau_2) return (z, 3);
        else return (z, 4);
    }
}