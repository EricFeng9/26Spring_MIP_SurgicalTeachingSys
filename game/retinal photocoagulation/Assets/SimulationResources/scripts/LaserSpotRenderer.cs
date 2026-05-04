using UnityEngine;

public static class LaserSpotRenderer
{
    private struct LesionBlobProfile
    {
        public float mainBlobScaleX;
        public float mainBlobScaleY;
        public float shoulderOffsetX;
        public float shoulderOffsetY;
        public float shoulderScaleX;
        public float shoulderScaleY;
        public float shoulderWeight;
        public float supportOffsetX;
        public float supportOffsetY;
        public float supportScaleX;
        public float supportScaleY;
        public float supportWeight;
        public float occluderOffsetX;
        public float occluderScaleX;
        public float occluderScaleY;
        public float occluderStrength;
        public float hueShift;
        public float saturationScale;
        public float valueLift;
        public float softness;
        public float coreFill;
        public float centerHighlight;
    }

    public static LaserShotMetrics RenderShot(
        Texture2D texture,
        Vector2Int centerTopLeft,
        LaserShotParameters parameters,
        LaserPhysicalModel model,
        float pixelToUm)
    {
        if (texture == null || model == null)
            return default;

        LaserShotMetrics metrics = model.Compute(parameters, pixelToUm);

        int centerX = centerTopLeft.x;
        int centerYTop = centerTopLeft.y;
        int centerY = texture.height - 1 - centerYTop;

        float supportRadius = metrics.effectiveRadiusPx * 1.95f;
        int gridHalf = Mathf.CeilToInt(Mathf.Max(10f, supportRadius + 6f));

        int xMin = Mathf.Max(0, centerX - gridHalf);
        int xMax = Mathf.Min(texture.width - 1, centerX + gridHalf);
        int yMin = Mathf.Max(0, centerY - gridHalf);
        int yMax = Mathf.Min(texture.height - 1, centerY + gridHalf);

        int patchW = xMax - xMin + 1;
        int patchH = yMax - yMin + 1;
        if (patchW <= 0 || patchH <= 0)
            return metrics;

        Color[] roi = texture.GetPixels(xMin, yMin, patchW, patchH);
        Color localBg = SampleLocalBackground(roi, patchW, patchH, centerX - xMin, centerY - yMin, metrics.effectiveRadiusPx);
        LesionBlobProfile profile = GetProfile(metrics.grade, metrics.gradeProgress01);
        Color lesionColor = BuildLesionColor(localBg, parameters.wavelengthNm, profile);
        Color occluderColor = BuildOccluderColor(localBg, lesionColor);
        float appearance = Mathf.Clamp01(metrics.appearanceStrength);

        for (int py = 0; py < patchH; py++)
        {
            for (int px = 0; px < patchW; px++)
            {
                int idx = py * patchW + px;
                float nx = ((xMin + px) - centerX) / Mathf.Max(1e-6f, metrics.effectiveRadiusPx);
                float ny = ((yMin + py) - centerY) / Mathf.Max(1e-6f, metrics.effectiveRadiusPx);

                float mainBlob = Gaussian(nx, ny, -0.05f, -0.03f, profile.mainBlobScaleX, profile.mainBlobScaleY, profile.softness);
                float shoulderBlob = Gaussian(nx, ny, profile.shoulderOffsetX, profile.shoulderOffsetY, profile.shoulderScaleX, profile.shoulderScaleY, profile.softness * 1.05f);
                float supportBlob = Gaussian(nx, ny, profile.supportOffsetX, profile.supportOffsetY, profile.supportScaleX, profile.supportScaleY, profile.softness * 1.15f);
                float occluderMask = Gaussian(nx, ny, profile.occluderOffsetX, 0.04f, profile.occluderScaleX, profile.occluderScaleY, 1.2f);
                float softEnvelope = Gaussian(nx, ny, 0f, 0f, 1.58f, 1.48f, 1.45f);

                float blobMask = mainBlob * 1.00f + shoulderBlob * profile.shoulderWeight + supportBlob * profile.supportWeight;
                blobMask = Mathf.Clamp01(blobMask * softEnvelope);
                blobMask = Mathf.Max(blobMask, mainBlob * profile.coreFill);
                blobMask *= appearance;

                float edgeSoft = Mathf.SmoothStep(0f, 1f, blobMask);
                edgeSoft = Mathf.Lerp(blobMask, edgeSoft, 0.45f + profile.softness * 0.18f);

                Color src = roi[idx];
                Color filled = Color.Lerp(src, lesionColor, edgeSoft);

                float warmLift = edgeSoft * (0.12f + 0.08f * appearance) * (1f - occluderMask * 0.25f);
                filled = Color.Lerp(filled, Color.Lerp(lesionColor, new Color(0.96f, 0.90f, 0.46f, 1f), 0.55f), warmLift);

                float darkenMask = occluderMask * profile.occluderStrength * edgeSoft;
                filled = Color.Lerp(filled, occluderColor, darkenMask);

                if (profile.centerHighlight > 0f)
                {
                    float centerMask = Gaussian(nx, ny, 0.02f, 0.01f, 0.28f, 0.24f, 1.9f) * edgeSoft;
                    Color centerColor = Color.Lerp(lesionColor, new Color(0.95f, 0.88f, 0.40f, 1f), 0.42f + 0.18f * appearance);
                    filled = Color.Lerp(filled, centerColor, centerMask * profile.centerHighlight);
                }

                float peripheralSoftening = Gaussian(nx, ny, 0f, 0f, 1.35f, 1.30f, 2.0f);
                filled = Color.Lerp(src, filled, peripheralSoftening);
                roi[idx] = ClampColor(filled);
            }
        }

        SoftBlurRoi(roi, patchW, patchH, 1);
        texture.SetPixels(xMin, yMin, patchW, patchH, roi);
        texture.Apply(true, false);

        return metrics;
    }

    private static LesionBlobProfile GetProfile(int grade, float progress)
    {
        LesionBlobProfile from;
        LesionBlobProfile to;

        switch (grade)
        {
            case 1:
                from = new LesionBlobProfile
                {
                    mainBlobScaleX = 0.64f,
                    mainBlobScaleY = 0.58f,
                    shoulderOffsetX = -0.28f,
                    shoulderOffsetY = -0.10f,
                    shoulderScaleX = 0.54f,
                    shoulderScaleY = 0.42f,
                    shoulderWeight = 0.18f,
                    supportOffsetX = -0.10f,
                    supportOffsetY = 0.16f,
                    supportScaleX = 0.38f,
                    supportScaleY = 0.32f,
                    supportWeight = 0.04f,
                    occluderOffsetX = 0.62f,
                    occluderScaleX = 0.64f,
                    occluderScaleY = 0.48f,
                    occluderStrength = 0.12f,
                    hueShift = 0.070f,
                    saturationScale = 1.18f,
                    valueLift = 0.10f,
                    softness = 1.35f,
                    coreFill = 0.82f,
                    centerHighlight = 0f
                };
                to = from;
                to.mainBlobScaleX = 0.70f;
                to.mainBlobScaleY = 0.64f;
                to.shoulderWeight = 0.24f;
                to.supportWeight = 0.06f;
                to.occluderStrength = 0.12f;
                to.valueLift = 0.14f;
                break;

            case 2:
                from = new LesionBlobProfile
                {
                    mainBlobScaleX = 0.72f,
                    mainBlobScaleY = 0.68f,
                    shoulderOffsetX = -0.24f,
                    shoulderOffsetY = -0.08f,
                    shoulderScaleX = 0.58f,
                    shoulderScaleY = 0.46f,
                    shoulderWeight = 0.28f,
                    supportOffsetX = -0.06f,
                    supportOffsetY = 0.18f,
                    supportScaleX = 0.42f,
                    supportScaleY = 0.36f,
                    supportWeight = 0.08f,
                    occluderOffsetX = 0.66f,
                    occluderScaleX = 0.68f,
                    occluderScaleY = 0.52f,
                    occluderStrength = 0.18f,
                    hueShift = 0.064f,
                    saturationScale = 1.12f,
                    valueLift = 0.14f,
                    softness = 1.28f,
                    coreFill = 0.86f,
                    centerHighlight = 0f
                };
                to = from;
                to.mainBlobScaleX = 0.80f;
                to.mainBlobScaleY = 0.74f;
                to.shoulderWeight = 0.34f;
                to.supportWeight = 0.10f;
                to.occluderStrength = 0.18f;
                to.valueLift = 0.18f;
                break;

            case 3:
                from = new LesionBlobProfile
                {
                    mainBlobScaleX = 0.80f,
                    mainBlobScaleY = 0.76f,
                    shoulderOffsetX = -0.18f,
                    shoulderOffsetY = -0.06f,
                    shoulderScaleX = 0.62f,
                    shoulderScaleY = 0.52f,
                    shoulderWeight = 0.36f,
                    supportOffsetX = 0.04f,
                    supportOffsetY = 0.20f,
                    supportScaleX = 0.48f,
                    supportScaleY = 0.40f,
                    supportWeight = 0.12f,
                    occluderOffsetX = 0.68f,
                    occluderScaleX = 0.72f,
                    occluderScaleY = 0.56f,
                    occluderStrength = 0.26f,
                    hueShift = 0.058f,
                    saturationScale = 1.04f,
                    valueLift = 0.17f,
                    softness = 1.18f,
                    coreFill = 0.90f,
                    centerHighlight = 0.14f
                };
                to = from;
                to.mainBlobScaleX = 0.88f;
                to.mainBlobScaleY = 0.84f;
                to.shoulderWeight = 0.42f;
                to.supportWeight = 0.16f;
                to.occluderStrength = 0.24f;
                to.valueLift = 0.22f;
                to.centerHighlight = 0.18f;
                break;

            default:
                from = new LesionBlobProfile
                {
                    mainBlobScaleX = 0.90f,
                    mainBlobScaleY = 0.86f,
                    shoulderOffsetX = -0.14f,
                    shoulderOffsetY = -0.04f,
                    shoulderScaleX = 0.68f,
                    shoulderScaleY = 0.56f,
                    shoulderWeight = 0.42f,
                    supportOffsetX = 0.08f,
                    supportOffsetY = 0.20f,
                    supportScaleX = 0.52f,
                    supportScaleY = 0.42f,
                    supportWeight = 0.18f,
                    occluderOffsetX = 0.70f,
                    occluderScaleX = 0.74f,
                    occluderScaleY = 0.58f,
                    occluderStrength = 0.34f,
                    hueShift = 0.050f,
                    saturationScale = 0.96f,
                    valueLift = 0.22f,
                    softness = 1.08f,
                    coreFill = 0.92f,
                    centerHighlight = 0.28f
                };
                to = from;
                to.mainBlobScaleX = 0.96f;
                to.mainBlobScaleY = 0.92f;
                to.shoulderWeight = 0.46f;
                to.supportWeight = 0.20f;
                to.occluderStrength = 0.32f;
                to.saturationScale = 0.90f;
                to.valueLift = 0.28f;
                to.centerHighlight = 0.30f;
                break;
        }

        return LerpProfile(from, to, Mathf.Clamp01(progress));
    }

    private static LesionBlobProfile LerpProfile(LesionBlobProfile a, LesionBlobProfile b, float t)
    {
        return new LesionBlobProfile
        {
            mainBlobScaleX = Mathf.Lerp(a.mainBlobScaleX, b.mainBlobScaleX, t),
            mainBlobScaleY = Mathf.Lerp(a.mainBlobScaleY, b.mainBlobScaleY, t),
            shoulderOffsetX = Mathf.Lerp(a.shoulderOffsetX, b.shoulderOffsetX, t),
            shoulderOffsetY = Mathf.Lerp(a.shoulderOffsetY, b.shoulderOffsetY, t),
            shoulderScaleX = Mathf.Lerp(a.shoulderScaleX, b.shoulderScaleX, t),
            shoulderScaleY = Mathf.Lerp(a.shoulderScaleY, b.shoulderScaleY, t),
            shoulderWeight = Mathf.Lerp(a.shoulderWeight, b.shoulderWeight, t),
            supportOffsetX = Mathf.Lerp(a.supportOffsetX, b.supportOffsetX, t),
            supportOffsetY = Mathf.Lerp(a.supportOffsetY, b.supportOffsetY, t),
            supportScaleX = Mathf.Lerp(a.supportScaleX, b.supportScaleX, t),
            supportScaleY = Mathf.Lerp(a.supportScaleY, b.supportScaleY, t),
            supportWeight = Mathf.Lerp(a.supportWeight, b.supportWeight, t),
            occluderOffsetX = Mathf.Lerp(a.occluderOffsetX, b.occluderOffsetX, t),
            occluderScaleX = Mathf.Lerp(a.occluderScaleX, b.occluderScaleX, t),
            occluderScaleY = Mathf.Lerp(a.occluderScaleY, b.occluderScaleY, t),
            occluderStrength = Mathf.Lerp(a.occluderStrength, b.occluderStrength, t),
            hueShift = Mathf.Lerp(a.hueShift, b.hueShift, t),
            saturationScale = Mathf.Lerp(a.saturationScale, b.saturationScale, t),
            valueLift = Mathf.Lerp(a.valueLift, b.valueLift, t),
            softness = Mathf.Lerp(a.softness, b.softness, t),
            coreFill = Mathf.Lerp(a.coreFill, b.coreFill, t),
            centerHighlight = Mathf.Lerp(a.centerHighlight, b.centerHighlight, t)
        };
    }

    private static Color SampleLocalBackground(Color[] roi, int width, int height, int centerX, int centerY, float radiusPx)
    {
        float inner = Mathf.Max(2f, radiusPx * 1.10f);
        float outer = Mathf.Max(inner + 2f, radiusPx * 1.85f);
        float inner2 = inner * inner;
        float outer2 = outer * outer;
        Color sum = Color.black;
        int count = 0;

        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
            {
                float dx = x - centerX;
                float dy = y - centerY;
                float d2 = dx * dx + dy * dy;
                if (d2 < inner2 || d2 > outer2)
                    continue;

                sum += roi[y * width + x];
                count++;
            }
        }

        if (count <= 0)
            return new Color(0.78f, 0.42f, 0.25f, 1f);

        return sum / count;
    }

    private static Color BuildLesionColor(Color localBg, float wavelengthNm, LesionBlobProfile profile)
    {
        Color.RGBToHSV(localBg, out float h, out float s, out float v);
        float waveBias = GetWaveHueBias(wavelengthNm);
        h = Mathf.Repeat(h + profile.hueShift + waveBias, 1f);
        s = Mathf.Clamp01(s * profile.saturationScale);
        v = Mathf.Clamp01(v + profile.valueLift);
        return ClampColor(Color.HSVToRGB(h, s, v));
    }

    private static Color BuildOccluderColor(Color localBg, Color lesionColor)
    {
        Color mixed = Color.Lerp(localBg, lesionColor, 0.18f);
        Color.RGBToHSV(mixed, out float h, out float s, out float v);
        h = Mathf.Repeat(h - 0.018f, 1f);
        s = Mathf.Clamp01(s * 0.96f);
        v = Mathf.Clamp01(v * 0.78f);
        return ClampColor(Color.HSVToRGB(h, s, v));
    }

    private static float GetWaveHueBias(float wavelengthNm)
    {
        if (Mathf.Abs(wavelengthNm - 577f) < 3f)
            return 0.002f;
        if (Mathf.Abs(wavelengthNm - 659f) < 3f)
            return -0.010f;
        return 0.008f;
    }

    private static float Gaussian(float x, float y, float centerX, float centerY, float scaleX, float scaleY, float softness)
    {
        float nx = (x - centerX) / Mathf.Max(0.01f, scaleX);
        float ny = (y - centerY) / Mathf.Max(0.01f, scaleY);
        return Mathf.Exp(-(nx * nx + ny * ny) * Mathf.Max(0.2f, softness));
    }

    private static void SoftBlurRoi(Color[] pixels, int width, int height, int radius)
    {
        if (radius <= 0 || pixels == null || pixels.Length != width * height)
            return;

        Color[] src = (Color[])pixels.Clone();
        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
            {
                Color sum = Color.black;
                int count = 0;
                int xMin = Mathf.Max(0, x - radius);
                int xMax = Mathf.Min(width - 1, x + radius);
                int yMin = Mathf.Max(0, y - radius);
                int yMax = Mathf.Min(height - 1, y + radius);

                for (int yy = yMin; yy <= yMax; yy++)
                {
                    for (int xx = xMin; xx <= xMax; xx++)
                    {
                        sum += src[yy * width + xx];
                        count++;
                    }
                }

                pixels[y * width + x] = sum / Mathf.Max(1, count);
            }
        }
    }

    private static Color ClampColor(Color c)
    {
        return new Color(
            Mathf.Clamp01(c.r),
            Mathf.Clamp01(c.g),
            Mathf.Clamp01(c.b),
            1f);
    }
}
