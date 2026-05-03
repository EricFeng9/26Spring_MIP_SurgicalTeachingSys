using UnityEngine;
using UnityEngine.UI;

public class SlitLampOverlayController : MonoBehaviour
{
    [Header("Refs")]
    [SerializeField] private RectTransform overlayRoot;
    [SerializeField] private RectTransform leftBlack;
    [SerializeField] private RectTransform rightBlack;
    [SerializeField] private RectTransform slitTint;
    [SerializeField] private RectTransform slitCore;   // 可选
    [SerializeField] private Image leftBlackImage;
    [SerializeField] private Image rightBlackImage;
    [SerializeField] private Image slitTintImage;
    [SerializeField] private Image slitCoreImage;      // 可选

    [Header("Slit")]
    [SerializeField, Range(0.001f, 0.8f)] private float slitWidthNormalized = 0.18f; // 把 0.02f 改为 0.001f
    [SerializeField, Range(0f, 1f)] private float slitCenterXNormalized = 0.5f;

    [Header("Visual")]
    [SerializeField, Range(0f, 1f)] private float sideDarkAlpha = 1.0f;
    [SerializeField] private bool showSlitCore = true;
    [SerializeField, Range(0f, 1f)] private float slitCoreAlpha = 0.10f;
    [SerializeField] private RectTransform topBlack;
    [SerializeField] private RectTransform bottomBlack;
    [SerializeField] private Image topBlackImage;
    [SerializeField] private Image bottomBlackImage;
    private bool initializedFromTint;
private float slitVerticalOffsetNormalized = 0f;

    public void SetSlitVerticalOffset(float yOffsetNormalized)
    {
        slitVerticalOffsetNormalized = yOffsetNormalized;
        Refresh();
    }
    private void Start()
    {
        EnsureTintReferences();
        // InitializeFromTintRect();
        Refresh();
    }

    private void OnRectTransformDimensionsChange()
    {
        EnsureTintReferences();
        // InitializeFromTintRect();
        Refresh();
    }

    public void AddSlitCenterXNormalized(float delta)
    {
        float half = slitWidthNormalized * 0.5f;
        slitCenterXNormalized = Mathf.Clamp(slitCenterXNormalized + delta, half, 1f - half);
        Refresh();
    }

    public void SetSlitWidthNormalized(float value)
    {
        slitWidthNormalized = Mathf.Clamp(value, 0.001f, 0.8f);
        Refresh();
    }

    public float GetSlitCenterXNormalized()
    {
        return slitCenterXNormalized;
    }

    public float GetSlitWidthNormalized()
    {
        return slitWidthNormalized;
    }

    public Vector2 GetSlitBoundsNormalized()
    {
        float half = slitWidthNormalized * 0.5f;
        return new Vector2(
            Mathf.Clamp01(slitCenterXNormalized - half),
            Mathf.Clamp01(slitCenterXNormalized + half));
    }

    public Vector2 GetReticleBoundsNormalized(float innerMaskVisibleFraction = 0f)
    {
        Vector2 slitBounds = GetSlitBoundsNormalized();
        float extension = Mathf.Clamp01(innerMaskVisibleFraction) * (1f - (slitBounds.y - slitBounds.x)) * 0.5f;
        return new Vector2(
            Mathf.Clamp01(slitBounds.x - extension),
            Mathf.Clamp01(slitBounds.y + extension));
    }

    public bool IsSlitCentered(float epsilon = 0.001f)
    {
        return Mathf.Abs(slitCenterXNormalized - 0.5f) <= epsilon;
    }

    public void SetSlitCenterXNormalized(float value)
    {
        float half = slitWidthNormalized * 0.5f;
        slitCenterXNormalized = Mathf.Clamp(value, half, 1f - half);
        Refresh();
    }

    public void SetDarkAlpha(float value)
    {
        sideDarkAlpha = Mathf.Clamp01(value);
        Refresh();
    }

public void Refresh()
    {
        EnsureTintReferences();

        if (overlayRoot == null || leftBlack == null || rightBlack == null) return;

        float w = overlayRoot.rect.width;
        float h = overlayRoot.rect.height;
        if (w <= 0f || h <= 0f) return;

        float slitWidth = w * slitWidthNormalized;
        float slitCenterX = w * slitCenterXNormalized;

        float slitLeft = Mathf.Clamp(slitCenterX - slitWidth * 0.5f, 0f, w);
        float slitRight = Mathf.Clamp(slitCenterX + slitWidth * 0.5f, 0f, w);

        // --- 1. 左右黑布（保持原样） ---
        leftBlack.anchorMin = new Vector2(0f, 0f);
        leftBlack.anchorMax = new Vector2(0f, 1f);
        leftBlack.pivot = new Vector2(0f, 0.5f);
        leftBlack.anchoredPosition = Vector2.zero;
        leftBlack.sizeDelta = new Vector2(slitLeft, 0f);

        rightBlack.anchorMin = new Vector2(1f, 0f);
        rightBlack.anchorMax = new Vector2(1f, 1f);
        rightBlack.pivot = new Vector2(1f, 0.5f);
        rightBlack.anchoredPosition = Vector2.zero;
        rightBlack.sizeDelta = new Vector2(w - slitRight, 0f);

        if (leftBlackImage != null) { Color c = leftBlackImage.color; c.a = sideDarkAlpha; leftBlackImage.color = c; }
        if (rightBlackImage != null){ Color c = rightBlackImage.color; c.a = sideDarkAlpha; rightBlackImage.color = c; }

        // --- 2. 计算变黑的像素高度 ---
        float fadeMultiplier = 1.0f; // 遮黑倍率，可微调
        float darkPixels = Mathf.Abs(slitVerticalOffsetNormalized) * fadeMultiplier * h;
        float bottomChop = slitVerticalOffsetNormalized > 0 ? darkPixels : 0f;
        float topChop = slitVerticalOffsetNormalized < 0 ? darkPixels : 0f;

        // --- 3. 【你的绝妙点子】：上下黑布拉伸遮挡 ---
        if (topBlack != null)
        {
            topBlack.gameObject.SetActive(topChop > 0.001f);
            // 贴紧屏幕最上方，向下延伸
            topBlack.anchorMin = new Vector2(0f, 1f);
            topBlack.anchorMax = new Vector2(1f, 1f);
            topBlack.pivot = new Vector2(0.5f, 1f);
            topBlack.anchoredPosition = Vector2.zero;
            topBlack.sizeDelta = new Vector2(0f, topChop); // 高度拉伸
            if (topBlackImage != null) { Color c = topBlackImage.color; c.a = sideDarkAlpha; topBlackImage.color = c; }
        }

        if (bottomBlack != null)
        {
            bottomBlack.gameObject.SetActive(bottomChop > 0.001f);
            // 贴紧屏幕最下方，向上延伸
            bottomBlack.anchorMin = new Vector2(0f, 0f);
            bottomBlack.anchorMax = new Vector2(1f, 0f);
            bottomBlack.pivot = new Vector2(0.5f, 0f);
            bottomBlack.anchoredPosition = Vector2.zero;
            bottomBlack.sizeDelta = new Vector2(0f, bottomChop); // 高度拉伸
            if (bottomBlackImage != null) { Color c = bottomBlackImage.color; c.a = sideDarkAlpha; bottomBlackImage.color = c; }
        }

        // --- 4. 恢复光带本身完整的高度（不再尝试裁剪它本身） ---
        if (slitTint != null)
        {
            slitTint.gameObject.SetActive(true);
            slitTint.anchorMin = new Vector2(0f, 0f);
            slitTint.anchorMax = new Vector2(0f, 1f);
            slitTint.pivot = new Vector2(0f, 0.5f);
            slitTint.anchoredPosition = new Vector2(slitLeft, 0f);
            slitTint.sizeDelta = new Vector2(slitWidth, 0f); // 0 表示高度占满
            slitTint.offsetMin = new Vector2(slitTint.offsetMin.x, 0f);
            slitTint.offsetMax = new Vector2(slitTint.offsetMax.x, 0f);
        }

        if (slitCore != null)
        {
            slitCore.gameObject.SetActive(showSlitCore);
            if (showSlitCore)
            {
                slitCore.anchorMin = new Vector2(0f, 0f);
                slitCore.anchorMax = new Vector2(0f, 1f);
                slitCore.pivot = new Vector2(0f, 0.5f);
                slitCore.anchoredPosition = new Vector2(slitLeft, 0f);
                slitCore.sizeDelta = new Vector2(slitWidth, 0f);
                slitCore.offsetMin = new Vector2(slitCore.offsetMin.x, 0f);
                slitCore.offsetMax = new Vector2(slitCore.offsetMax.x, 0f);

                if (slitCoreImage != null)
                {
                    Color c = slitCoreImage.color;
                    c.a = slitCoreAlpha;
                    slitCoreImage.color = c;
                }
            }
        }
    }

private void EnsureTintReferences()
    {
        if (overlayRoot == null) return;

        if (slitTint == null)
        {
            Transform tintTransform = overlayRoot.Find("Image_SlitTint");
            if (tintTransform != null) slitTint = tintTransform as RectTransform;
        }
        if (slitTintImage == null && slitTint != null) slitTintImage = slitTint.GetComponent<Image>();

        // --- 新增：自动寻找上下黑布 ---
        if (topBlack == null)
        {
            Transform t = overlayRoot.Find("Image_TopBlack");
            if (t != null) topBlack = t as RectTransform;
        }
        if (bottomBlack == null)
        {
            Transform t = overlayRoot.Find("Image_BottomBlack");
            if (t != null) bottomBlack = t as RectTransform;
        }
        if (topBlackImage == null && topBlack != null) topBlackImage = topBlack.GetComponent<Image>();
        if (bottomBlackImage == null && bottomBlack != null) bottomBlackImage = bottomBlack.GetComponent<Image>();
    }
    private void InitializeFromTintRect()
    {
        if (initializedFromTint || overlayRoot == null || slitTint == null)
            return;

        float overlayWidth = overlayRoot.rect.width;
        if (overlayWidth <= 0.001f)
            return;

        Vector2 tintBounds = GetNormalizedBoundsFromRect(slitTint, overlayRoot);
        float width = Mathf.Clamp(tintBounds.y - tintBounds.x, 0.02f, 0.8f);
        float center = Mathf.Clamp01((tintBounds.x + tintBounds.y) * 0.5f);
        if (width <= 0.001f)
            return;

        slitWidthNormalized = width;
        slitCenterXNormalized = Mathf.Clamp(center, width * 0.5f, 1f - width * 0.5f);
        initializedFromTint = true;
    }

    private static Vector2 GetNormalizedBoundsFromRect(RectTransform target, RectTransform relativeTo)
    {
        Vector3[] corners = new Vector3[4];
        target.GetWorldCorners(corners);

        Vector2 left = relativeTo.InverseTransformPoint(corners[0]);
        Vector2 right = relativeTo.InverseTransformPoint(corners[3]);
        float width = relativeTo.rect.width;
        if (width <= 0.001f)
            return new Vector2(0f, 1f);

        float min = Mathf.Clamp01((left.x - relativeTo.rect.xMin) / width);
        float max = Mathf.Clamp01((right.x - relativeTo.rect.xMin) / width);
        if (max < min)
        {
            float temp = min;
            min = max;
            max = temp;
        }

        return new Vector2(min, max);
    }
}
