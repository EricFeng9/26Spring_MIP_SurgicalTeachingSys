using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using TMPro;

public class FundusFovController : MonoBehaviour, IPointerDownHandler, IPointerMoveHandler
{
    public enum WorkingLensPreset
    {
        GoldmannWorking38,
        KriegerWorking41,
        PanfundoscopeWorking70,
        MainsterWorking60
    }

    public enum CameraPreset
    {
        Optos200,
        Clarus133,
        Montage267,
        Custom
    }

    [Header("External Controllers")]
    [SerializeField] private SlitLampOverlayController slitLamp;

    [Header("UI References")]
    [SerializeField] private RawImage fundusRawImage;         // 清晰图
    [SerializeField] private RawImage focusBlurRawImage;      // 模糊层（叠在清晰图上面）
    [SerializeField] private RectTransform circularViewportRect; //圆形可见区域
    [SerializeField] private TMP_Dropdown lensDropdown;
    [SerializeField] private Text debugText;                  // 可选

    [Header("Source Image")]
    [SerializeField] private Texture2D sourceTexture;
    [SerializeField, Range(0, 50)] private int nonBlackThreshold = 8;
    [SerializeField] private bool useMaskCentroidAsStart = true;//把非黑色部分的质心作为中心点
    [SerializeField, Range(0f, 1f)] private float startXFraction = 0.5f;
    [SerializeField, Range(0f, 1f)] private float startYFraction = 0.5f;

    [Header("FOV Settings")]
    [SerializeField] private WorkingLensPreset lensPreset = WorkingLensPreset.GoldmannWorking38;
    [SerializeField] private CameraPreset cameraPreset = CameraPreset.Montage267;
    [SerializeField, Range(30f, 300f)] private float customCameraTotalDeg = 200f;

    [Header("Movement")]
    [SerializeField] private bool enableKeyboardMove = true;
    [SerializeField] private bool useWASD = true;
    [SerializeField] private float moveSpeedPxPerSecond = 360f;
    [SerializeField] private float fineMoveSpeedMultiplier = 0.2f;
    [SerializeField] private bool normalizeDiagonal = true;

    [Header("Mask Relaxation")]
    [SerializeField, Range(0, 64)] private int moveMaskExpandPixels = 12;
    [SerializeField, Range(0, 32)] private int moveMaskBlurRadius = 8;
    [SerializeField, Range(0.01f, 1f)] private float moveMaskAcceptThreshold = 0.35f;
    [SerializeField, Range(0, 12)] private int allowedInvalidRingSamples = 3;
    [SerializeField, Range(0, 12)] private int allowedInvalidInnerSamples = 1;

    [Header("Focus")]
    [SerializeField] private bool enableFocus = true;
    [SerializeField, Range(0f, 1f)] private float initialFocusNormalized = 0f; // 0=最糊, 1=最清晰
    [SerializeField, Range(0.01f, 0.5f)] private float focusWheelStep = 0.08f;
    [SerializeField, Range(1, 12)] private int focusBlurRadius = 5;
    [SerializeField] private bool invertFocusWheel = false;

    [Header("Calibration")]
    [SerializeField] private RectTransform calibrationLine;
    [SerializeField] private RectTransform calibrationPreviewStartMarker;
    [SerializeField] private RectTransform calibrationPreviewEndMarker;
    [SerializeField] private float minCalibrationDistancePx = 8f;

    [Header("Debug")]
    [SerializeField] private bool initializeOnStart = true;
    [SerializeField] private bool logDebugInfo = true;
    
    private bool[] areaMask;        // 面积计算 / 质心 / 原始有效区域
    private float[] moveSoftMask;   // 移动边界判断
    private int texWidth;
    private int texHeight;
    private int validPixelCount;

    private Vector2 currentCenterPx;
    private float currentRadiusPx;
    private float currentDiameterPx;

    private bool isReady;

    private Texture2D focusBlurTexture;
    private float focusNormalized;
    private bool isCalibrationMode;
    private bool hasCalibrationStartPoint;
    private bool hasDiscCalibration;
    private Vector2 calibrationStartOriginalPx;
    private Vector2 calibrationCurrentOriginalPx;
    private float calibratedPixelToUmOriginal;
    private float calibratedDiscDiameterPxOriginal;
    private float calibratedDiscDiameterUm;

    public Vector2 CurrentCenterPx => currentCenterPx;
    public float CurrentRadiusPx => currentRadiusPx;
    public float CurrentDiameterPx => currentDiameterPx;
    public bool IsReady => isReady;
    public bool IsCalibrationMode => isCalibrationMode;
    public bool HasDiscCalibration => hasDiscCalibration;
    public float CalibratedPixelToUmOriginal => calibratedPixelToUmOriginal;
    public float CalibratedDiscDiameterPxOriginal => calibratedDiscDiameterPxOriginal;
    public float CalibratedDiscDiameterUm => calibratedDiscDiameterUm;

    public event Action<float> DiscCalibrationLineCompleted;
    public float MoveSpeedPxPerSecond => moveSpeedPxPerSecond;
    private void Awake()
    {
        SetupLensDropdown();
    }

    private void Start()
    {
        SetCalibrationPreviewVisible(false);

        if (initializeOnStart && sourceTexture != null)
        {
            InitializeWithTexture(sourceTexture);
        }
    }

    private void OnDestroy()
    {
        if (focusBlurTexture != null)
        {
            Destroy(focusBlurTexture);
            focusBlurTexture = null;
        }
    }

    private void Update()
    {
        if (!isReady)
            return;

        if (isCalibrationMode)
        {
            HandleCalibrationPointerInput();

            if (Input.GetMouseButtonDown(1) || Input.GetKeyDown(KeyCode.Escape))
                CancelDiscCalibration();

            return;
        }

        // 鼠标滚轮调焦
        if (enableFocus)
        {
            float wheel = Input.mouseScrollDelta.y;
            if (Mathf.Abs(wheel) > 0.001f)
            {
                float signed = invertFocusWheel ? -wheel : wheel;
                focusNormalized = Mathf.Clamp01(focusNormalized + signed * focusWheelStep);
                UpdateFocusVisual();
                RefreshDebugText();
            }
        }

        if (!enableKeyboardMove)
            return;

        if (HasInteractiveUiFocus())
            return;

        Vector2 dir = Vector2.zero;

        if (useWASD && Input.GetKey(KeyCode.W))
            dir.y -= 1f;

        if (useWASD && Input.GetKey(KeyCode.S))
            dir.y += 1f;

        if (useWASD && Input.GetKey(KeyCode.A))
            dir.x -= 1f;

        if (useWASD && Input.GetKey(KeyCode.D))
            dir.x += 1f;

        if (dir == Vector2.zero)
            return;

        if (normalizeDiagonal)
            dir = dir.normalized;

        float speedMultiplier = (Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift))
            ? fineMoveSpeedMultiplier
            : 1f;
        Vector2 deltaPx = dir * moveSpeedPxPerSecond * Mathf.Max(0f, speedMultiplier) * Time.deltaTime;

        // 横向规则：
        // 1. 裂隙不在中心 -> 先只动裂隙，不许图像横向动
        // 2. 裂隙在中心 -> 优先动图像
        // 3. 图像到左右边 -> 才开始动裂隙
        if (Mathf.Abs(deltaPx.x) > 0.001f)
        {
            MoveHorizontalByDirection(Mathf.Sign(deltaPx.x));
        }

        // 纵向始终只动图像
        if (Mathf.Abs(deltaPx.y) > 0.001f)
        {
            TryMoveImageY(deltaPx.y);
        }
    }

public void MoveHorizontalByDirection(float direction, float speedScale = 1f)
    {
        if (!isReady)
            return;

        float signedDirection = Mathf.Sign(direction);
        if (Mathf.Abs(signedDirection) <= 0.001f)
            return;

        float deltaPx = signedDirection * moveSpeedPxPerSecond * Mathf.Max(0f, speedScale) * Time.deltaTime;
        if (Mathf.Abs(deltaPx) <= 0.001f)
            return;

        // 【核心修复】：使用底层视野直径 (CurrentDiameterPx) 替代 UI 宽度 (viewportWidth)
        // 这样计算出的 normalizedDelta 能保证裂隙灯在边缘的 UI 移动速度与中心底图的移动速度视觉上绝对 1:1 一致
        float normalizedDelta = deltaPx / Mathf.Max(1f, currentDiameterPx);

        // 1. 如果裂隙不在中心 -> 先只动裂隙，使其归中
        if (slitLamp != null && !slitLamp.IsSlitCentered())
        {
            slitLamp.AddSlitCenterXNormalized(normalizedDelta);
            return;
        }

        // 2. 尝试移动底图
        bool movedX = TryMoveImageX(deltaPx);
        if (movedX || slitLamp == null)
            return;

        // 3. 底图碰到左右边缘（撞墙） -> 图像无法移动，转而移动裂隙（准星）
        slitLamp.AddSlitCenterXNormalized(normalizedDelta);
    }
    public void MoveVerticalByDirection(float direction, float speedScale = 1f)
    {
        if (!isReady)
            return;

        float signedDirection = Mathf.Sign(direction);
        if (Mathf.Abs(signedDirection) <= 0.001f)
            return;

        float deltaPx = signedDirection * moveSpeedPxPerSecond * Mathf.Max(0f, speedScale) * Time.deltaTime;
        if (Mathf.Abs(deltaPx) <= 0.001f)
            return;

        TryMoveImageY(deltaPx);
    }

    public void InitializeWithTexture(Texture2D texture)
    {
        if (texture == null)
        {
            Debug.LogWarning("InitializeWithTexture failed: texture is null.");
            isReady = false;
            RefreshDebugText();
            return;
        }

        sourceTexture = texture;
        texWidth = sourceTexture.width;
        texHeight = sourceTexture.height;

        BuildNonBlackMask();

        if (validPixelCount <= 0)
        {
            Debug.LogWarning("No valid non-black pixels found. Try lowering threshold.");
            isReady = false;
            RefreshDebugText();
            return;
        }

        RecalculateFov();

        currentCenterPx = ChooseInitialCenter();
        if (!IsCenterValid(currentCenterPx))
        {
            currentCenterPx = FindNearestValidCenter(currentCenterPx, 300, 4f);
        }

        if (fundusRawImage != null)
        {
            fundusRawImage.texture = sourceTexture;
        }

        // 重新生成模糊图
        if (focusBlurTexture != null)
        {
            Destroy(focusBlurTexture);
            focusBlurTexture = null;
        }

        if (focusBlurRawImage != null)
        {
            focusBlurTexture = CreateBlurredTexture(sourceTexture, focusBlurRadius);
            focusBlurRawImage.texture = focusBlurTexture;
            focusBlurRawImage.raycastTarget = false;
        }

        // 新图加载后默认先模糊
        focusNormalized = initialFocusNormalized;
        UpdateFocusVisual();

        // 新图加载时把裂隙灯复位到中心
        if (slitLamp != null)
            slitLamp.SetSlitCenterXNormalized(0.5f);

        ApplyView();
        isReady = true;

        if (logDebugInfo)
        {
            Debug.Log(
                $"FOV init done. tex={texWidth}x{texHeight}, validPixels={validPixelCount}, " +
                $"diameterPx={currentDiameterPx:F1}, radiusPx={currentRadiusPx:F1}, center={currentCenterPx}"
            );
        }

        RefreshDebugText();
    }

    public void SetSourceTexture(Texture2D texture)
    {
        InitializeWithTexture(texture);
    }

    public void BeginDiscCalibration()
    {
        if (!isReady || circularViewportRect == null || fundusRawImage == null)
            return;

        isCalibrationMode = true;
        hasCalibrationStartPoint = false;
        calibrationStartOriginalPx = Vector2.zero;
        calibrationCurrentOriginalPx = Vector2.zero;
        SetCalibrationPreviewVisible(false);
        RefreshDebugText();
    }

    public void CancelDiscCalibration()
    {
        isCalibrationMode = false;
        hasCalibrationStartPoint = false;
        SetCalibrationPreviewVisible(false);
        RefreshDebugText();
    }

    public bool TrySetDiscCalibration(float discDiameterPxOriginal, float discDiameterUm)
    {
        if (discDiameterPxOriginal < minCalibrationDistancePx || discDiameterUm <= 0f)
            return false;

        calibratedDiscDiameterPxOriginal = discDiameterPxOriginal;
        calibratedDiscDiameterUm = discDiameterUm;
        calibratedPixelToUmOriginal = discDiameterUm / discDiameterPxOriginal;
        hasDiscCalibration = true;
        isCalibrationMode = false;
        hasCalibrationStartPoint = false;
        SetCalibrationPreviewVisible(false);
        RefreshDebugText();
        return true;
    }

    public void ClearDiscCalibration()
    {
        hasDiscCalibration = false;
        calibratedPixelToUmOriginal = 0f;
        calibratedDiscDiameterPxOriginal = 0f;
        calibratedDiscDiameterUm = 0f;
        CancelDiscCalibration();
    }

public float GetEffectivePixelToUm(float fallbackPixelToUm)
    {
        // 1. 优先使用医生手动定标的极高精度数据
        if (hasDiscCalibration && calibratedPixelToUmOriginal > 0f)
            return calibratedPixelToUmOriginal;

        // 2. 核心修复：基于相机的物理视场角与有效像素总面积，自动精确推导 微米/像素 比例
        if (validPixelCount > 0)
        {
            // 李斯丁眼模型半径 R = 11.39 mm = 11390 um
            float R_um = 11390f; 
            float phi_Camera = (GetCameraTotalDeg() * 0.5f) * Mathf.Deg2Rad;
            
            // 计算相机拍摄到的视网膜总物理表面积 (平方微米)
            float areaRetinaUm2 = 2f * Mathf.PI * R_um * R_um * (1f - Mathf.Cos(phi_Camera));
            
            // 计算单个像素代表的物理面积，开方即得 um/px 
            float pixelAreaUm2 = areaRetinaUm2 / Mathf.Max(1, validPixelCount);
            return Mathf.Sqrt(pixelAreaUm2);
        }

        // 3. 极端情况下的安全兜底
        return fallbackPixelToUm;
    }

    public void OnPointerDown(PointerEventData eventData)
    {
        if (!isCalibrationMode || !isReady)
            return;

        HandleCalibrationPointerEvent(eventData);
    }

    public void OnPointerMove(PointerEventData eventData)
    {
        if (!isCalibrationMode || !hasCalibrationStartPoint)
            return;

        HandleCalibrationMoveEvent(eventData);
    }

    public void SetLensPreset(WorkingLensPreset preset)
    {
        lensPreset = preset;
        SyncLensDropdownWithoutNotify();
        RefreshFovOnly();
    }

    // public void SetLensPresetFromDropdown(int dropdownIndex)
    // {
    //     if (dropdownIndex < 0 || dropdownIndex > 3)
    //         return;

    //     lensPreset = (WorkingLensPreset)dropdownIndex;
    //     RefreshFovOnly();
    // }

    public void SetCameraPreset(CameraPreset preset)
    {
        cameraPreset = preset;
        RefreshFovOnly();
    }

    public void SetCustomCameraTotalDeg(float totalDeg)
    {
        customCameraTotalDeg = Mathf.Clamp(totalDeg, 30f, 300f);
        RefreshFovOnly();
    }

    public void SetNonBlackThreshold(int threshold)
    {
        nonBlackThreshold = Mathf.Clamp(threshold, 0, 50);

        if (sourceTexture == null)
            return;

        BuildNonBlackMask();

        if (validPixelCount <= 0)
        {
            isReady = false;
            RefreshDebugText();
            return;
        }

        RecalculateFov();

        if (!IsCenterValid(currentCenterPx))
        {
            currentCenterPx = FindNearestValidCenter(currentCenterPx, 300, 4f);
        }

        ApplyView();
        isReady = true;
        RefreshDebugText();
    }

    public void RefreshFovOnly()
    {
        if (sourceTexture == null || areaMask == null || moveSoftMask == null)
            return;

        RecalculateFov();

        if (!IsCenterValid(currentCenterPx))
        {
            currentCenterPx = FindNearestValidCenter(currentCenterPx, 300, 4f);
        }

        ApplyView();
        RefreshDebugText();
    }

private void SetupLensDropdown()
    {
        if (lensDropdown == null)
            return;

        lensDropdown.onValueChanged.RemoveAllListeners();
        lensDropdown.options.Clear();

        // 移除 70° 镜头，仅保留三个选项
        lensDropdown.options.Add(new TMP_Dropdown.OptionData("Goldmann±38°")); // Index 0
        lensDropdown.options.Add(new TMP_Dropdown.OptionData("Krieger±41°"));  // Index 1
        lensDropdown.options.Add(new TMP_Dropdown.OptionData("Mainster±60°")); // Index 2

        // 手动映射枚举到新的下拉索引，避免使用 (int)lensPreset 导致越界
        if (lensPreset == WorkingLensPreset.GoldmannWorking38) lensDropdown.value = 0;
        else if (lensPreset == WorkingLensPreset.KriegerWorking41) lensDropdown.value = 1;
        else if (lensPreset == WorkingLensPreset.MainsterWorking60) lensDropdown.value = 2;
        else lensDropdown.value = 0; // 如果 Inspector 里默认选了 70°，则安全回退到 38°

        lensDropdown.RefreshShownValue();
        lensDropdown.onValueChanged.AddListener(SetLensPresetFromDropdown);
    }

    private void SyncLensDropdownWithoutNotify()
    {
        if (lensDropdown == null)
            return;

        lensDropdown.onValueChanged.RemoveListener(SetLensPresetFromDropdown);
        
        // 同样替换掉强制转换逻辑
        if (lensPreset == WorkingLensPreset.GoldmannWorking38) lensDropdown.value = 0;
        else if (lensPreset == WorkingLensPreset.KriegerWorking41) lensDropdown.value = 1;
        else if (lensPreset == WorkingLensPreset.MainsterWorking60) lensDropdown.value = 2;
        else lensDropdown.value = 0;

        lensDropdown.RefreshShownValue();
        lensDropdown.onValueChanged.AddListener(SetLensPresetFromDropdown);
    }

    public void SetLensPresetFromDropdown(int dropdownIndex)
    {
        // 根据新的 UI 索引反向映射回枚举
        switch (dropdownIndex)
        {
            case 0: lensPreset = WorkingLensPreset.GoldmannWorking38; break;
            case 1: lensPreset = WorkingLensPreset.KriegerWorking41; break;
            case 2: lensPreset = WorkingLensPreset.MainsterWorking60; break;
            default: lensPreset = WorkingLensPreset.GoldmannWorking38; break;
        }
        RefreshFovOnly();
    }

    private void BuildNonBlackMask()
    {
        Color32[] pixels = sourceTexture.GetPixels32();

        areaMask = new bool[pixels.Length];
        validPixelCount = 0;

        for (int i = 0; i < pixels.Length; i++)
        {
            Color32 c = pixels[i];
            byte maxRgb = c.r;
            if (c.g > maxRgb) maxRgb = c.g;
            if (c.b > maxRgb) maxRgb = c.b;

            bool valid = maxRgb > nonBlackThreshold;
            areaMask[i] = valid;

            if (valid)
                validPixelCount++;
        }

        bool[] expanded = DilateMask(areaMask, texWidth, texHeight, moveMaskExpandPixels);
        moveSoftMask = BlurMaskToFloat(expanded, texWidth, texHeight, moveMaskBlurRadius);
    }

    private void RecalculateFov()
    {
        float thetaIHalfDeg = GetCameraTotalDeg() * 0.5f;
        float thetaGHalfDeg = GetLensHalfDeg();

        float p = SphericalAreaRatio(thetaGHalfDeg, thetaIHalfDeg);
        currentDiameterPx = 2f * Mathf.Sqrt((p / Mathf.PI) * validPixelCount);
        currentDiameterPx = Mathf.Max(1f, currentDiameterPx);
        currentRadiusPx = currentDiameterPx * 0.5f;
    }

    private Vector2 ChooseInitialCenter()
    {
        if (useMaskCentroidAsStart)
        {
            long sumX = 0;
            long sumY = 0;
            int count = 0;

            for (int y = 0; y < texHeight; y++)
            {
                for (int x = 0; x < texWidth; x++)
                {
                    if (areaMask[y * texWidth + x])
                    {
                        sumX += x;
                        sumY += y;
                        count++;
                    }
                }
            }

            if (count > 0)
                return new Vector2((float)sumX / count, (float)sumY / count);
        }

        return new Vector2(
            startXFraction * (texWidth - 1),
            startYFraction * (texHeight - 1)
        );
    }

    private bool TryMoveImageX(float deltaX)
    {
        Vector2 candidate = new Vector2(currentCenterPx.x + deltaX, currentCenterPx.y);

        if (IsCenterValid(candidate))
        {
            currentCenterPx = candidate;
            ApplyView();
            RefreshDebugText();
            return true;
        }

        return false;
    }

    private bool TryMoveImageY(float deltaY)
    {
        Vector2 candidate = new Vector2(currentCenterPx.x, currentCenterPx.y + deltaY);

        if (IsCenterValid(candidate))
        {
            currentCenterPx = candidate;
            ApplyView();
            RefreshDebugText();
            return true;
        }

        return false;
    }

    private bool IsCenterValid(Vector2 centerPx)
    {
        if (!IsMaskValid(centerPx.x, centerPx.y))
            return false;

        int invalidRing = 0;
        const int ringSamples = 72;

        for (int i = 0; i < ringSamples; i++)
        {
            float t = i / (float)ringSamples;
            float a = t * Mathf.PI * 2f;

            float sx = centerPx.x + Mathf.Cos(a) * currentRadiusPx;
            float sy = centerPx.y + Mathf.Sin(a) * currentRadiusPx;

            if (!IsMaskValid(sx, sy))
            {
                invalidRing++;
                if (invalidRing > allowedInvalidRingSamples)
                    return false;
            }
        }

        int invalidInner = 0;
        const int innerSamples = 24;
        float innerR = currentRadiusPx * 0.6f;

        for (int i = 0; i < innerSamples; i++)
        {
            float t = i / (float)innerSamples;
            float a = t * Mathf.PI * 2f;

            float sx = centerPx.x + Mathf.Cos(a) * innerR;
            float sy = centerPx.y + Mathf.Sin(a) * innerR;

            if (!IsMaskValid(sx, sy))
            {
                invalidInner++;
                if (invalidInner > allowedInvalidInnerSamples)
                    return false;
            }
        }

        return true;
    }

    private bool IsMaskValid(float x, float y)
    {
        return SampleSoftMaskBilinear(x, y) >= moveMaskAcceptThreshold;
    }

    private Vector2 FindNearestValidCenter(Vector2 from, int maxRadiusSteps, float stepSize)
    {
        if (IsCenterValid(from))
            return from;

        for (int r = 1; r <= maxRadiusSteps; r++)
        {
            float radius = r * stepSize;
            int samples = Mathf.Max(16, Mathf.CeilToInt(radius * 6f));

            for (int i = 0; i < samples; i++)
            {
                float t = i / (float)samples;
                float a = t * Mathf.PI * 2f;

                Vector2 candidate = from + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * radius;
                if (IsCenterValid(candidate))
                    return candidate;
            }
        }

        return from;
    }

    private void ApplyView()
    {
        if (circularViewportRect == null || sourceTexture == null)
            return;

        float viewportDiameterUi = Mathf.Min(circularViewportRect.rect.width, circularViewportRect.rect.height);
        float uiScale = viewportDiameterUi / currentDiameterPx;

        float scaledWidth = texWidth * uiScale;
        float scaledHeight = texHeight * uiScale;

        float posX = scaledWidth * 0.5f - currentCenterPx.x * uiScale;
        float posY = -scaledHeight * 0.5f + currentCenterPx.y * uiScale;

        ApplyRawImageTransform(fundusRawImage, scaledWidth, scaledHeight, posX, posY);
        ApplyRawImageTransform(focusBlurRawImage, scaledWidth, scaledHeight, posX, posY);
    }

    private void ApplyRawImageTransform(RawImage rawImage, float scaledWidth, float scaledHeight, float posX, float posY)
    {
        if (rawImage == null)
            return;

        RectTransform imageRt = rawImage.rectTransform;
        imageRt.anchorMin = new Vector2(0.5f, 0.5f);
        imageRt.anchorMax = new Vector2(0.5f, 0.5f);
        imageRt.pivot = new Vector2(0.5f, 0.5f);
        imageRt.sizeDelta = new Vector2(scaledWidth, scaledHeight);
        imageRt.anchoredPosition = new Vector2(posX, posY);

        rawImage.uvRect = new Rect(0f, 0f, 1f, 1f);
    }

    private void UpdateFocusVisual()
    {
        if (focusBlurRawImage == null)
            return;

        Color c = focusBlurRawImage.color;
        c.a = enableFocus ? (1f - focusNormalized) : 0f;
        focusBlurRawImage.color = c;
    }

    private bool TryGetOriginalPixelFromPointer(PointerEventData eventData, out Vector2 originalPx, out Vector2 localPoint)
    {
        Camera eventCamera = eventData != null ? (eventData.pressEventCamera ?? eventData.enterEventCamera) : null;
        Vector2 screenPoint = eventData != null ? eventData.position : (Vector2)Input.mousePosition;
        return TryGetOriginalPixelFromScreenPoint(screenPoint, eventCamera, out originalPx, out localPoint);
    }

    private bool TryGetOriginalPixelFromScreenPoint(Vector2 screenPoint, Camera eventCamera, out Vector2 originalPx, out Vector2 localPoint)
    {
        originalPx = default;
        localPoint = default;

        if (circularViewportRect == null || fundusRawImage == null || sourceTexture == null)
            return false;

        if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(
                circularViewportRect,
                screenPoint,
                eventCamera,
                out localPoint))
        {
            return false;
        }

        float viewportRadiusUi = Mathf.Min(circularViewportRect.rect.width, circularViewportRect.rect.height) * 0.5f;
        if (localPoint.sqrMagnitude > viewportRadiusUi * viewportRadiusUi)
            return false;

        float viewportDiameterUi = viewportRadiusUi * 2f;
        if (viewportDiameterUi <= 0.001f || currentDiameterPx <= 0.001f)
            return false;

        float uiScale = viewportDiameterUi / currentDiameterPx;
        Vector2 imageLocal = localPoint - fundusRawImage.rectTransform.anchoredPosition;

        float originalX = imageLocal.x / uiScale + texWidth * 0.5f;
        float originalY = texHeight * 0.5f - imageLocal.y / uiScale;

        if (originalX < 0f || originalY < 0f || originalX > texWidth - 1 || originalY > texHeight - 1)
            return false;

        originalPx = new Vector2(originalX, originalY);
        return true;
    }

    private void HandleCalibrationPointerInput()
    {
        if (Input.GetMouseButtonDown(0) && !IsPointerOverInteractiveUi())
        {
            if (TryGetOriginalPixelFromScreenPoint(Input.mousePosition, null, out Vector2 originalPx, out Vector2 localPoint))
                CommitCalibrationPoint(originalPx, localPoint);
        }

        if (hasCalibrationStartPoint && !IsPointerOverInteractiveUi())
        {
            if (TryGetOriginalPixelFromScreenPoint(Input.mousePosition, null, out Vector2 originalPx, out Vector2 localPoint))
            {
                calibrationCurrentOriginalPx = originalPx;
                UpdateCalibrationPreviewForOriginalPoints(calibrationStartOriginalPx, calibrationCurrentOriginalPx, localPoint);
            }
        }
    }

    private void HandleCalibrationPointerEvent(PointerEventData eventData)
    {
        if (!TryGetOriginalPixelFromPointer(eventData, out Vector2 originalPx, out Vector2 localPoint))
            return;

        CommitCalibrationPoint(originalPx, localPoint);
    }

    private void HandleCalibrationMoveEvent(PointerEventData eventData)
    {
        if (!TryGetOriginalPixelFromPointer(eventData, out Vector2 originalPx, out Vector2 localPoint))
            return;

        calibrationCurrentOriginalPx = originalPx;
        UpdateCalibrationPreviewForOriginalPoints(calibrationStartOriginalPx, calibrationCurrentOriginalPx, localPoint);
    }

    private void CommitCalibrationPoint(Vector2 originalPx, Vector2 localPoint)
    {
        if (!hasCalibrationStartPoint)
        {
            hasCalibrationStartPoint = true;
            calibrationStartOriginalPx = originalPx;
            calibrationCurrentOriginalPx = originalPx;
            UpdateCalibrationPreview(localPoint, localPoint);
            RefreshDebugText();
            return;
        }

        calibrationCurrentOriginalPx = originalPx;
        UpdateCalibrationPreviewForOriginalPoints(calibrationStartOriginalPx, calibrationCurrentOriginalPx);

        float distancePx = Vector2.Distance(calibrationStartOriginalPx, calibrationCurrentOriginalPx);
        if (distancePx < minCalibrationDistancePx)
            return;

        isCalibrationMode = false;
        hasCalibrationStartPoint = false;
        DiscCalibrationLineCompleted?.Invoke(distancePx);
        RefreshDebugText();
    }

    private bool IsPointerOverInteractiveUi()
    {
        return HasInteractiveUiFocus();
    }

    private bool HasInteractiveUiFocus()
    {
        if (EventSystem.current == null)
            return false;

        GameObject go = EventSystem.current.currentSelectedGameObject;
        if (go == null)
            return false;

        return go.GetComponentInParent<Button>() != null
            || go.GetComponentInParent<TMP_InputField>() != null
            || go.GetComponentInParent<Slider>() != null
            || go.GetComponentInParent<TMP_Dropdown>() != null
            || go.GetComponentInParent<Toggle>() != null;
    }

    private void UpdateCalibrationPreviewForOriginalPoints(Vector2 startOriginalPx, Vector2 endOriginalPx, Vector2? overrideEndLocalPoint = null)
    {
        if (!TryConvertOriginalPixelToViewportLocal(startOriginalPx, out Vector2 startLocal))
            return;

        Vector2 endLocal = overrideEndLocalPoint ?? startLocal;
        if (!overrideEndLocalPoint.HasValue && !TryConvertOriginalPixelToViewportLocal(endOriginalPx, out endLocal))
            return;

        UpdateCalibrationPreview(startLocal, endLocal);
    }

    public bool TryGetOriginalPixelFromViewportLocal(Vector2 localPoint, out Vector2 originalPx)
    {
        originalPx = default;

        if (circularViewportRect == null || fundusRawImage == null || sourceTexture == null)
            return false;

        float viewportRadiusUi = Mathf.Min(circularViewportRect.rect.width, circularViewportRect.rect.height) * 0.5f;
        if (localPoint.sqrMagnitude > viewportRadiusUi * viewportRadiusUi)
            return false;

        float viewportDiameterUi = viewportRadiusUi * 2f;
        if (viewportDiameterUi <= 0.001f || currentDiameterPx <= 0.001f)
            return false;

        float uiScale = viewportDiameterUi / currentDiameterPx;
        Vector2 imageLocal = localPoint - fundusRawImage.rectTransform.anchoredPosition;

        float originalX = imageLocal.x / uiScale + texWidth * 0.5f;
        float originalY = texHeight * 0.5f - imageLocal.y / uiScale;

        if (originalX < 0f || originalY < 0f || originalX > texWidth - 1 || originalY > texHeight - 1)
            return false;

        originalPx = new Vector2(originalX, originalY);
        return true;
    }

    private bool TryConvertOriginalPixelToViewportLocal(Vector2 originalPx, out Vector2 localPoint)
    {
        localPoint = default;

        if (circularViewportRect == null || currentDiameterPx <= 0.001f)
            return false;

        float viewportDiameterUi = Mathf.Min(circularViewportRect.rect.width, circularViewportRect.rect.height);
        if (viewportDiameterUi <= 0.001f)
            return false;

        float uiScale = viewportDiameterUi / currentDiameterPx;
        localPoint = new Vector2(
            (originalPx.x - texWidth * 0.5f) * uiScale + fundusRawImage.rectTransform.anchoredPosition.x,
            (texHeight * 0.5f - originalPx.y) * uiScale + fundusRawImage.rectTransform.anchoredPosition.y);
        return true;
    }

    private void UpdateCalibrationPreview(Vector2 startLocal, Vector2 endLocal)
    {
        if (calibrationPreviewStartMarker != null)
            calibrationPreviewStartMarker.anchoredPosition = startLocal;

        if (calibrationPreviewEndMarker != null)
            calibrationPreviewEndMarker.anchoredPosition = endLocal;

        if (calibrationLine != null)
        {
            Vector2 delta = endLocal - startLocal;
            calibrationLine.anchoredPosition = (startLocal + endLocal) * 0.5f;
            calibrationLine.sizeDelta = new Vector2(delta.magnitude, calibrationLine.sizeDelta.y);
            calibrationLine.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(delta.y, delta.x) * Mathf.Rad2Deg);
        }

        SetCalibrationPreviewVisible(true);
    }

    private void SetCalibrationPreviewVisible(bool visible)
    {
        if (calibrationLine != null)
            calibrationLine.gameObject.SetActive(visible);

        if (calibrationPreviewStartMarker != null)
            calibrationPreviewStartMarker.gameObject.SetActive(visible);

        if (calibrationPreviewEndMarker != null)
            calibrationPreviewEndMarker.gameObject.SetActive(visible);
    }

    private Texture2D CreateBlurredTexture(Texture2D source, int radius)
    {
        if (source == null)
            return null;

        Color[] src = source.GetPixels();
        int w = source.width;
        int h = source.height;

        Color[] temp = new Color[src.Length];
        Color[] dst = new Color[src.Length];

        BoxBlurHorizontal(src, temp, w, h, radius);
        BoxBlurVertical(temp, dst, w, h, radius);

        Texture2D tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
        tex.SetPixels(dst);
        tex.Apply();
        return tex;
    }

    private void BoxBlurHorizontal(Color[] src, Color[] dst, int w, int h, int radius)
    {
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                Color sum = Color.black;
                int count = 0;

                int xmin = Mathf.Max(0, x - radius);
                int xmax = Mathf.Min(w - 1, x + radius);

                for (int xx = xmin; xx <= xmax; xx++)
                {
                    sum += src[y * w + xx];
                    count++;
                }

                dst[y * w + x] = sum / count;
            }
        }
    }

    private void BoxBlurVertical(Color[] src, Color[] dst, int w, int h, int radius)
    {
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                Color sum = Color.black;
                int count = 0;

                int ymin = Mathf.Max(0, y - radius);
                int ymax = Mathf.Min(h - 1, y + radius);

                for (int yy = ymin; yy <= ymax; yy++)
                {
                    sum += src[yy * w + x];
                    count++;
                }

                dst[y * w + x] = sum / count;
            }
        }
    }

    private bool[] DilateMask(bool[] src, int w, int h, int radius)
    {
        if (radius <= 0)
            return (bool[])src.Clone();

        bool[] dst = new bool[src.Length];
        int r2 = radius * radius;

        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                bool found = false;

                int yMin = Mathf.Max(0, y - radius);
                int yMax = Mathf.Min(h - 1, y + radius);
                int xMin = Mathf.Max(0, x - radius);
                int xMax = Mathf.Min(w - 1, x + radius);

                for (int yy = yMin; yy <= yMax && !found; yy++)
                {
                    int dy = yy - y;

                    for (int xx = xMin; xx <= xMax; xx++)
                    {
                        int dx = xx - x;
                        if (dx * dx + dy * dy > r2)
                            continue;

                        if (src[yy * w + xx])
                        {
                            found = true;
                            break;
                        }
                    }
                }

                dst[y * w + x] = found;
            }
        }

        return dst;
    }

    private float[] BlurMaskToFloat(bool[] src, int w, int h, int radius)
    {
        float[] srcF = new float[src.Length];
        for (int i = 0; i < src.Length; i++)
            srcF[i] = src[i] ? 1f : 0f;

        if (radius <= 0)
            return srcF;

        float[] temp = new float[srcF.Length];
        float[] dst = new float[srcF.Length];

        int kernelSize = radius * 2 + 1;
        float invKernel = 1f / kernelSize;

        for (int y = 0; y < h; y++)
        {
            float sum = 0f;

            for (int k = -radius; k <= radius; k++)
            {
                int xx = Mathf.Clamp(k, 0, w - 1);
                sum += srcF[y * w + xx];
            }

            for (int x = 0; x < w; x++)
            {
                temp[y * w + x] = sum * invKernel;

                int removeX = Mathf.Clamp(x - radius, 0, w - 1);
                int addX = Mathf.Clamp(x + radius + 1, 0, w - 1);

                sum -= srcF[y * w + removeX];
                sum += srcF[y * w + addX];
            }
        }

        for (int x = 0; x < w; x++)
        {
            float sum = 0f;

            for (int k = -radius; k <= radius; k++)
            {
                int yy = Mathf.Clamp(k, 0, h - 1);
                sum += temp[yy * w + x];
            }

            for (int y = 0; y < h; y++)
            {
                dst[y * w + x] = Mathf.Clamp01(sum * invKernel);

                int removeY = Mathf.Clamp(y - radius, 0, h - 1);
                int addY = Mathf.Clamp(y + radius + 1, 0, h - 1);

                sum -= temp[removeY * w + x];
                sum += temp[addY * w + x];
            }
        }

        return dst;
    }

    private float SampleSoftMaskBilinear(float x, float y)
    {
        if (x < 0 || y < 0 || x > texWidth - 1 || y > texHeight - 1)
            return 0f;

        int x0 = Mathf.FloorToInt(x);
        int y0 = Mathf.FloorToInt(y);
        int x1 = Mathf.Min(x0 + 1, texWidth - 1);
        int y1 = Mathf.Min(y0 + 1, texHeight - 1);

        float tx = x - x0;
        float ty = y - y0;

        float v00 = moveSoftMask[y0 * texWidth + x0];
        float v10 = moveSoftMask[y0 * texWidth + x1];
        float v01 = moveSoftMask[y1 * texWidth + x0];
        float v11 = moveSoftMask[y1 * texWidth + x1];

        float vx0 = Mathf.Lerp(v00, v10, tx);
        float vx1 = Mathf.Lerp(v01, v11, tx);

        return Mathf.Lerp(vx0, vx1, ty);
    }

    private float GetCameraTotalDeg()
    {
        switch (cameraPreset)
        {
            case CameraPreset.Optos200: return 200f;
            case CameraPreset.Clarus133: return 133f;
            case CameraPreset.Montage267: return 267f;
            case CameraPreset.Custom: return customCameraTotalDeg;
            default: return 200f;
        }
    }

    private float GetLensHalfDeg()
    {
        switch (lensPreset)
        {
            case WorkingLensPreset.GoldmannWorking38: return 38f;
            case WorkingLensPreset.KriegerWorking41: return 41f;
            case WorkingLensPreset.PanfundoscopeWorking70: return 70f;
            case WorkingLensPreset.MainsterWorking60: return 60f;
            default: return 38f;
        }
    }

private float SphericalAreaRatio(float thetaGHalfDeg, float thetaIHalfDeg)
    {
        // --- 引入李斯丁(Listing)简约眼模型物理参数 ---
        float R = 11.39f; // 眼球几何半径 mm
        float d = 5.73f;  // 角膜顶点到结点N的距离 mm
        float ratio_Rd = (R - d) / R; // 约等于 0.4969

        // 1. 将角度转换为弧度 (此时传入的参数已经是正确的半场角)
        // thetaGHalfDeg: 接触镜的半场角 (如 Goldmann 38°, Panfundoscope 70°)
        // thetaIHalfDeg: 照相机的半场角 (如 200°全角 / 2 = 100°)
        float theta = thetaGHalfDeg * Mathf.Deg2Rad;       
        float phi_Camera = thetaIHalfDeg * Mathf.Deg2Rad;  

        // 2. 核心修正：利用几何公式计算接触镜在视网膜上对应的真实球心半角 phi
        // 公式: phi = theta + arcsin((R-d)/R * sin(theta))
        float phi_Lens = theta + Mathf.Asin(ratio_Rd * Mathf.Sin(theta));

        // 3. 计算球冠面积之比
        // 照相机拍摄到的总视网膜表面积对应的分母 (1 - cos(phi_Camera))
        float denom = 1f - Mathf.Cos(phi_Camera);
        if (Mathf.Abs(denom) < 1e-6f)
            return 0f;

        // 医生视野表面积与照相机表面积之比
        float p = (1f - Mathf.Cos(phi_Lens)) / denom;
        
        return Mathf.Clamp01(p);
    }

    private void RefreshDebugText()
    {
        if (debugText == null)
            return;

        if (!isReady)
        {
            debugText.text = "FOV not ready.";
            return;
        }

        float thetaIHalfDeg = GetCameraTotalDeg() * 0.5f;
        float thetaGHalfDeg = GetLensHalfDeg();
        float p = SphericalAreaRatio(thetaGHalfDeg, thetaIHalfDeg);
        string calibrationText = hasDiscCalibration
            ? $"calibrated ({calibratedDiscDiameterPxOriginal:F1}px -> {calibratedPixelToUmOriginal:F3} um/px)"
            : (isCalibrationMode ? "marking optic disc" : "not calibrated");

        debugText.text =
            $"Lens: {GetLensDisplayName()}\n" +
            $"Camera Total FOV: {GetCameraTotalDeg():F1}°\n" +
            $"Lens Half FOV: {thetaGHalfDeg:F1}°\n" +
            $"Area Ratio p: {p:F4}\n" +
            $"Valid Pixels ΣM: {validPixelCount}\n" +
            $"Diameter: {currentDiameterPx:F1}px\n" +
            $"Radius: {currentRadiusPx:F1}px\n" +
            $"Center: ({currentCenterPx.x:F1}, {currentCenterPx.y:F1})\n" +
            $"Focus: {focusNormalized:F2}\n" +
            $"Calibration: {calibrationText}";
    }

    private string GetLensDisplayName()
    {
        switch (lensPreset)
        {
            case WorkingLensPreset.GoldmannWorking38: return "Goldmann±38°";
            case WorkingLensPreset.KriegerWorking41: return "Krieger±41°";
            case WorkingLensPreset.PanfundoscopeWorking70: return "Panfundoscope±70°";
            case WorkingLensPreset.MainsterWorking60: return "Mainster±60°";
            default: return lensPreset.ToString();
        }
    }
}