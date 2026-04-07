using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

public class RetinaPainter : MonoBehaviour, IPointerDownHandler, IPointerUpHandler, IDragHandler, IScrollHandler
{
    public Material spotMaterial; 
    public RawImage ImageContent { get; private set; }
    private RectTransform contentRect;
    private Vector2 calibrationStartPos;
    private float currentScale = 1.0f;
    private const float FocusStepPerWheel = 0.5f;
    private int currentBlurLevel = -1;
    private RenderTexture sourceTexture;
    private RenderTexture displayTexture;
    private Material blurMaterial;
    private SimpleUIRuler ruler;

    void Awake() {
        if (!GetComponent<RectMask2D>()) gameObject.AddComponent<RectMask2D>();
        GetComponent<RawImage>().enabled = false;

        if (spotMaterial != null) {
            // 分离材质状态，避免“打斑参数”覆盖“失焦渲染参数”。
            spotMaterial = new Material(spotMaterial);
            blurMaterial = new Material(spotMaterial);
        }

        GameObject child = new GameObject("FundusImageContent");
        child.transform.SetParent(this.transform, false);
        contentRect = child.AddComponent<RectTransform>();
        ImageContent = child.AddComponent<RawImage>();

        ruler = new SimpleUIRuler(this.transform);
    }

    public void SetupImageSize(float tw, float th) {
        Canvas.ForceUpdateCanvases();
        float viewW = GetComponent<RectTransform>().rect.width;
        float viewH = GetComponent<RectTransform>().rect.height;
        float aspect = tw / th;
        float targetW = viewW * 1.5f;
        float targetH = targetW / aspect;
        if (targetH < viewH * 1.5f) { targetH = viewH * 1.5f; targetW = targetH * aspect; }
        contentRect.sizeDelta = new Vector2(targetW, targetH);
        ResetView();
    }

    public void SetSourceTexture(RenderTexture source) {
        sourceTexture = source;
        EnsureDisplayTexture();
        ApplyFocusBlur(currentBlurLevel, true);
    }

    public void ApplyFocusBlur(int blurLevel, bool forceUpdate = false) {
        if (sourceTexture == null || blurMaterial == null) return;

        EnsureDisplayTexture();
        int clamped = Mathf.Clamp(blurLevel, 0, 20);
        if (!forceUpdate && clamped == currentBlurLevel) return;

        currentBlurLevel = clamped;
        blurMaterial.SetFloat("_BlurLevel", currentBlurLevel);
        blurMaterial.SetInt("_Grade", 0);
        Graphics.Blit(sourceTexture, displayTexture, blurMaterial);
    }

    public Vector2 GetViewportCenterUV() {
        if (contentRect == null || contentRect.rect.width <= 0 || contentRect.rect.height <= 0) {
            return new Vector2(0.5f, 0.5f);
        }

        RectTransform viewport = GetComponent<RectTransform>();
        Canvas canvas = GetComponentInParent<Canvas>();
        Camera eventCamera = null;
        if (canvas != null && canvas.renderMode != RenderMode.ScreenSpaceOverlay) {
            eventCamera = canvas.worldCamera;
        }

        Vector3 viewportCenterWorld = viewport.TransformPoint(viewport.rect.center);
        Vector2 viewportCenterScreen = RectTransformUtility.WorldToScreenPoint(eventCamera, viewportCenterWorld);
        RectTransformUtility.ScreenPointToLocalPointInRectangle(contentRect, viewportCenterScreen, eventCamera, out Vector2 localCenter);

        float u = (localCenter.x / Mathf.Max(0.0001f, contentRect.rect.width)) + 0.5f;
        float v = (localCenter.y / Mathf.Max(0.0001f, contentRect.rect.height)) + 0.5f;
        return new Vector2(Mathf.Clamp01(u), Mathf.Clamp01(v));
    }

    private void EnsureDisplayTexture() {
        if (sourceTexture == null) return;
        if (displayTexture != null && displayTexture.width == sourceTexture.width && displayTexture.height == sourceTexture.height) {
            if (ImageContent.texture != displayTexture) ImageContent.texture = displayTexture;
            return;
        }

        if (displayTexture != null) displayTexture.Release();
        displayTexture = new RenderTexture(sourceTexture.width, sourceTexture.height, 0);
        displayTexture.Create();
        ImageContent.texture = displayTexture;
    }

    private void ClampPosition() {
        RectTransform parent = GetComponent<RectTransform>();
        float scaledW = contentRect.rect.width * currentScale;
        float scaledH = contentRect.rect.height * currentScale;
        float maxX = Mathf.Max(0, (scaledW - parent.rect.width) / 2f);
        float maxY = Mathf.Max(0, (scaledH - parent.rect.height) / 2f);
        Vector2 pos = contentRect.anchoredPosition;
        pos.x = Mathf.Clamp(pos.x, -maxX, maxX);
        pos.y = Mathf.Clamp(pos.y, -maxY, maxY);
        contentRect.anchoredPosition = pos;
    }

    public void OnPointerDown(PointerEventData eventData) {
        if (eventData.button == PointerEventData.InputButton.Right) return;
        if (LaserAppManager.Instance.interactionMode == "calibrate") {
            calibrationStartPos = eventData.position;
            ruler.SetActive(true);
        } else {
            FireLaser(GetUVFromEvent(eventData));
        }
    }

    public void OnPointerUp(PointerEventData eventData) {
        if (ruler.IsActive) {
            ruler.SetActive(false);
            float dist = Vector2.Distance(calibrationStartPos, eventData.position);
            if (dist > 10f) LaserAppManager.Instance.ProcessCalibration(dist);
        }
    }

    public void OnDrag(PointerEventData eventData) {
        if (eventData.button == PointerEventData.InputButton.Right) {
            contentRect.anchoredPosition += eventData.delta;
            ClampPosition();
        } else if (ruler.IsActive) {
            ruler.UpdateLine(calibrationStartPos, eventData.position, eventData.pressEventCamera, GetComponent<RectTransform>());
        }
    }

    public void OnScroll(PointerEventData eventData) {
        if (Input.GetKey(KeyCode.LeftControl)) {
            if (eventData.scrollDelta.y > 0) currentScale *= 1.15f;
            else if (eventData.scrollDelta.y < 0) currentScale /= 1.15f;
            currentScale = Mathf.Clamp(currentScale, 0.2f, 5f);
            contentRect.localScale = Vector3.one * currentScale;
            ClampPosition();
        } else {
            // 缩小每次滚轮的调焦步进，避免一两次滚动就恢复清晰。
            if (eventData.scrollDelta.y > 0) LaserAppManager.Instance.AdjustFocus(FocusStepPerWheel);
            else if (eventData.scrollDelta.y < 0) LaserAppManager.Instance.AdjustFocus(-FocusStepPerWheel);
        }
    }

    public void Pan(Vector2 d) { contentRect.anchoredPosition += d; ClampPosition(); }
    public void ResetView() { contentRect.anchoredPosition = Vector2.zero; currentScale = 1f; contentRect.localScale = Vector3.one; ClampPosition(); }

    private Vector2 GetUVFromEvent(PointerEventData e) {
        RectTransformUtility.ScreenPointToLocalPointInRectangle(contentRect, e.position, e.pressEventCamera, out Vector2 local);
        return new Vector2((local.x / contentRect.rect.width) + 0.5f, (local.y / contentRect.rect.height) + 0.5f);
    }

    private void FireLaser(Vector2 uv) {
        if (uv.x < 0 || uv.x > 1 || uv.y < 0 || uv.y > 1) return;
        var (p, s, t, w) = LaserAppManager.Instance.GetCurrentLaserParams();
        var res = LaserAppManager.Instance.GetPhysicsModel().ComputeZAndGrade(p, s, t, w);
        if (res.grade == 0) return;

        RenderTexture rt = sourceTexture != null ? sourceTexture : (RenderTexture)ImageContent.texture;
        if (rt == null) return;
        Texture2D origin = LaserAppManager.Instance.originFundusImage;
        float aspect = origin != null ? (float)origin.width / origin.height : (float)rt.width / rt.height;

        spotMaterial.SetVector("_CenterUV", uv);
        spotMaterial.SetFloat("_RadiusUV", (s / 2f) / LaserAppManager.Instance.pixelToUm / rt.width);
        spotMaterial.SetInt("_Grade", res.grade);
        spotMaterial.SetFloat("_BlurLevel", 0f);
        spotMaterial.SetFloat("_Aspect", aspect);

        RenderTexture tmp = RenderTexture.GetTemporary(rt.width, rt.height, 0);
        Graphics.Blit(rt, tmp, spotMaterial); Graphics.Blit(tmp, rt);
        RenderTexture.ReleaseTemporary(tmp);
        ApplyFocusBlur(currentBlurLevel, true);
        LaserAppManager.Instance.RecordShot(uv, res.grade);
    }

    void OnDestroy() {
        if (displayTexture != null) displayTexture.Release();
        if (spotMaterial != null) Destroy(spotMaterial);
        if (blurMaterial != null) Destroy(blurMaterial);
    }

    private class SimpleUIRuler {
        private GameObject line; private RectTransform rt;
        public bool IsActive => line.activeSelf;
        public SimpleUIRuler(Transform p) {
            line = new GameObject("Ruler"); line.transform.SetParent(p, false);
            rt = line.AddComponent<RectTransform>(); rt.pivot = new Vector2(0, 0.5f);
            line.AddComponent<Image>().color = Color.green; line.SetActive(false);
        }
        public void SetActive(bool s) => line.SetActive(s);
        public void UpdateLine(Vector2 s, Vector2 e, Camera c, RectTransform p) {
            RectTransformUtility.ScreenPointToLocalPointInRectangle(p, s, c, out Vector2 start);
            RectTransformUtility.ScreenPointToLocalPointInRectangle(p, e, c, out Vector2 end);
            rt.anchoredPosition = start;
            Vector2 dir = end - start;
            rt.sizeDelta = new Vector2(dir.magnitude, 10f);
            rt.localRotation = Quaternion.Euler(0, 0, Mathf.Atan2(dir.y, dir.x) * Mathf.Rad2Deg);
        }
    }
}