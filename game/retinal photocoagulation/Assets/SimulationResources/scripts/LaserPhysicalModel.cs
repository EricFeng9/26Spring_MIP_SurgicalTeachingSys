using System;
using UnityEngine;

public enum LaserMode
{
    Single = 0,
    Matrix = 1
}

public enum LaserPulseMode
{
    SinglePulse = 0,
    Repeat = 1
}

public enum MatrixShape
{
    Square = 0,
    Line = 1,
    Triangle = 2,
    Circle = 3,
    QuarterCircle = 4,
    HalfCircle = 5
}

public enum TreatmentFundusLens
{
    Goldmann = 0,
    Krieger = 1,
    Panfundoscope = 2,
    Mainster = 3
}

[Serializable]
public struct LaserShotParameters
{
    public LaserMode mode;
    public float wavelengthNm;
    public float powerMw;
    public float durationMs;
    public LaserPulseMode pulseMode;
    public float intervalSeconds;
    public float spotSizeUm;
    public TreatmentFundusLens fundusLens;
    public float aimingBeamLevel;
    public bool titrateMode;

    public MatrixShape shape;
    public int shapeParam;
    public float spacingXSpot;
    public float rotationDeg;
    public float offsetDx;
    public float offsetDy;
}

public struct LaserShotMetrics
{
    public float zValue;
    public int grade;
    public float normalizedIntensity;
    public float gradeProgress01;

    public float effectiveRadiusPx;
    public float appearanceStrength;
}

public class LaserPhysicalModel
{
    // 你的公式对应的固定分级阈值
    public const float Grade1Upper = 2.989f;
    public const float Grade2Upper = 4.820f;
    public const float Grade3Upper = 7.026f;
    private const float SpotRadiusRenderScale = 1.5f;

    private readonly float beta0;

    public LaserPhysicalModel(float zBias = 0f)
    {
        beta0 = zBias;
    }

    public LaserShotMetrics Compute(LaserShotParameters p, float pixelToUm)
    {
        float beamRadiusPx = Mathf.Max(1f, p.spotSizeUm * GetLensFactor(p.fundusLens) * 0.5f / Mathf.Max(pixelToUm, 1e-6f));

        float z = ComputeFormulaZ(p.powerMw, p.spotSizeUm, p.durationMs, p.wavelengthNm, p.titrateMode) + beta0;
        int grade = ComputeGrade(z);
        float gradeProgress01 = ComputeGradeProgress01(z, grade);
        float intensity = ComputeNormalizedIntensity(z);

        float radiusScale;
        switch (grade)
        {
            case 1:
                radiusScale = Mathf.Lerp(0.84f, 0.98f, gradeProgress01);
                break;
            case 2:
                radiusScale = Mathf.Lerp(0.98f, 1.12f, gradeProgress01);
                break;
            case 3:
                radiusScale = Mathf.Lerp(1.12f, 1.28f, gradeProgress01);
                break;
            default:
                radiusScale = Mathf.Lerp(1.26f, 1.48f, Mathf.SmoothStep(0f, 1f, gradeProgress01));
                break;
        }

        return new LaserShotMetrics
        {
            zValue = z,
            grade = grade,
            normalizedIntensity = intensity,
            gradeProgress01 = gradeProgress01,
            effectiveRadiusPx = Mathf.Max(1f, beamRadiusPx * radiusScale * SpotRadiusRenderScale),
            appearanceStrength = Mathf.Lerp(0.24f, 1f, intensity)
        };
    }

    public static float GetLensFactor(TreatmentFundusLens lens)
    {
        switch (lens)
        {
            case TreatmentFundusLens.Goldmann: return 1.08f;
            case TreatmentFundusLens.Krieger: return 1.53f;
            case TreatmentFundusLens.Panfundoscope: return 1.41f;
            case TreatmentFundusLens.Mainster: return 1.05f;
            default: return 1.08f;
        }
    }

    public static float GetColorCoefficient(float wavelengthNm)
    {
        if (ApproximatelyNm(wavelengthNm, 577f)) return 1.08f;
        if (ApproximatelyNm(wavelengthNm, 659f)) return 0.72f;
        return 1.00f; // 532nm baseline
    }

    public float ComputeFormulaZ(float powerMw, float spotSizeUm, float durationMs, float wavelengthNm, bool titrateMode)
    {
        if (powerMw <= 0f || durationMs <= 0f || spotSizeUm <= 0f)
            return -999f;

        float p = powerMw * (titrateMode ? 0.92f : 1f);
        float t = Mathf.Max(1e-4f, durationMs);
        float d = Mathf.Max(1e-4f, spotSizeUm);
        float kColor = GetColorCoefficient(wavelengthNm);

        float temporalRise = 1f - Mathf.Exp(-((t / 1000f) / 0.0492f));
        float z =
            Mathf.Log(t / 87.8f) +
            5.600f * kColor * (p / 160.8f) * Mathf.Pow(136.5f / d, 0.548f) * temporalRise;

        return z;
    }

    private static int ComputeGrade(float z)
    {
        if (z < Grade1Upper) return 1;
        if (z < Grade2Upper) return 2;
        if (z < Grade3Upper) return 3;
        return 4;
    }

    private static float ComputeGradeProgress01(float z, int grade)
    {
        switch (grade)
        {
            case 1:
                return Mathf.InverseLerp(1.8f, Grade1Upper, z);
            case 2:
                return Mathf.InverseLerp(Grade1Upper, Grade2Upper, z);
            case 3:
                return Mathf.InverseLerp(Grade2Upper, Grade3Upper, z);
            default:
                return Mathf.InverseLerp(Grade3Upper, Grade3Upper + 2.5f, z);
        }
    }

    private static float ComputeNormalizedIntensity(float z)
    {
        return Mathf.Clamp01(Mathf.InverseLerp(2.2f, 7.6f, z));
    }

    private static bool ApproximatelyNm(float value, float target)
    {
        return Mathf.Abs(value - target) < 3f;
    }
}
