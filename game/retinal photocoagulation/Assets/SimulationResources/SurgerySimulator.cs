using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using TMPro;

/// <summary>
/// 手术模拟器主控脚本：整合物理计算、图像渲染、光学标定、视野控制及小地图
/// </summary>
public class SurgerySimulator : MonoBehaviour, IPointerDownHandler, IDragHandler, IPointerUpHandler, IScrollHandler
{
    [Header("基础组件引用")]
    public RawImage fundusImage;       // 眼底巨图
    public RectTransform viewWindow;   // 观察窗（带 Rect Mask 2D）
    public GameObject slitLampOverlay; // 裂隙灯遮罩层
    public RectTransform slitAperture; // 裂隙镜缝隙可视区域（可选，建议绑定）
    public RectTransform aimingRing;   // 绿色光斑瞄准圈
    public CanvasGroup flashOverlay;   // 击发闪光层
    public RectTransform calibrationLine; // 标定用虚线

    [Header("裂隙镜边界参数")]
    [Range(0.05f, 1f)] public float slitWidthRatioFallback = 0.12f;  // 未绑定缝隙 Rect 时，按观察窗宽度比例估算
    [Range(0.05f, 1f)] public float slitHeightRatioFallback = 1.0f;  // 未绑定缝隙 Rect 时，按观察窗高度比例估算

    [Header("小地图系统")]
    public RawImage minimapImage;      // 小地图底图
    public RectTransform roiIndicator;  // 小地图中的视野绿框
    public GameObject minimapPanel;     // 小地图整体容器
    public bool autoFindMinimapRefs = true;
    private bool isMinimapLarge = false;

    [Header("右侧统计面板")]
    public GameObject shotStatsPanel;
    public GameObject timeStatsPanel;
    public TMP_Text shotCountText;
    public TMP_Text elapsedTimeText;
    public bool autoFindStatsRefs = true;

    [Header("右侧参数展示面板")]
    public GameObject parameterStatsPanel;
    public TMP_Text wavelengthText;
    public TMP_Text powerText;
    public TMP_Text durationText;
    public TMP_Text spotSizeText;
    public bool autoFindParameterRefs = true;
    public bool parameterPanelVisibleByUser = true;

    [Header("标定按钮控制")]
    public Button realCalibrationButton;
    public GameObject realCalibrationButtonRoot;
    public bool autoFindCalibrationButton = true;
    private readonly System.Collections.Generic.List<GameObject> calibrationButtonRoots = new System.Collections.Generic.List<GameObject>();

    [Header("光学参数与标定")]
    public float targetFovUm = 6000f;   // 目标物理视野 (6mm)
    public float pixelToUm = 2.0f;      // 标定出的像素/微米比
    public bool isCalibrating = false;  // 是否处于标定状态
    public bool hasCompletedCalibration = false; // 是否已完成视盘标定
    private Vector2 calibrationStartPos;

    [Header("当前手术参数")]
    public float currentPower = 200f;
    public float currentSpotSize = 200f;
    public float currentDuration = 100f;
    public float currentWavelength = 532f;

    [Header("视野控制 (操纵杆)")]
    public float panSpeed = 600f;
    public bool invertPan = true;
    public float currentZ = 0f;         // 当前手动调节的焦段
    public float flashFadeSpeed = 5f;   // 闪光消退速度

    private LaserPhysicsModel physicsModel;
    private Material blurMat;           // 引用眼底图材质用于控制模糊
    private Image roiIndicatorImage;
    private Text shotCountTextLegacy;
    private Text elapsedTimeTextLegacy;
    private Text wavelengthTextLegacy;
    private Text powerTextLegacy;
    private Text durationTextLegacy;
    private Text spotSizeTextLegacy;
    private int totalShotCount;
    private float calibrationCompleteTime = -1f;

    private const string DefaultMinimapImageName = "RightMinimap";
    private const string DefaultRoiName = "ROIIndicator";
    private const string DefaultShotStatsPanelName = "ShotStatsPanel";
    private const string DefaultTimeStatsPanelName = "TimeStatsPanel";
    private const string DefaultParameterPanelName = "ParameterStatsPanel";
    private const string DefaultShotCountTextName = "ShotCountText";
    private const string DefaultElapsedTimeTextName = "ElapsedTimeText";
    private const string DefaultWavelengthTextName = "WavelengthText";
    private const string DefaultPowerTextName = "PowerText";
    private const string DefaultDurationTextName = "DurationText";
    private const string DefaultSpotSizeTextName = "SpotSizeText";
    private const string DefaultCalibrationButtonName = "Btn_Calib";

    void Start()
    {
        // 1. 初始化物理引擎
        physicsModel = new LaserPhysicsModel(z_bias: 0.0f);

        // 2. 自动获取组件
        if (fundusImage == null) fundusImage = GetComponent<RawImage>();
        if (viewWindow == null && fundusImage.transform.parent != null)
            viewWindow = fundusImage.transform.parent.GetComponent<RectTransform>();

        if (autoFindMinimapRefs)
        {
            TryAutoBindMinimapReferences();
        }

        if (autoFindStatsRefs)
        {
            TryAutoBindStatsReferences();
        }

        if (autoFindParameterRefs)
        {
            TryAutoBindParameterReferences();
        }

        if (autoFindCalibrationButton)
        {
            TryAutoBindCalibrationButton();
        }

        // 3. 强制建立安全画布 (RGBA32)，防止格式不支持报错
        if (fundusImage.texture != null)
        {
            Texture2D source = (Texture2D)fundusImage.texture;
            Texture2D cloned = new Texture2D(source.width, source.height, TextureFormat.RGBA32, false);
            cloned.SetPixels(source.GetPixels());
            cloned.Apply();
            fundusImage.texture = cloned;
            
            // 获取材质引用（需先在 Inspector 给 RawImage 挂载你建的 UIBlur 材质）
            blurMat = fundusImage.material;
            
            // 同步小地图底图：使用当前可写纹理，保证激光灼斑和主图一致
            if (minimapImage != null) minimapImage.texture = cloned;
        }

        // 4. 初始 UI 状态
        if (slitLampOverlay) slitLampOverlay.SetActive(false);
        if (flashOverlay) flashOverlay.alpha = 0f;
        if (calibrationLine) calibrationLine.gameObject.SetActive(false);
        if (aimingRing) aimingRing.gameObject.SetActive(false);
        if (roiIndicator != null) roiIndicatorImage = roiIndicator.GetComponent<Image>();
        RefreshStatsPanel();
        RefreshCalibrationButtonVisibility();
    }

    void Update()
    {
        if (autoFindMinimapRefs && (minimapImage == null || roiIndicator == null || roiIndicatorImage == null))
        {
            TryAutoBindMinimapReferences();
        }

        if (autoFindStatsRefs && (!HasShotCountLabel() || !HasElapsedTimeLabel()))
        {
            TryAutoBindStatsReferences();
        }

        if (autoFindParameterRefs && !HasAllParameterLabels())
        {
            TryAutoBindParameterReferences();
        }

        if (autoFindCalibrationButton && realCalibrationButton == null)
        {
            TryAutoBindCalibrationButton();
        }

        if (minimapImage != null && fundusImage != null && minimapImage.texture == null)
        {
            minimapImage.texture = fundusImage.texture;
        }

        HandlePanInput();
        HandleHotkeys();
        UpdateVisualEffects();
        UpdateMinimapROI();
        RefreshStatsPanel();
        RefreshParameterPanel();
        RefreshCalibrationButtonVisibility();
    }

    private void TryAutoBindCalibrationButton()
    {
        if (realCalibrationButtonRoot == null && realCalibrationButton != null)
        {
            realCalibrationButtonRoot = realCalibrationButton.gameObject;
        }

        if (realCalibrationButtonRoot == null)
        {
            GameObject buttonObj = GameObject.Find(DefaultCalibrationButtonName);
            if (buttonObj != null)
            {
                realCalibrationButtonRoot = buttonObj;
            }
        }

        if (realCalibrationButton == null && realCalibrationButtonRoot != null)
        {
            realCalibrationButton = realCalibrationButtonRoot.GetComponent<Button>();
            if (realCalibrationButton == null)
            {
                realCalibrationButton = realCalibrationButtonRoot.GetComponentInChildren<Button>(true);
            }
        }

        if (realCalibrationButtonRoot != null)
        {
            RegisterCalibrationButtonRoot(realCalibrationButtonRoot);
        }

        Button[] allButtons = FindObjectsOfType<Button>(true);
        for (int i = 0; i < allButtons.Length; i++)
        {
            Button btn = allButtons[i];
            if (btn == null) continue;

            int count = btn.onClick.GetPersistentEventCount();
            for (int j = 0; j < count; j++)
            {
                Object target = btn.onClick.GetPersistentTarget(j);
                string method = btn.onClick.GetPersistentMethodName(j);
                if (target == this && method == nameof(StartCalibrationMode))
                {
                    RegisterCalibrationButtonRoot(btn.gameObject);
                    break;
                }
            }
        }
    }

    private void RegisterCalibrationButtonRoot(GameObject root)
    {
        if (root == null) return;
        if (!calibrationButtonRoots.Contains(root))
        {
            calibrationButtonRoots.Add(root);
        }
    }

    private void RefreshCalibrationButtonVisibility()
    {
        if (realCalibrationButtonRoot == null && realCalibrationButton != null)
        {
            realCalibrationButtonRoot = realCalibrationButton.gameObject;
        }

        if (realCalibrationButtonRoot != null)
        {
            RegisterCalibrationButtonRoot(realCalibrationButtonRoot);
        }

        bool shouldShow = !hasCompletedCalibration;

        for (int i = calibrationButtonRoots.Count - 1; i >= 0; i--)
        {
            GameObject root = calibrationButtonRoots[i];
            if (root == null)
            {
                calibrationButtonRoots.RemoveAt(i);
                continue;
            }

            if (root.activeSelf != shouldShow)
            {
                root.SetActive(shouldShow);
            }

            CanvasGroup group = root.GetComponent<CanvasGroup>();
            if (group != null)
            {
                group.alpha = shouldShow ? 1f : 0f;
                group.interactable = shouldShow;
                group.blocksRaycasts = shouldShow;
            }
        }

        if (realCalibrationButton != null)
        {
            realCalibrationButton.interactable = shouldShow;
            if (realCalibrationButton.targetGraphic != null)
            {
                realCalibrationButton.targetGraphic.enabled = shouldShow;
            }
        }
    }

    private void TryAutoBindMinimapReferences()
    {
        if (minimapPanel == null) return;

        if (minimapImage == null)
        {
            Transform t = minimapPanel.transform.Find(DefaultMinimapImageName);
            if (t != null)
            {
                minimapImage = t.GetComponent<RawImage>();
            }

            if (minimapImage == null)
            {
                minimapImage = minimapPanel.GetComponentInChildren<RawImage>(true);
            }
        }

        if (roiIndicator == null)
        {
            Transform t = minimapPanel.transform.Find(DefaultRoiName);
            if (t != null)
            {
                roiIndicator = t as RectTransform;
            }

            if (roiIndicator == null)
            {
                Image[] imgs = minimapPanel.GetComponentsInChildren<Image>(true);
                foreach (Image img in imgs)
                {
                    string n = img.gameObject.name.ToLowerInvariant();
                    if (n.Contains("roi") || n.Contains("indicator"))
                    {
                        roiIndicator = img.rectTransform;
                        break;
                    }
                }
            }
        }

        if (roiIndicator != null && roiIndicatorImage == null)
        {
            roiIndicatorImage = roiIndicator.GetComponent<Image>();
        }
    }

    private void TryAutoBindStatsReferences()
    {
        if (shotStatsPanel == null)
        {
            GameObject candidate = GameObject.Find(DefaultShotStatsPanelName);
            if (candidate != null)
            {
                shotStatsPanel = candidate;
            }
            else if (minimapPanel != null)
            {
                Transform parent = minimapPanel.transform.parent;
                if (parent != null)
                {
                    Transform panelTransform = parent.Find(DefaultShotStatsPanelName);
                    if (panelTransform != null)
                    {
                        shotStatsPanel = panelTransform.gameObject;
                    }
                }
            }
        }

        if (timeStatsPanel == null)
        {
            GameObject candidate = GameObject.Find(DefaultTimeStatsPanelName);
            if (candidate != null)
            {
                timeStatsPanel = candidate;
            }
            else if (minimapPanel != null)
            {
                Transform parent = minimapPanel.transform.parent;
                if (parent != null)
                {
                    Transform panelTransform = parent.Find(DefaultTimeStatsPanelName);
                    if (panelTransform != null)
                    {
                        timeStatsPanel = panelTransform.gameObject;
                    }
                }
            }
        }

        if (!HasShotCountLabel())
        {
            if (shotStatsPanel != null)
            {
                Transform textTransform = shotStatsPanel.transform.Find(DefaultShotCountTextName);
                if (textTransform != null)
                {
                    shotCountText = textTransform.GetComponent<TMP_Text>();
                    if (shotCountText == null)
                    {
                        shotCountTextLegacy = textTransform.GetComponent<Text>();
                    }
                }
            }

            if (!HasShotCountLabel())
            {
                GameObject textObj = GameObject.Find(DefaultShotCountTextName);
                if (textObj != null)
                {
                    shotCountText = textObj.GetComponent<TMP_Text>();
                    if (shotCountText == null)
                    {
                        shotCountTextLegacy = textObj.GetComponent<Text>();
                    }
                }
            }

            if (!HasShotCountLabel() && shotStatsPanel != null)
            {
                TMP_Text[] tmpTexts = shotStatsPanel.GetComponentsInChildren<TMP_Text>(true);
                foreach (TMP_Text text in tmpTexts)
                {
                    if (text.gameObject.name.ToLowerInvariant().Contains("shot"))
                    {
                        shotCountText = text;
                        break;
                    }
                }

                if (!HasShotCountLabel())
                {
                    Text[] texts = shotStatsPanel.GetComponentsInChildren<Text>(true);
                    foreach (Text text in texts)
                    {
                        if (text.gameObject.name.ToLowerInvariant().Contains("shot"))
                        {
                            shotCountTextLegacy = text;
                            break;
                        }
                    }
                }
            }
        }

        if (!HasElapsedTimeLabel())
        {
            if (timeStatsPanel != null)
            {
                Transform textTransform = timeStatsPanel.transform.Find(DefaultElapsedTimeTextName);
                if (textTransform != null)
                {
                    elapsedTimeText = textTransform.GetComponent<TMP_Text>();
                    if (elapsedTimeText == null)
                    {
                        elapsedTimeTextLegacy = textTransform.GetComponent<Text>();
                    }
                }
            }

            if (!HasElapsedTimeLabel())
            {
                GameObject textObj = GameObject.Find(DefaultElapsedTimeTextName);
                if (textObj != null)
                {
                    elapsedTimeText = textObj.GetComponent<TMP_Text>();
                    if (elapsedTimeText == null)
                    {
                        elapsedTimeTextLegacy = textObj.GetComponent<Text>();
                    }
                }
            }

            if (!HasElapsedTimeLabel() && timeStatsPanel != null)
            {
                TMP_Text[] tmpTexts = timeStatsPanel.GetComponentsInChildren<TMP_Text>(true);
                foreach (TMP_Text text in tmpTexts)
                {
                    string name = text.gameObject.name.ToLowerInvariant();
                    if (name.Contains("elapsed") || name.Contains("time"))
                    {
                        elapsedTimeText = text;
                        break;
                    }
                }

                if (!HasElapsedTimeLabel())
                {
                    Text[] texts = timeStatsPanel.GetComponentsInChildren<Text>(true);
                    foreach (Text text in texts)
                    {
                        string name = text.gameObject.name.ToLowerInvariant();
                        if (name.Contains("elapsed") || name.Contains("time"))
                        {
                            elapsedTimeTextLegacy = text;
                            break;
                        }
                    }
                }
            }
        }
    }

    private bool HasShotCountLabel()
    {
        return shotCountText != null || shotCountTextLegacy != null;
    }

    private bool HasElapsedTimeLabel()
    {
        return elapsedTimeText != null || elapsedTimeTextLegacy != null;
    }

    private void SetShotCountLabel(string content)
    {
        if (shotCountText != null) shotCountText.text = content;
        if (shotCountTextLegacy != null) shotCountTextLegacy.text = content;
    }

    private void SetElapsedTimeLabel(string content)
    {
        if (elapsedTimeText != null) elapsedTimeText.text = content;
        if (elapsedTimeTextLegacy != null) elapsedTimeTextLegacy.text = content;
    }

    private void RefreshStatsPanel()
    {
        SetShotCountLabel($"Shots: {totalShotCount}");

        if (calibrationCompleteTime < 0f)
        {
            SetElapsedTimeLabel("Elapsed: --:--");
        }
        else
        {
            float elapsedSeconds = Time.unscaledTime - calibrationCompleteTime;
            int minutes = Mathf.FloorToInt(elapsedSeconds / 60f);
            int seconds = Mathf.FloorToInt(elapsedSeconds % 60f);
            SetElapsedTimeLabel($"Elapsed: {minutes:00}:{seconds:00}");
        }

        bool slitLampOn = slitLampOverlay != null && slitLampOverlay.activeSelf;
        bool shouldShow = slitLampOn && parameterPanelVisibleByUser;

        if (shotStatsPanel != null)
        {
            if (shotStatsPanel.activeSelf != shouldShow)
            {
                shotStatsPanel.SetActive(shouldShow);
            }
        }

        if (timeStatsPanel != null)
        {
            if (timeStatsPanel.activeSelf != shouldShow)
            {
                timeStatsPanel.SetActive(shouldShow);
            }
        }
    }

    private void TryAutoBindParameterReferences()
    {
        if (parameterStatsPanel == null)
        {
            GameObject panel = GameObject.Find(DefaultParameterPanelName);
            if (panel != null)
            {
                parameterStatsPanel = panel;
            }
        }

        BindParameterLabel(ref wavelengthText, ref wavelengthTextLegacy, DefaultWavelengthTextName, "wavelength");
        BindParameterLabel(ref powerText, ref powerTextLegacy, DefaultPowerTextName, "power");
        BindParameterLabel(ref durationText, ref durationTextLegacy, DefaultDurationTextName, "duration");
        BindParameterLabel(ref spotSizeText, ref spotSizeTextLegacy, DefaultSpotSizeTextName, "spot");
    }

    private void BindParameterLabel(ref TMP_Text tmpLabel, ref Text legacyLabel, string defaultName, string keyword)
    {
        if (tmpLabel != null || legacyLabel != null) return;

        if (parameterStatsPanel != null)
        {
            Transform t = parameterStatsPanel.transform.Find(defaultName);
            if (t != null)
            {
                tmpLabel = t.GetComponent<TMP_Text>();
                if (tmpLabel == null) legacyLabel = t.GetComponent<Text>();
            }
        }

        if (tmpLabel == null && legacyLabel == null)
        {
            GameObject textObj = GameObject.Find(defaultName);
            if (textObj != null)
            {
                tmpLabel = textObj.GetComponent<TMP_Text>();
                if (tmpLabel == null) legacyLabel = textObj.GetComponent<Text>();
            }
        }

        if (tmpLabel == null && legacyLabel == null && parameterStatsPanel != null)
        {
            TMP_Text[] tmpTexts = parameterStatsPanel.GetComponentsInChildren<TMP_Text>(true);
            foreach (TMP_Text t in tmpTexts)
            {
                string name = t.gameObject.name.ToLowerInvariant();
                if (name.Contains(keyword))
                {
                    tmpLabel = t;
                    break;
                }
            }

            if (tmpLabel == null)
            {
                Text[] texts = parameterStatsPanel.GetComponentsInChildren<Text>(true);
                foreach (Text t in texts)
                {
                    string name = t.gameObject.name.ToLowerInvariant();
                    if (name.Contains(keyword))
                    {
                        legacyLabel = t;
                        break;
                    }
                }
            }
        }
    }

    private bool HasAllParameterLabels()
    {
        return (wavelengthText != null || wavelengthTextLegacy != null)
            && (powerText != null || powerTextLegacy != null)
            && (durationText != null || durationTextLegacy != null)
            && (spotSizeText != null || spotSizeTextLegacy != null);
    }

    private void SetParameterLabel(TMP_Text tmpLabel, Text legacyLabel, string content)
    {
        if (tmpLabel != null) tmpLabel.text = content;
        if (legacyLabel != null) legacyLabel.text = content;
    }

    private void SetDeviceParameterLabel(TMP_Text tmpLabel, Text legacyLabel, string title, int value, string unit)
    {
        if (tmpLabel != null)
        {
            tmpLabel.richText = true;
            tmpLabel.enableWordWrapping = false;
            tmpLabel.text = $"<size=72%><color=#9FB2C2>{title}</color></size>\n<size=118%><b>{value}</b></size> <size=78%><color=#C9D6E2>{unit}</color></size>";
        }

        if (legacyLabel != null)
        {
            legacyLabel.text = $"{title}\n{value} {unit}";
        }
    }

    private void RefreshParameterPanel()
    {
        SetDeviceParameterLabel(wavelengthText, wavelengthTextLegacy, "WAVELENGTH", Mathf.RoundToInt(currentWavelength), "nm");
        SetDeviceParameterLabel(powerText, powerTextLegacy, "POWER", Mathf.RoundToInt(currentPower), "mW");
        SetDeviceParameterLabel(durationText, durationTextLegacy, "EXPOSURE", Mathf.RoundToInt(currentDuration), "ms");
        SetDeviceParameterLabel(spotSizeText, spotSizeTextLegacy, "SPOT SIZE", Mathf.RoundToInt(currentSpotSize), "um");

        bool slitLampOn = slitLampOverlay != null && slitLampOverlay.activeSelf;
        bool shouldShow = slitLampOn && parameterPanelVisibleByUser;
        if (parameterStatsPanel != null)
        {
            if (parameterStatsPanel.activeSelf != shouldShow)
            {
                parameterStatsPanel.SetActive(shouldShow);
            }
        }
    }

    // ==========================================
    // 1. 视野控制与边界限制
    // ==========================================
    private void HandlePanInput()
    {
        float h = Input.GetAxis("Horizontal");
        float v = Input.GetAxis("Vertical");

        if (viewWindow == null || fundusImage == null) return;

        Vector2 newPos = fundusImage.rectTransform.anchoredPosition;
        if (h != 0 || v != 0)
        {
            float direction = invertPan ? -1f : 1f;
            Vector2 movement = new Vector2(h, v) * direction * panSpeed * Time.deltaTime;
            newPos += movement;
        }

        // 每帧都执行一次夹紧，避免切换裂隙镜/缩放后没有输入时仍越界
        float scale = fundusImage.rectTransform.localScale.x;
        float sW = fundusImage.rectTransform.rect.width * scale;
        float sH = fundusImage.rectTransform.rect.height * scale;
        GetPanLimits(sW, sH, out Vector2 minPos, out Vector2 maxPos, out _);

        fundusImage.rectTransform.anchoredPosition = new Vector2(
            Mathf.Clamp(newPos.x, minPos.x, maxPos.x),
            Mathf.Clamp(newPos.y, minPos.y, maxPos.y)
        );
    }

    private Rect GetEffectiveViewRectInViewWindow()
    {
        if (viewWindow == null)
        {
            return new Rect(0f, 0f, 0f, 0f);
        }

        Rect vwRect = viewWindow.rect;

        if (slitLampOverlay != null && slitLampOverlay.activeSelf)
        {
            if (slitAperture != null)
            {
                Vector3[] worldCorners = new Vector3[4];
                slitAperture.GetWorldCorners(worldCorners);

                Vector3 p0 = viewWindow.InverseTransformPoint(worldCorners[0]);
                Vector3 p1 = viewWindow.InverseTransformPoint(worldCorners[1]);
                Vector3 p2 = viewWindow.InverseTransformPoint(worldCorners[2]);
                Vector3 p3 = viewWindow.InverseTransformPoint(worldCorners[3]);

                float minX = Mathf.Min(Mathf.Min(p0.x, p1.x), Mathf.Min(p2.x, p3.x));
                float maxX = Mathf.Max(Mathf.Max(p0.x, p1.x), Mathf.Max(p2.x, p3.x));
                float minY = Mathf.Min(Mathf.Min(p0.y, p1.y), Mathf.Min(p2.y, p3.y));
                float maxY = Mathf.Max(Mathf.Max(p0.y, p1.y), Mathf.Max(p2.y, p3.y));

                // 夹到观察窗内，防止配置偏移导致异常
                minX = Mathf.Max(minX, vwRect.xMin);
                maxX = Mathf.Min(maxX, vwRect.xMax);
                minY = Mathf.Max(minY, vwRect.yMin);
                maxY = Mathf.Min(maxY, vwRect.yMax);

                if (maxX > minX && maxY > minY)
                {
                    return Rect.MinMaxRect(minX, minY, maxX, maxY);
                }
            }

            // 未绑定缝隙 Rect 时，按比例回退估算
            float w = vwRect.width * Mathf.Clamp01(slitWidthRatioFallback);
            float h = vwRect.height * Mathf.Clamp01(slitHeightRatioFallback);
            Vector2 c = vwRect.center;
            return new Rect(c.x - w / 2f, c.y - h / 2f, w, h);
        }

        return vwRect;
    }

    private Vector2 GetEffectiveViewSize()
    {
        return GetEffectiveViewRectInViewWindow().size;
    }

    private void GetPanLimits(float scaledWidth, float scaledHeight, out Vector2 minPos, out Vector2 maxPos, out Vector2 effectiveViewSize)
    {
        Rect effectiveRect = GetEffectiveViewRectInViewWindow();
        effectiveViewSize = effectiveRect.size;

        // 允许范围来自“图像覆盖可视区域”的不等式，支持缝隙偏移后的非对称边界
        float minX = effectiveRect.xMax - scaledWidth / 2f;
        float maxX = effectiveRect.xMin + scaledWidth / 2f;
        float minY = effectiveRect.yMax - scaledHeight / 2f;
        float maxY = effectiveRect.yMin + scaledHeight / 2f;

        if (minX > maxX)
        {
            float cx = effectiveRect.center.x;
            minX = cx;
            maxX = cx;
        }
        if (minY > maxY)
        {
            float cy = effectiveRect.center.y;
            minY = cy;
            maxY = cy;
        }

        minPos = new Vector2(minX, minY);
        maxPos = new Vector2(maxX, maxY);
    }

    // ==========================================
    // 2. 动态模糊与闪光特效
    // ==========================================
    private void UpdateVisualEffects()
    {
        // 闪光消退
        if (flashOverlay != null && flashOverlay.alpha > 0)
        {
            flashOverlay.alpha = Mathf.MoveTowards(flashOverlay.alpha, 0f, Time.deltaTime * flashFadeSpeed);
        }

        // 动态失焦模糊
        if (blurMat != null)
        {
            // 景深模型：距离中心越远，由于球面率 Z 偏移越大
            float distFromCenter = fundusImage.rectTransform.anchoredPosition.magnitude;
            float optimalZ = distFromCenter * 0.45f; 
            float focusDiff = Mathf.Abs(currentZ - optimalZ);
            
            // 将焦距差映射到 Shader 的模糊强度上
            float blurStrength = Mathf.Clamp(focusDiff / 60f, 0, 8f);
            blurMat.SetFloat("_BlurSize", blurStrength);
        }

        // 瞄准圈跟随与动态缩放
        if (aimingRing != null && !isCalibrating && slitLampOverlay.activeSelf)
        {
            aimingRing.gameObject.SetActive(true);
            float scale = fundusImage.rectTransform.localScale.x;
            float diameter = (currentSpotSize / pixelToUm) * scale;
            aimingRing.sizeDelta = new Vector2(diameter, diameter);

            RectTransformUtility.ScreenPointToLocalPointInRectangle(
                viewWindow, Input.mousePosition, null, out Vector2 localMouse);
            aimingRing.anchoredPosition = localMouse;
        }
    }

    // ==========================================
    // 3. 小地图与 ROI 绿框逻辑
    // ==========================================
    private void UpdateMinimapROI()
    {
        if (roiIndicator == null || minimapImage == null || viewWindow == null) return;

        float scale = fundusImage.rectTransform.localScale.x;
        float scaledWidth = fundusImage.rectTransform.rect.width * scale;
        float scaledHeight = fundusImage.rectTransform.rect.height * scale;
        Rect miniRect = minimapImage.rectTransform.rect;

        // 小地图 ROI 与平移边界复用同一套约束，避免视觉错位
        GetPanLimits(scaledWidth, scaledHeight, out Vector2 minPos, out Vector2 maxPos, out Vector2 effectiveViewSize);
        float viewWidthRatio = Mathf.Clamp01(effectiveViewSize.x / Mathf.Max(1e-6f, scaledWidth));
        float viewHeightRatio = Mathf.Clamp01(effectiveViewSize.y / Mathf.Max(1e-6f, scaledHeight));

        // 更新绿框大小
        Vector2 roiSize = new Vector2(miniRect.width * viewWidthRatio, miniRect.height * viewHeightRatio);
        roiIndicator.sizeDelta = roiSize;

        // 按当前平移可达边界映射 ROI 位置，保证 ROI 不越界
        Vector2 imgPos = fundusImage.rectTransform.anchoredPosition;
        float px = 0f;
        float py = 0f;
        float rangeX = maxPos.x - minPos.x;
        float rangeY = maxPos.y - minPos.y;

        if (rangeX > 1e-6f)
        {
            float tX = Mathf.InverseLerp(minPos.x, maxPos.x, imgPos.x);
            // 图像平移与观察中心在底图上的位置相反
            px = Mathf.Lerp((miniRect.width - roiSize.x) / 2f, -(miniRect.width - roiSize.x) / 2f, tX);
        }
        if (rangeY > 1e-6f)
        {
            float tY = Mathf.InverseLerp(minPos.y, maxPos.y, imgPos.y);
            py = Mathf.Lerp((miniRect.height - roiSize.y) / 2f, -(miniRect.height - roiSize.y) / 2f, tY);
        }

        roiIndicator.anchoredPosition = new Vector2(
            Mathf.Clamp(px, -(miniRect.width - roiSize.x) / 2f, (miniRect.width - roiSize.x) / 2f),
            Mathf.Clamp(py, -(miniRect.height - roiSize.y) / 2f, (miniRect.height - roiSize.y) / 2f)
        );

        // 绿框闪烁
        float alpha = Mathf.PingPong(Time.time * 2f, 0.8f) + 0.2f;
        if (roiIndicatorImage == null) roiIndicatorImage = roiIndicator.GetComponent<Image>();
        if (roiIndicatorImage != null) roiIndicatorImage.color = new Color(0, 1, 0, alpha);
    }

    private void HandleHotkeys()
    {
        // M 键切换小地图大小
        if (Input.GetKeyDown(KeyCode.M) && minimapPanel != null)
        {
            isMinimapLarge = !isMinimapLarge;
            minimapPanel.transform.localScale = isMinimapLarge ? new Vector3(2.5f, 2.5f, 1) : Vector3.one;
        }

        // T 键切换参数面板显示
        if (Input.GetKeyDown(KeyCode.T))
        {
            parameterPanelVisibleByUser = !parameterPanelVisibleByUser;
        }
    }

    // ==========================================
    // 4. 输入接口实现 (激光 & 标定 & 滚轮)
    // ==========================================
    public void OnScroll(PointerEventData eventData)
    {
        // 滚轮调节焦段 (Z-Axis)
        currentZ += eventData.scrollDelta.y * 30f;
        currentZ = Mathf.Clamp(currentZ, -500f, 2500f);
    }

    public void OnPointerDown(PointerEventData eventData)
    {
        if (eventData.button != PointerEventData.InputButton.Left) return;
        RectTransformUtility.ScreenPointToLocalPointInRectangle(fundusImage.rectTransform, eventData.position, eventData.pressEventCamera, out Vector2 localPos);

        if (isCalibrating)
        {
            calibrationStartPos = localPos;
            calibrationLine.gameObject.SetActive(true);
            calibrationLine.anchoredPosition = localPos;
            calibrationLine.sizeDelta = new Vector2(0, 4f);
        }
        else
        {
            if (!hasCompletedCalibration)
            {
                Debug.LogWarning("请先完成视盘标定，再进行激光击发。");
                return;
            }
            if (FireLaser(localPos))
            {
                totalShotCount++;
            }
        }
    }

    public void OnDrag(PointerEventData eventData)
    {
        if (!isCalibrating || calibrationLine == null) return;
        RectTransformUtility.ScreenPointToLocalPointInRectangle(fundusImage.rectTransform, eventData.position, eventData.pressEventCamera, out Vector2 localPos);
        
        Vector2 dir = localPos - calibrationStartPos;
        calibrationLine.sizeDelta = new Vector2(dir.magnitude, 4f);
        calibrationLine.localEulerAngles = new Vector3(0, 0, Mathf.Atan2(dir.y, dir.x) * Mathf.Rad2Deg);
    }

    public void OnPointerUp(PointerEventData eventData)
    {
        if (!isCalibrating) return;

        RectTransformUtility.ScreenPointToLocalPointInRectangle(fundusImage.rectTransform, eventData.position, eventData.pressEventCamera, out Vector2 localPos);
        float dist = Vector2.Distance(calibrationStartPos, localPos);

        if (dist > 10f)
        {
            pixelToUm = 1500f / dist; // 视盘标定
            // 执行 Python 逻辑：强制放大图像填满物理视野
            if (viewWindow != null)
            {
                float scale = (viewWindow.rect.width * pixelToUm) / targetFovUm;
                fundusImage.rectTransform.localScale = new Vector3(scale, scale, 1f);
                fundusImage.rectTransform.anchoredPosition = Vector2.zero; // 居中
            }
            if (slitLampOverlay) slitLampOverlay.SetActive(true); // 罩上裂隙灯
            hasCompletedCalibration = true;
            if (calibrationCompleteTime < 0f)
            {
                calibrationCompleteTime = Time.unscaledTime;
            }
        }
        
        calibrationLine.gameObject.SetActive(false);
        isCalibrating = false;
    }

    // ==========================================
    // 5. 激光击发与渲染 (核心复刻)
    // ==========================================
    private bool FireLaser(Vector2 localPos)
    {
        if (flashOverlay) flashOverlay.alpha = 1f; // 击发瞬闪
        var res = physicsModel.ComputeZAndGrade(currentPower, currentSpotSize, currentDuration, currentWavelength);
        return RenderLaserSpot(localPos, res.zValue, currentPower, currentDuration, currentSpotSize);
    }

    public void StartCalibrationMode()
    {
        if (hasCompletedCalibration) return;

        if (EventSystem.current != null && EventSystem.current.currentSelectedGameObject != null)
        {
            RegisterCalibrationButtonRoot(EventSystem.current.currentSelectedGameObject);
        }

        isCalibrating = true;
    }

    private bool RenderLaserSpot(Vector2 localPos, float zValue, float power, float duration, float spotSize)
    {
        Texture2D tex = (Texture2D)fundusImage.texture;
        int tx = Mathf.RoundToInt((localPos.x + fundusImage.rectTransform.rect.width / 2f) * (tex.width / fundusImage.rectTransform.rect.width));
        int ty = Mathf.RoundToInt((localPos.y + fundusImage.rectTransform.rect.height / 2f) * (tex.height / fundusImage.rectTransform.rect.height));

        float p_n = Mathf.Clamp01((power - 50f) / 350f);
        float t_n = Mathf.Clamp01((duration - 10f) / 490f);
        float energy_n = Mathf.Clamp01(0.56f * p_n + 0.44f * t_n);
        float radius_px = (spotSize / 2f) / pixelToUm;
        float eff_radius = radius_px * (0.92f + 0.26f * Mathf.Clamp01((spotSize - 50f)/350f));

        int g = (int)Mathf.Max(8, eff_radius * (3.0f + 1.8f * energy_n));
        int xMin = Mathf.Max(0, tx - g), xMax = Mathf.Min(tex.width, tx + g + 1);
        int yMin = Mathf.Max(0, ty - g), yMax = Mathf.Min(tex.height, ty + g + 1);

        if (xMin >= xMax || yMin >= yMax) return false;

        int rw = xMax - xMin, rh = yMax - yMin;
        Color[] pxs = tex.GetPixels(xMin, yMin, rw, rh);
        Color coag = new Color(210f/255f, 220f/255f, 220f/255f);
        float burn = 0.3f + 0.7f * energy_n;

        for (int y = 0; y < rh; y++) {
            for (int x = 0; x < rw; x++) {
                float d = Vector2.Distance(new Vector2(xMin + x, yMin + y), new Vector2(tx, ty));
                float r = d / Mathf.Max(1e-6f, eff_radius);
                float core = Mathf.Exp(-Mathf.Pow(r / 0.85f, 4f));
                float edema = Mathf.Clamp01(Mathf.Exp(-Mathf.Pow(r / 1.2f, 2f)) - core);

                Color.RGBToHSV(pxs[y * rw + x], out float h, out float s, out float v);
                s *= (1f - Mathf.Clamp01(core * burn * 0.85f + edema * burn * 0.4f));
                v += core * burn * (1f - v) * 0.8f + edema * burn * (1f - v) * 0.3f;
                Color nc = Color.HSVToRGB(h, Mathf.Clamp01(s), Mathf.Clamp01(v));
                
                float op = core * burn * 0.6f;
                nc.r = 1f - (1f - nc.r) * (1f - coag.r * op);
                nc.g = 1f - (1f - nc.g) * (1f - coag.g * op);
                nc.b = 1f - (1f - nc.b) * (1f - coag.b * op);
                pxs[y * rw + x] = nc;
            }
        }
        tex.SetPixels(xMin, yMin, rw, rh, pxs);
        tex.Apply();
        return true;
    }
}