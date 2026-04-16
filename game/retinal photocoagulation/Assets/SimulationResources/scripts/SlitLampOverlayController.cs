using UnityEngine;
using UnityEngine.UI;

public class SlitLampOverlayController : MonoBehaviour
{
    [Header("Refs")]
    [SerializeField] private RectTransform overlayRoot;
    [SerializeField] private RectTransform leftBlack;
    [SerializeField] private RectTransform rightBlack;
    [SerializeField] private RectTransform slitCore;   // 可选
    [SerializeField] private Image leftBlackImage;
    [SerializeField] private Image rightBlackImage;
    [SerializeField] private Image slitCoreImage;      // 可选

    [Header("Slit")]
    [SerializeField, Range(0.02f, 0.8f)] private float slitWidthNormalized = 0.18f;
    [SerializeField, Range(0f, 1f)] private float slitCenterXNormalized = 0.5f;

    [Header("Visual")]
    [SerializeField, Range(0f, 1f)] private float sideDarkAlpha = 0.95f;
    [SerializeField] private bool showSlitCore = true;
    [SerializeField, Range(0f, 1f)] private float slitCoreAlpha = 0.10f;

    private void Start()
    {
        Refresh();
    }

    private void OnRectTransformDimensionsChange()
    {
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
        slitWidthNormalized = Mathf.Clamp(value, 0.02f, 0.8f);
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
        if (overlayRoot == null || leftBlack == null || rightBlack == null)
            return;

        float w = overlayRoot.rect.width;
        float h = overlayRoot.rect.height;
        if (w <= 0f || h <= 0f)
            return;

        float slitWidth = w * slitWidthNormalized;
        float slitCenterX = w * slitCenterXNormalized;

        float slitLeft = slitCenterX - slitWidth * 0.5f;
        float slitRight = slitCenterX + slitWidth * 0.5f;

        slitLeft = Mathf.Clamp(slitLeft, 0f, w);
        slitRight = Mathf.Clamp(slitRight, 0f, w);

        // Left black
        leftBlack.anchorMin = new Vector2(0f, 0f);
        leftBlack.anchorMax = new Vector2(0f, 1f);
        leftBlack.pivot = new Vector2(0f, 0.5f);
        leftBlack.anchoredPosition = Vector2.zero;
        leftBlack.sizeDelta = new Vector2(slitLeft, 0f);

        // Right black
        rightBlack.anchorMin = new Vector2(1f, 0f);
        rightBlack.anchorMax = new Vector2(1f, 1f);
        rightBlack.pivot = new Vector2(1f, 0.5f);
        rightBlack.anchoredPosition = Vector2.zero;
        rightBlack.sizeDelta = new Vector2(w - slitRight, 0f);

        if (leftBlackImage != null)
        {
            Color c = leftBlackImage.color;
            c.r = 0f; c.g = 0f; c.b = 0f; c.a = sideDarkAlpha;
            leftBlackImage.color = c;
        }

        if (rightBlackImage != null)
        {
            Color c = rightBlackImage.color;
            c.r = 0f; c.g = 0f; c.b = 0f; c.a = sideDarkAlpha;
            rightBlackImage.color = c;
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

                if (slitCoreImage != null)
                {
                    Color c = slitCoreImage.color;
                    c.r = 1f; c.g = 1f; c.b = 1f; c.a = slitCoreAlpha;
                    slitCoreImage.color = c;
                }
            }
        }
    }
}