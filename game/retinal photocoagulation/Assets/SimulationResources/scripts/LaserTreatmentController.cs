using System;
using System.Globalization;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class LaserTreatmentController : MonoBehaviour
{
    [Serializable]
    private class ExportPlayerInfo
    {
        public string id;
        public string name;
    }

    [Serializable]
    private class ExportShotParams
    {
        public float power;
        public float spot_size_set;
        public float exposure_time;
        public float wavelength;
        public string mode;
        public string matrix_shape;
        public int matrix_shape_param;
        public float matrix_spacing_x_spot;
        public float matrix_rotation_deg;
        public float matrix_offset_dx;
        public float matrix_offset_dy;
    }

    [Serializable]
    private class ExportShotRecord
    {
        public int id;
        public float[] pos;
        public bool is_trial;
        public int spot_grade;
        public ExportShotParams @params;
    }

    [Serializable]
    private class ExportSessionRecord
    {
        public string session_id;
        public string task_id;
        public ExportPlayerInfo player_info;
        public List<ExportShotRecord> shots;
    }

    private struct BlurRegion
    {
        public int x;
        public int y;
        public int width;
        public int height;

        public bool IsValid => width > 0 && height > 0;
    }

    private struct ExportSnapshot
    {
        public string jsonPath;
        public string pngPath;
        public string json;
        public byte[] pngBytes;
    }

    private struct UndoShotSnapshot
    {
        public int x;
        public int y;
        public int width;
        public int height;
        public int shotCountDelta;
        public Color[] previousPixels;
        public BlurRegion blurRegion;

        public bool IsValid => previousPixels != null && width > 0 && height > 0;
    }

    [System.Serializable]
    public class FloatControl
    {
        public Slider slider;
        public TMP_InputField input;
        public float fallbackValue;

        public float ReadValue()
        {
            if (input != null && !string.IsNullOrWhiteSpace(input.text))
            {
                if (float.TryParse(input.text, NumberStyles.Float, CultureInfo.InvariantCulture, out float inv))
                    return inv;

                if (float.TryParse(input.text, out float local))
                    return local;
            }

            if (slider != null)
                return slider.value;

            return fallbackValue;
        }

        public void WriteValue(float value)
        {
            if (slider != null)
                slider.value = value;

            if (input != null)
                input.text = value.ToString("0.###", CultureInfo.InvariantCulture);
        }
    }

    [Header("Core Refs")]
    [SerializeField] private SlitLampOverlayController slitLamp;
    [SerializeField] private FundusFovController fovController;
    [SerializeField] private RawImage fundusRawImage;
    [SerializeField] private RawImage focusBlurRawImage;
    [SerializeField] private RectTransform circularViewportRect;
    [SerializeField] private RectTransform crosshairRect;
    [SerializeField] private Image crosshairImage;
    [SerializeField] private float aimMoveSpeedNormalized = 0.18f;
    [SerializeField] private float fineAimSpeedMultiplier = 0.2f;
    [SerializeField] private Image shotFlashOverlay;
    [SerializeField] private float shotFlashPeakAlpha = 0.32f;
    [SerializeField] private float shotFlashFadeSpeed = 5.5f;
    [SerializeField, Range(0f, 1f)] private float reticleFadeZoneFraction = 0.1f;
    [SerializeField] private TMP_Text statusText;

    [Header("Info Bar")]
    [SerializeField] private TMP_Text spotsValueText;
    [SerializeField] private TMP_Text timerValueText;
    [SerializeField] private TMP_Text gradeValueText;

    [Header("UI - Single Shot")]
    [SerializeField] private TMP_Dropdown modeDropdown;
    [SerializeField] private TMP_Dropdown wavelengthDropdown;
    [SerializeField] private FloatControl powerMw;
    [SerializeField] private FloatControl durationMs;
    [SerializeField] private TMP_Dropdown pulseModeDropdown;
    [SerializeField] private FloatControl intervalSeconds;
    [SerializeField] private FloatControl spotSizeUm;
    [SerializeField] private TMP_Dropdown fundusLensDropdown;
    [SerializeField] private FloatControl aimingBeamLevel;
    [SerializeField] private Toggle titrateModeToggle;

    [Header("UI - Matrix")]
    [SerializeField] private TMP_Dropdown shapeDropdown;
    [SerializeField] private FloatControl shapeParam;
    [SerializeField] private FloatControl spacingXSpot;
    [SerializeField] private FloatControl rotationDeg;
    [SerializeField] private FloatControl offsetDx;
    [SerializeField] private FloatControl offsetDy;

    [Header("Calibration")]
    [SerializeField] private Button startDiscCalibrationButton;
    [SerializeField] private Button resetCalibrationButton;
    [SerializeField] private TMP_InputField opticDiscUmInput;

    [Header("Toolbar")]
    [SerializeField] private Button undoLastButton;
    [SerializeField] private Button clearAllButton;
    [SerializeField] private Button miniMapButton;
    [SerializeField] private Button endSurgeryButton;
    [SerializeField] private GameObject popupMinimapOverlay;

    [Header("Export")]
    [SerializeField] private string outputRelativeDirectory = "Assets/SimulationResources/player_output";
    [SerializeField] private string defaultTaskId = "T001_RP_Standard";
    [SerializeField] private string defaultPlayerId = "ST_001";
    [SerializeField] private string defaultPlayerName = "Operator";

    [Header("Runtime")]
    [SerializeField] private KeyCode fireKey = KeyCode.Space;
    [SerializeField] private float defaultPixelToUm = 2.0f;
    [SerializeField] private int blurRadiusForFocusLayer = 5;
    [SerializeField] private bool rebuildBlurAfterEveryShot = true;

    private LaserPhysicalModel physicalModel;
    private Texture2D workingTexture;
    private Texture2D workingBlurTexture;
    private Texture2D baseTextureSnapshot;
    private Color[] baseTexturePixels;
    private Color[] baseBlurPixels;

    private readonly List<ExportShotRecord> shotHistory = new List<ExportShotRecord>();
    private readonly List<UndoShotSnapshot> undoShotHistory = new List<UndoShotSnapshot>();
    private string currentSessionId;
    private float repeatTimer = 0f;
    private int shotCount = 0;
    private float surgeryElapsedSeconds = 0f;
    private int lastComputedGrade = 0;
    private int lastInfoBarSecond = -1;
    private bool blurRebuildQueued = false;
    private Coroutine blurRebuildCoroutine;
    private bool isExporting = false;
    private BlurRegion pendingBlurRegion;
    private Vector2 aimOffsetNormalized = Vector2.zero;
    private float shotFlashAlpha = 0f;

    private void Awake()
    {
        physicalModel = new LaserPhysicalModel();
        currentSessionId = BuildSessionId();

        if (shotFlashOverlay == null && circularViewportRect != null)
        {
            Transform flashTransform = circularViewportRect.Find("Image_ShotFlashOverlay");
            if (flashTransform != null)
                shotFlashOverlay = flashTransform.GetComponent<Image>();
        }

        if (shotFlashOverlay != null)
        {
            Color flashColor = shotFlashOverlay.color;
            flashColor.a = 0f;
            shotFlashOverlay.color = flashColor;
            shotFlashOverlay.gameObject.SetActive(false);
            shotFlashOverlay.raycastTarget = false;
        }

        if (startDiscCalibrationButton != null)
            startDiscCalibrationButton.onClick.AddListener(BeginDiscCalibration);

        if (resetCalibrationButton != null)
            resetCalibrationButton.onClick.AddListener(ResetDiscCalibration);

        if (undoLastButton != null)
            undoLastButton.onClick.AddListener(UndoLastShot);

        if (clearAllButton != null)
            clearAllButton.onClick.AddListener(ClearAllShots);

        if (miniMapButton != null)
            miniMapButton.onClick.AddListener(OpenMiniMap);

        if (endSurgeryButton != null)
            endSurgeryButton.onClick.AddListener(EndSurgery);

        if (fovController != null)
            fovController.DiscCalibrationLineCompleted += HandleDiscCalibrationLineCompleted;
    }

    private void Start()
    {
        EnsureRuntimeTextures();
        RefreshCrosshair();
        RefreshInfoBar(force: true);
        RefreshStatus(null, default);
    }

    private void OnDestroy()
    {
        if (blurRebuildCoroutine != null)
            StopCoroutine(blurRebuildCoroutine);

        if (fovController != null)
            fovController.DiscCalibrationLineCompleted -= HandleDiscCalibrationLineCompleted;

        if (startDiscCalibrationButton != null)
            startDiscCalibrationButton.onClick.RemoveListener(BeginDiscCalibration);

        if (resetCalibrationButton != null)
            resetCalibrationButton.onClick.RemoveListener(ResetDiscCalibration);

        if (undoLastButton != null)
            undoLastButton.onClick.RemoveListener(UndoLastShot);

        if (clearAllButton != null)
            clearAllButton.onClick.RemoveListener(ClearAllShots);

        if (miniMapButton != null)
            miniMapButton.onClick.RemoveListener(OpenMiniMap);

        if (endSurgeryButton != null)
            endSurgeryButton.onClick.RemoveListener(EndSurgery);

        if (workingTexture != null)
            Destroy(workingTexture);

        if (workingBlurTexture != null)
            Destroy(workingBlurTexture);

        if (baseTextureSnapshot != null)
            Destroy(baseTextureSnapshot);
    }

    private void Update()
    {
        EnsureRuntimeTextures();
        HandleAimInput();
        RefreshCrosshair();
        UpdateShotFlash();
        surgeryElapsedSeconds += Time.deltaTime;

        int currentSecond = Mathf.FloorToInt(surgeryElapsedSeconds);
        if (currentSecond != lastInfoBarSecond)
        {
            lastInfoBarSecond = currentSecond;
            RefreshInfoBar();
        }

        if (HasInteractiveUiFocus())
            return;

        LaserShotParameters parameters = ReadParametersFromUI();

        if (parameters.pulseMode == LaserPulseMode.SinglePulse)
        {
            if (Input.GetKeyDown(fireKey))
                Fire(parameters);
        }
        else
        {
            if (Input.GetKey(fireKey))
            {
                repeatTimer += Time.deltaTime;
                if (repeatTimer >= Mathf.Max(0.02f, parameters.intervalSeconds))
                {
                    repeatTimer = 0f;
                    Fire(parameters);
                }
            }
            else
            {
                repeatTimer = Mathf.Max(0f, parameters.intervalSeconds);
            }
        }
    }

    private void EnsureRuntimeTextures()
    {
        if (fundusRawImage == null || fovController == null)
            return;

        Texture2D currentTex = fundusRawImage.texture as Texture2D;
        if (currentTex == null)
            return;

        // 如果当前显示的不是我们的 workingTexture，说明可能刚加载了新图
        if (workingTexture == null || currentTex != workingTexture)
        {
            BindNewWorkingTexture(currentTex);
        }
    }

    private void BindNewWorkingTexture(Texture2D source)
    {
        if (source == null)
            return;

        if (workingTexture != null)
            Destroy(workingTexture);

        if (workingBlurTexture != null)
            Destroy(workingBlurTexture);

        if (baseTextureSnapshot != null)
            Destroy(baseTextureSnapshot);

        Color[] sourcePixels = source.GetPixels();
        baseTexturePixels = (Color[])sourcePixels.Clone();
        baseBlurPixels = CreateBlurredPixels(baseTexturePixels, source.width, source.height, blurRadiusForFocusLayer);
        baseTextureSnapshot = CloneTexture(source, sourcePixels);
        workingTexture = CloneTexture(source, sourcePixels);
        fundusRawImage.texture = workingTexture;
        shotHistory.Clear();
        undoShotHistory.Clear();
        shotCount = 0;
        lastComputedGrade = 0;
        surgeryElapsedSeconds = 0f;
        lastInfoBarSecond = -1;
        repeatTimer = 0f;
        aimOffsetNormalized = Vector2.zero;
        currentSessionId = BuildSessionId();
        RefreshInfoBar(force: true);
        RestoreBaseBlurTexture();
    }

    private void Fire(LaserShotParameters parameters)
    {
        if (physicalModel == null)
            physicalModel = new LaserPhysicalModel();

        if (workingTexture == null || fovController == null || !fovController.IsReady)
            return;

        float pixelToUm = GetEffectivePixelToUm();
        Vector2Int aimPoint = GetCurrentAimPointTopLeft();
        List<Vector2Int> shotPoints = BuildShotPoints(aimPoint, parameters, pixelToUm);
        LaserShotMetrics previewMetrics = physicalModel.Compute(parameters, pixelToUm);
        List<Vector2Int> validShotPoints = new List<Vector2Int>(shotPoints.Count);

        BlurRegion mergedUndoRegion = default;
        for (int i = 0; i < shotPoints.Count; i++)
        {
            Vector2Int pt = shotPoints[i];
            if (pt.x < 0 || pt.y < 0 || pt.x >= workingTexture.width || pt.y >= workingTexture.height)
                continue;

            validShotPoints.Add(pt);
            MergeBlurRegion(ref mergedUndoRegion, BuildRenderRegionForShot(pt, previewMetrics));
        }

        if (validShotPoints.Count <= 0)
            return;

        UndoShotSnapshot actionUndoSnapshot = CaptureUndoSnapshot(mergedUndoRegion, validShotPoints.Count);

        LaserShotMetrics lastMetrics = default;
        BlurRegion mergedBlurRegion = default;

        foreach (Vector2Int pt in validShotPoints)
        {
            lastMetrics = LaserSpotRenderer.RenderShot(
                workingTexture,
                pt,
                parameters,
                physicalModel,
                pixelToUm
            );

            MergeBlurRegion(ref mergedBlurRegion, BuildBlurRegionForShot(pt, lastMetrics));
            shotCount++;
            shotHistory.Add(BuildShotRecord(shotCount, pt, parameters, lastMetrics));
        }

        if (actionUndoSnapshot.IsValid)
        {
            actionUndoSnapshot.blurRegion = mergedBlurRegion;
            undoShotHistory.Add(actionUndoSnapshot);
        }

        TriggerShotFlash();
        lastComputedGrade = lastMetrics.grade;
        QueueBlurRebuild(mergedBlurRegion);
        RefreshInfoBar(force: true);
        RefreshStatus(parameters, lastMetrics);
    }

    private LaserShotParameters ReadParametersFromUI()
    {
        LaserShotParameters p = new LaserShotParameters();

        p.mode = ReadMode();
        p.wavelengthNm = ReadWavelength();
        p.powerMw = Mathf.Clamp(powerMw != null ? powerMw.ReadValue() : 200f, 50f, 800f);
        p.durationMs = Mathf.Clamp(durationMs != null ? durationMs.ReadValue() : 100f, 10f, 500f);
        p.pulseMode = ReadPulseMode();
        p.intervalSeconds = Mathf.Clamp(intervalSeconds != null ? intervalSeconds.ReadValue() : 0.2f, 0.05f, 1.0f);
        p.spotSizeUm = Mathf.Clamp(spotSizeUm != null ? spotSizeUm.ReadValue() : 200f, 50f, 800f);
        p.fundusLens = ReadFundusLens();
        p.aimingBeamLevel = Mathf.Clamp(aimingBeamLevel != null ? aimingBeamLevel.ReadValue() : 50f, 0f, 100f);
        p.titrateMode = titrateModeToggle != null && titrateModeToggle.isOn;

        p.shape = ReadShape();
        p.shapeParam = Mathf.Max(1, Mathf.RoundToInt(shapeParam != null ? shapeParam.ReadValue() : 3f));
        p.spacingXSpot = Mathf.Clamp(spacingXSpot != null ? spacingXSpot.ReadValue() : 1f, 0.25f, 3f);
        p.rotationDeg = rotationDeg != null ? rotationDeg.ReadValue() : 0f;
        p.offsetDx = offsetDx != null ? offsetDx.ReadValue() : 0f;
        p.offsetDy = offsetDy != null ? offsetDy.ReadValue() : 0f;

        return p;
    }

    private LaserMode ReadMode()
    {
        if (modeDropdown == null) return LaserMode.Single;
        return modeDropdown.value == 1 ? LaserMode.Matrix : LaserMode.Single;
    }

    private float ReadWavelength()
    {
        if (wavelengthDropdown == null) return 532f;

        switch (wavelengthDropdown.value)
        {
            case 0: return 532f;
            case 1: return 577f;
            case 2: return 659f;
            default: return 532f;
        }
    }

    private LaserPulseMode ReadPulseMode()
    {
        if (pulseModeDropdown == null) return LaserPulseMode.SinglePulse;
        return pulseModeDropdown.value == 1 ? LaserPulseMode.Repeat : LaserPulseMode.SinglePulse;
    }

    private TreatmentFundusLens ReadFundusLens()
    {
        if (fundusLensDropdown == null) return TreatmentFundusLens.Goldmann;

        switch (fundusLensDropdown.value)
        {
            case 0: return TreatmentFundusLens.Goldmann;
            case 1: return TreatmentFundusLens.Krieger;
            case 2: return TreatmentFundusLens.Panfundoscope;
            case 3: return TreatmentFundusLens.Mainster;
            default: return TreatmentFundusLens.Goldmann;
        }
    }

    private MatrixShape ReadShape()
    {
        if (shapeDropdown == null) return MatrixShape.Square;

        switch (shapeDropdown.value)
        {
            case 0: return MatrixShape.Square;
            case 1: return MatrixShape.Line;
            case 2: return MatrixShape.Triangle;
            case 3: return MatrixShape.Circle;
            case 4: return MatrixShape.QuarterCircle;
            case 5: return MatrixShape.HalfCircle;
            default: return MatrixShape.Square;
        }
    }

    private List<Vector2Int> BuildShotPoints(Vector2Int center, LaserShotParameters p, float pixelToUm)
    {
        List<Vector2Int> result = new List<Vector2Int>();

        if (p.mode == LaserMode.Single)
        {
            result.Add(center);
            return result;
        }

        float spotDiameterPx = p.spotSizeUm / Mathf.Max(pixelToUm, 1e-6f);
        if (physicalModel != null)
        {
            LaserShotMetrics previewMetrics = physicalModel.Compute(p, pixelToUm);
            spotDiameterPx = Mathf.Max(2f, previewMetrics.effectiveRadiusPx * 2f);
        }

        float spacingPx = Mathf.Max(1f, spotDiameterPx * p.spacingXSpot);

        List<Vector2> localPts = BuildLocalMatrixPoints(p.shape, p.shapeParam, spacingPx);

        float rot = p.rotationDeg * Mathf.Deg2Rad;
        float cos = Mathf.Cos(rot);
        float sin = Mathf.Sin(rot);

        for (int i = 0; i < localPts.Count; i++)
        {
            Vector2 pt = localPts[i];
            float rx = pt.x * cos - pt.y * sin;
            float ry = pt.x * sin + pt.y * cos;

            int finalX = Mathf.RoundToInt(center.x + rx + p.offsetDx);
            int finalY = Mathf.RoundToInt(center.y + ry + p.offsetDy);

            result.Add(new Vector2Int(finalX, finalY));
        }

        return result;
    }

    private List<Vector2> BuildLocalMatrixPoints(MatrixShape shape, int shapeParamValue, float spacingPx)
    {
        switch (shape)
        {
            case MatrixShape.Line:
                return BuildLinePoints(shapeParamValue, spacingPx);
            case MatrixShape.Triangle:
                return BuildTrianglePoints(shapeParamValue, spacingPx);
            case MatrixShape.Circle:
                return BuildCirclePoints(shapeParamValue, spacingPx);
            case MatrixShape.QuarterCircle:
                return BuildQuarterCirclePoints(shapeParamValue, spacingPx);
            case MatrixShape.HalfCircle:
                return BuildHalfCirclePoints(shapeParamValue, spacingPx);
            default:
                return BuildSquarePoints(shapeParamValue, spacingPx);
        }
    }

    private List<Vector2> BuildSquarePoints(int shapeParamValue, float spacingPx)
    {
        List<Vector2> localPts = new List<Vector2>();
        int side = GetEffectiveShapeParam(MatrixShape.Square, shapeParamValue);
        float half = (side - 1) / 2f;

        for (int j = 0; j < side; j++)
        {
            for (int i = 0; i < side; i++)
                localPts.Add(new Vector2((i - half) * spacingPx, (j - half) * spacingPx));
        }

        return localPts;
    }

    private List<Vector2> BuildLinePoints(int shapeParamValue, float spacingPx)
    {
        List<Vector2> localPts = new List<Vector2>();
        int count = GetEffectiveShapeParam(MatrixShape.Line, shapeParamValue);
        float half = (count - 1) / 2f;

        for (int i = 0; i < count; i++)
            localPts.Add(new Vector2((i - half) * spacingPx, 0f));

        return localPts;
    }

    private List<Vector2> BuildTrianglePoints(int shapeParamValue, float spacingPx)
    {
        List<Vector2> localPts = new List<Vector2>();
        int rows = GetEffectiveShapeParam(MatrixShape.Triangle, shapeParamValue);

        for (int row = 0; row < rows; row++)
        {
            int cols = row + 1;
            float startX = -0.5f * (cols - 1) * spacingPx;
            float y = (row - (rows - 1) / 2f) * spacingPx;
            for (int col = 0; col < cols; col++)
                localPts.Add(new Vector2(startX + col * spacingPx, y));
        }

        return localPts;
    }

    private List<Vector2> BuildCirclePoints(int shapeParamValue, float spacingPx)
    {
        List<Vector2> localPts = new List<Vector2>();
        int count = GetEffectiveShapeParam(MatrixShape.Circle, shapeParamValue);
        float radius = spacingPx;

        for (int i = 0; i < count; i++)
        {
            float a = Mathf.PI * 2f * i / count;
            localPts.Add(new Vector2(radius * Mathf.Cos(a), radius * Mathf.Sin(a)));
        }

        return localPts;
    }

    private List<Vector2> BuildQuarterCirclePoints(int shapeParamValue, float spacingPx)
    {
        List<Vector2> localPts = new List<Vector2>();
        int count = GetEffectiveShapeParam(MatrixShape.QuarterCircle, shapeParamValue);
        float radius = spacingPx;

        for (int i = 0; i < count; i++)
        {
            float a = (Mathf.PI * 0.5f) * i / Mathf.Max(1, count - 1);
            localPts.Add(new Vector2(radius * Mathf.Cos(a), radius * Mathf.Sin(a)));
        }

        return localPts;
    }

    private List<Vector2> BuildHalfCirclePoints(int shapeParamValue, float spacingPx)
    {
        List<Vector2> localPts = new List<Vector2>();
        int count = GetEffectiveShapeParam(MatrixShape.HalfCircle, shapeParamValue);
        float radius = spacingPx;

        for (int i = 0; i < count; i++)
        {
            float a = Mathf.PI * i / Mathf.Max(1, count - 1);
            localPts.Add(new Vector2(radius * Mathf.Cos(a), radius * Mathf.Sin(a)));
        }

        return localPts;
    }

    private int GetEffectiveShapeParam(LaserShotParameters parameters)
    {
        return GetEffectiveShapeParam(parameters.shape, parameters.shapeParam);
    }

    private int GetEffectiveShapeParam(MatrixShape shape, int rawValue)
    {
        switch (shape)
        {
            case MatrixShape.Square:
                return Mathf.Clamp(rawValue, 2, 5);
            case MatrixShape.Line:
                return Mathf.Clamp(rawValue, 2, 15);
            case MatrixShape.Triangle:
                return Mathf.Clamp(rawValue, 2, 15);
            case MatrixShape.Circle:
                return Mathf.Clamp(rawValue, 4, 24);
            case MatrixShape.QuarterCircle:
            case MatrixShape.HalfCircle:
                return Mathf.Clamp(rawValue, 2, 24);
            default:
                return Mathf.Max(1, rawValue);
        }
    }

    private string GetShapeParamMeaning(MatrixShape shape)
    {
        switch (shape)
        {
            case MatrixShape.Square:
                return "side length";
            case MatrixShape.Line:
                return "spot count";
            case MatrixShape.Triangle:
                return "row count";
            case MatrixShape.Circle:
                return "ring spot count";
            case MatrixShape.QuarterCircle:
                return "arc spot count";
            case MatrixShape.HalfCircle:
                return "arc spot count";
            default:
                return "value";
        }
    }

    private string GetShapeParamRangeText(MatrixShape shape)
    {
        switch (shape)
        {
            case MatrixShape.Square:
                return "2-5";
            case MatrixShape.Line:
            case MatrixShape.Triangle:
                return "2-15";
            case MatrixShape.Circle:
                return "4-24";
            case MatrixShape.QuarterCircle:
            case MatrixShape.HalfCircle:
                return "2-24";
            default:
                return "1+";
        }
    }

    private int GetGeneratedShotCount(LaserShotParameters parameters)
    {
        if (parameters.mode == LaserMode.Single)
            return 1;

        int effectiveParam = GetEffectiveShapeParam(parameters);
        switch (parameters.shape)
        {
            case MatrixShape.Square:
                return effectiveParam * effectiveParam;
            case MatrixShape.Triangle:
                return effectiveParam * (effectiveParam + 1) / 2;
            default:
                return effectiveParam;
        }
    }

    private bool TryParseLaserMode(string value, out LaserMode mode)
    {
        if (!string.IsNullOrWhiteSpace(value) && Enum.TryParse(value, true, out mode))
            return true;

        mode = LaserMode.Single;
        return false;
    }

    private bool TryParseMatrixShape(string value, out MatrixShape shape)
    {
        if (!string.IsNullOrWhiteSpace(value) && Enum.TryParse(value, true, out shape))
            return true;

        shape = MatrixShape.Square;
        return false;
    }

    private void RefreshCrosshair()
    {
        if (crosshairRect == null || circularViewportRect == null)
            return;

        Vector2 viewportDiameter = GetViewportDiameter();
        aimOffsetNormalized = ConvertAnchoredPositionToAimOffset(
            ClampAimAnchoredPositionToLitRegion(GetAimAnchoredPosition()),
            viewportDiameter);

        float aiming = Mathf.Clamp(aimingBeamLevel != null ? aimingBeamLevel.ReadValue() : 50f, 0f, 100f);
        if (crosshairImage != null)
        {
            Color color = crosshairImage.color;
            color.a = Mathf.Lerp(0.15f, 1f, aiming / 100f);
            crosshairImage.color = color;
        }

        crosshairRect.anchoredPosition = GetAimAnchoredPosition();
    }

    private void RefreshInfoBar(bool force = false)
    {
        if (spotsValueText != null)
        {
            string spotsText = shotCount.ToString(CultureInfo.InvariantCulture);
            if (force || !string.Equals(spotsValueText.text, spotsText, StringComparison.Ordinal))
                spotsValueText.text = spotsText;
        }

        if (timerValueText != null)
        {
            string timerText = FormatElapsedTime(surgeryElapsedSeconds);
            if (force || !string.Equals(timerValueText.text, timerText, StringComparison.Ordinal))
                timerValueText.text = timerText;
        }

        if (gradeValueText != null)
        {
            string gradeText = shotCount > 0 ? lastComputedGrade.ToString(CultureInfo.InvariantCulture) : "-";
            if (force || !string.Equals(gradeValueText.text, gradeText, StringComparison.Ordinal))
                gradeValueText.text = gradeText;
        }
    }

    private void TriggerShotFlash()
    {
        if (shotFlashOverlay == null)
            return;

        shotFlashAlpha = Mathf.Clamp01(shotFlashPeakAlpha);
        Color color = shotFlashOverlay.color;
        color.a = shotFlashAlpha;
        shotFlashOverlay.color = color;
        if (!shotFlashOverlay.gameObject.activeSelf)
            shotFlashOverlay.gameObject.SetActive(true);
        shotFlashOverlay.transform.SetAsLastSibling();
        if (crosshairRect != null)
            crosshairRect.SetAsLastSibling();
    }

    private void UpdateShotFlash()
    {
        if (shotFlashOverlay == null)
            return;

        if (shotFlashAlpha <= 0.001f)
        {
            shotFlashAlpha = 0f;
            if (shotFlashOverlay.gameObject.activeSelf)
                shotFlashOverlay.gameObject.SetActive(false);
            return;
        }

        shotFlashAlpha = Mathf.MoveTowards(shotFlashAlpha, 0f, Time.deltaTime * Mathf.Max(0.01f, shotFlashFadeSpeed));
        Color color = shotFlashOverlay.color;
        color.a = shotFlashAlpha;
        shotFlashOverlay.color = color;
    }

    private static string FormatElapsedTime(float elapsedSeconds)
    {
        int totalSeconds = Mathf.Max(0, Mathf.FloorToInt(elapsedSeconds));
        int minutes = totalSeconds / 60;
        int seconds = totalSeconds % 60;
        return $"{minutes:00}:{seconds:00}";
    }

    private float GetEffectivePixelToUm()
    {
        if (fovController == null)
            return defaultPixelToUm;

        return fovController.GetEffectivePixelToUm(defaultPixelToUm);
    }

    private void BeginDiscCalibration()
    {
        if (fovController == null)
            return;

        fovController.BeginDiscCalibration();
        RefreshStatus(null, default);
    }

    private void ResetDiscCalibration()
    {
        if (fovController == null)
            return;

        fovController.ClearDiscCalibration();
        RefreshStatus(null, default);
    }

    private void HandleDiscCalibrationLineCompleted(float discDiameterPx)
    {
        if (fovController == null)
            return;

        float discDiameterUm = ReadOpticDiscDiameterUm();
        bool success = fovController.TrySetDiscCalibration(discDiameterPx, discDiameterUm);

        if (!success)
        {
            if (statusText != null)
                statusText.text = "Calibration failed. Check optic disc μm and drawn distance.";
            return;
        }

        RefreshStatus(null, default);
    }

    private float ReadOpticDiscDiameterUm()
    {
        if (opticDiscUmInput == null || string.IsNullOrWhiteSpace(opticDiscUmInput.text))
            return 1500f;

        if (float.TryParse(opticDiscUmInput.text, NumberStyles.Float, CultureInfo.InvariantCulture, out float inv))
            return inv;

        if (float.TryParse(opticDiscUmInput.text, out float local))
            return local;

        return 1500f;
    }

    private void UndoLastShot()
    {
        if (shotHistory.Count <= 0)
        {
            RefreshInfoBar(force: true);
            RefreshStatus(null, default);
            return;
        }

        if (TryUndoFromSnapshot(out UndoShotSnapshot snapshot))
        {
            int removeCount = Mathf.Clamp(snapshot.shotCountDelta, 1, shotHistory.Count);
            shotHistory.RemoveRange(shotHistory.Count - removeCount, removeCount);
            shotCount = shotHistory.Count;
            lastComputedGrade = shotHistory.Count > 0 ? shotHistory[shotHistory.Count - 1].spot_grade : 0;

            QueueBlurRebuild(snapshot.blurRegion);
            RefreshInfoBar(force: true);

            if (shotHistory.Count > 0)
            {
                ExportShotRecord lastRecord = shotHistory[shotHistory.Count - 1];
                LaserShotParameters statusParams = BuildParametersFromRecord(lastRecord);
                LaserShotMetrics statusMetrics = new LaserShotMetrics { grade = lastRecord.spot_grade };
                RefreshStatus(statusParams, statusMetrics);
            }
            else
            {
                RefreshStatus(null, default);
            }

            return;
        }

        shotHistory.RemoveAt(shotHistory.Count - 1);
        shotCount = shotHistory.Count;
        lastComputedGrade = shotHistory.Count > 0 ? shotHistory[shotHistory.Count - 1].spot_grade : 0;
        RebuildWorkingTextureFromHistory();
        RefreshInfoBar(force: true);
        RefreshStatus(null, default);
    }

    private void ClearAllShots()
    {
        shotHistory.Clear();
        undoShotHistory.Clear();
        shotCount = 0;
        lastComputedGrade = 0;
        RestoreBaseTexture();
        RestoreBaseBlurTexture();
        RefreshInfoBar(force: true);
        RefreshStatus(null, default);
    }

    private void OpenMiniMap()
    {
        if (popupMinimapOverlay != null)
            popupMinimapOverlay.SetActive(true);
    }

    private void EndSurgery()
    {
        if (isExporting)
            return;

        StartCoroutine(ExportAndReloadScene());
    }

    private ExportShotRecord BuildShotRecord(int id, Vector2Int point, LaserShotParameters parameters, LaserShotMetrics metrics)
    {
        return new ExportShotRecord
        {
            id = id,
            pos = new[] { (float)point.x, (float)point.y },
            is_trial = parameters.titrateMode,
            spot_grade = metrics.grade,
            @params = new ExportShotParams
            {
                power = parameters.powerMw,
                spot_size_set = parameters.spotSizeUm,
                exposure_time = parameters.durationMs,
                wavelength = parameters.wavelengthNm,
                mode = parameters.mode.ToString(),
                matrix_shape = parameters.shape.ToString(),
                matrix_shape_param = GetEffectiveShapeParam(parameters),
                matrix_spacing_x_spot = parameters.spacingXSpot,
                matrix_rotation_deg = parameters.rotationDeg,
                matrix_offset_dx = parameters.offsetDx,
                matrix_offset_dy = parameters.offsetDy
            }
        };
    }

    private void RebuildWorkingTextureFromHistory()
    {
        RestoreBaseTexture();
        undoShotHistory.Clear();

        if (workingTexture == null || physicalModel == null)
            return;

        float pixelToUm = GetEffectivePixelToUm();
        LaserShotMetrics lastMetrics = default;
        LaserShotParameters lastParams = default;
        bool hasAny = false;

        foreach (ExportShotRecord record in shotHistory)
        {
            LaserShotParameters parameters = BuildParametersFromRecord(record);
            Vector2Int point = new Vector2Int(
                Mathf.RoundToInt(record.pos[0]),
                Mathf.RoundToInt(record.pos[1]));

            lastMetrics = LaserSpotRenderer.RenderShot(
                workingTexture,
                point,
                parameters,
                physicalModel,
                pixelToUm);

            lastParams = parameters;
            hasAny = true;
        }

        QueueBlurRebuild(forceImmediate: true, fullRebuild: true);

        if (hasAny)
        {
            lastComputedGrade = lastMetrics.grade;
            RefreshStatus(lastParams, lastMetrics);
        }
        else
        {
            lastComputedGrade = 0;
            RefreshStatus(null, default);
        }

        RefreshInfoBar(force: true);
    }

    private LaserShotParameters BuildParametersFromRecord(ExportShotRecord record)
    {
        LaserShotParameters parameters = ReadParametersFromUI();
        if (record == null || record.@params == null)
            return parameters;

        parameters.powerMw = record.@params.power;
        parameters.spotSizeUm = record.@params.spot_size_set;
        parameters.durationMs = record.@params.exposure_time;
        parameters.wavelengthNm = record.@params.wavelength;
        parameters.titrateMode = record.is_trial;

        if (!TryParseLaserMode(record.@params.mode, out parameters.mode))
            parameters.mode = LaserMode.Single;

        if (!TryParseMatrixShape(record.@params.matrix_shape, out parameters.shape))
            parameters.shape = MatrixShape.Square;

        parameters.shapeParam = record.@params.matrix_shape_param > 0
            ? record.@params.matrix_shape_param
            : Mathf.Max(1, parameters.shapeParam);
        parameters.spacingXSpot = record.@params.matrix_spacing_x_spot > 0f
            ? record.@params.matrix_spacing_x_spot
            : parameters.spacingXSpot;
        parameters.rotationDeg = record.@params.matrix_rotation_deg;
        parameters.offsetDx = record.@params.matrix_offset_dx;
        parameters.offsetDy = record.@params.matrix_offset_dy;
        return parameters;
    }

    private void RestoreBaseTexture()
    {
        if (workingTexture == null || baseTexturePixels == null)
            return;

        workingTexture.SetPixels(baseTexturePixels);
        workingTexture.Apply(false, false);
        fundusRawImage.texture = workingTexture;
    }

    private void RestoreBaseBlurTexture()
    {
        if (focusBlurRawImage == null)
            return;

        if (workingTexture == null)
            return;

        EnsureBlurTextureInitialized();
        if (workingBlurTexture == null)
            return;

        if (baseBlurPixels != null && baseBlurPixels.Length == workingTexture.width * workingTexture.height)
        {
            workingBlurTexture.SetPixels(baseBlurPixels);
            workingBlurTexture.Apply(false, false);
            focusBlurRawImage.texture = workingBlurTexture;
            return;
        }

        QueueBlurRebuild(forceImmediate: true, fullRebuild: true);
    }

    private BlurRegion BuildRenderRegionForShot(Vector2Int point, LaserShotMetrics metrics)
    {
        if (workingTexture == null)
            return default;

        int centerX = point.x;
        int centerY = workingTexture.height - 1 - point.y;
        float supportRadius = metrics.effectiveRadiusPx * 1.95f;
        int gridHalf = Mathf.CeilToInt(Mathf.Max(10f, supportRadius + 6f));

        int xMin = Mathf.Max(0, centerX - gridHalf);
        int xMax = Mathf.Min(workingTexture.width - 1, centerX + gridHalf);
        int yMin = Mathf.Max(0, centerY - gridHalf);
        int yMax = Mathf.Min(workingTexture.height - 1, centerY + gridHalf);

        return new BlurRegion
        {
            x = xMin,
            y = yMin,
            width = xMax - xMin + 1,
            height = yMax - yMin + 1
        };
    }

    private UndoShotSnapshot CaptureUndoSnapshot(BlurRegion region, int shotCountDelta)
    {
        UndoShotSnapshot snapshot = default;
        if (workingTexture == null || !region.IsValid)
            return snapshot;

        int xMin = region.x;
        int yMin = region.y;
        int patchW = region.width;
        int patchH = region.height;
        if (patchW <= 0 || patchH <= 0)
            return snapshot;

        snapshot.x = xMin;
        snapshot.y = yMin;
        snapshot.width = patchW;
        snapshot.height = patchH;
        snapshot.shotCountDelta = Mathf.Max(1, shotCountDelta);
        snapshot.previousPixels = workingTexture.GetPixels(xMin, yMin, patchW, patchH);
        return snapshot;
    }

    private bool TryUndoFromSnapshot(out UndoShotSnapshot snapshot)
    {
        snapshot = default;
        if (workingTexture == null || undoShotHistory.Count <= 0)
            return false;

        int lastIndex = undoShotHistory.Count - 1;
        snapshot = undoShotHistory[lastIndex];
        undoShotHistory.RemoveAt(lastIndex);

        if (!snapshot.IsValid)
            return false;

        workingTexture.SetPixels(snapshot.x, snapshot.y, snapshot.width, snapshot.height, snapshot.previousPixels);
        workingTexture.Apply(false, false);
        fundusRawImage.texture = workingTexture;
        return true;
    }

    private void QueueBlurRebuild(BlurRegion dirtyRegion = default, bool forceImmediate = false, bool fullRebuild = false)
    {
        if (focusBlurRawImage == null)
            return;

        if (!forceImmediate && !rebuildBlurAfterEveryShot)
            return;

        if (fullRebuild)
        {
            pendingBlurRegion = default;
        }
        else if (dirtyRegion.IsValid)
        {
            MergeBlurRegion(ref pendingBlurRegion, dirtyRegion);
        }

        blurRebuildQueued = true;

        if (forceImmediate)
        {
            if (blurRebuildCoroutine != null)
            {
                StopCoroutine(blurRebuildCoroutine);
                blurRebuildCoroutine = null;
            }

            RebuildBlurTextureIfNeeded(force: true, fullRebuild: fullRebuild);
            blurRebuildQueued = false;
            pendingBlurRegion = default;
            return;
        }

        if (blurRebuildCoroutine == null)
            blurRebuildCoroutine = StartCoroutine(RebuildBlurNextFrame());
    }

    private IEnumerator RebuildBlurNextFrame()
    {
        yield return null;

        if (blurRebuildQueued)
        {
            BlurRegion dirtyRegion = pendingBlurRegion;
            bool hasDirtyRegion = dirtyRegion.IsValid;
            RebuildBlurTextureIfNeeded(force: true, fullRebuild: !hasDirtyRegion, dirtyRegion: dirtyRegion);
        }

        blurRebuildQueued = false;
        pendingBlurRegion = default;
        blurRebuildCoroutine = null;
    }

    private void RebuildBlurTextureIfNeeded(bool force = false, bool fullRebuild = false, BlurRegion dirtyRegion = default)
    {
        if (focusBlurRawImage == null)
            return;

        if (!force && !rebuildBlurAfterEveryShot)
            return;

        if (workingTexture == null)
            return;

        EnsureBlurTextureInitialized();
        if (workingBlurTexture == null)
            return;

        if (!fullRebuild && dirtyRegion.IsValid)
        {
            UpdateBlurRegion(dirtyRegion);
        }
        else
        {
            Color[] blurred = CreateBlurredPixels(workingTexture.GetPixels(), workingTexture.width, workingTexture.height, blurRadiusForFocusLayer);
            if (blurred == null)
                return;

            workingBlurTexture.SetPixels(blurred);
            workingBlurTexture.Apply(false, false);
        }

        focusBlurRawImage.texture = workingBlurTexture;
    }

    private bool TryBuildExportSnapshot(string sessionId, string pngPath, out ExportSnapshot snapshot, out string message)
    {
        snapshot = default;
        message = string.Empty;

        if (workingTexture == null)
        {
            message = "Export failed: no fundus texture.";
            return false;
        }

        try
        {
            ExportSessionRecord session = new ExportSessionRecord
            {
                session_id = sessionId,
                task_id = defaultTaskId,
                player_info = new ExportPlayerInfo
                {
                    id = defaultPlayerId,
                    name = defaultPlayerName
                },
                shots = new List<ExportShotRecord>(shotHistory)
            };

            snapshot = new ExportSnapshot
            {
                jsonPath = Path.ChangeExtension(pngPath, ".json"),
                pngPath = pngPath,
                json = JsonUtility.ToJson(session, true),
                pngBytes = workingTexture.EncodeToPNG()
            };

            return true;
        }
        catch (Exception ex)
        {
            message = "Export failed: " + ex.Message;
            return false;
        }
    }

    private static bool TryWriteExportSnapshot(ExportSnapshot snapshot, out string message)
    {
        try
        {
            File.WriteAllText(snapshot.jsonPath, snapshot.json);
            File.WriteAllBytes(snapshot.pngPath, snapshot.pngBytes);
            message = $"Exported to {snapshot.pngPath}";
            return true;
        }
        catch (Exception ex)
        {
            message = "Export failed: " + ex.Message;
            return false;
        }
    }

    private IEnumerator ExportAndReloadScene()
    {
        if (workingTexture == null)
        {
            if (statusText != null)
                statusText.text = "Export failed: no fundus texture.";
            yield break;
        }

        isExporting = true;
        if (endSurgeryButton != null)
            endSurgeryButton.interactable = false;
        if (statusText != null)
            statusText.text = "Exporting surgery...";

        string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        string outputDirectory = Path.GetFullPath(Path.Combine(projectRoot, outputRelativeDirectory));
        Directory.CreateDirectory(outputDirectory);

        string sessionId = string.IsNullOrWhiteSpace(currentSessionId) ? BuildSessionId() : currentSessionId;
        string pngPath = Path.Combine(outputDirectory, sessionId + ".png");

        yield return null;

        if (!TryBuildExportSnapshot(sessionId, pngPath, out ExportSnapshot snapshot, out string exportMessage))
        {
            isExporting = false;
            if (endSurgeryButton != null)
                endSurgeryButton.interactable = true;
            if (statusText != null)
                statusText.text = exportMessage;
            yield break;
        }

        if (statusText != null)
            statusText.text = "Exporting surgery... writing files...";

        Task<(bool success, string message)> writeTask = Task.Run(() =>
        {
            bool success = TryWriteExportSnapshot(snapshot, out string message);
            return (success, message);
        });

        while (!writeTask.IsCompleted)
            yield return null;

        if (writeTask.IsFaulted)
        {
            isExporting = false;
            if (endSurgeryButton != null)
                endSurgeryButton.interactable = true;
            if (statusText != null)
                statusText.text = "Export failed: " + (writeTask.Exception?.GetBaseException().Message ?? "unknown error.");
            yield break;
        }

        (bool success, string message) result = writeTask.Result;
        if (!result.success)
        {
            isExporting = false;
            if (endSurgeryButton != null)
                endSurgeryButton.interactable = true;
            if (statusText != null)
                statusText.text = result.message;
            yield break;
        }

        if (statusText != null)
            statusText.text = result.message;

        yield return null;
        SceneManager.LoadScene(SceneManager.GetActiveScene().name);
    }

    private BlurRegion BuildBlurRegionForShot(Vector2Int point, LaserShotMetrics metrics)
    {
        if (workingTexture == null)
            return default;

        int blurPadding = Mathf.Max(blurRadiusForFocusLayer * 2 + 2, 4);
        float visualRadius = metrics.effectiveRadiusPx * Mathf.Lerp(1.55f, 1.95f, Mathf.Clamp01(metrics.appearanceStrength));
        int gridHalf = Mathf.CeilToInt(Mathf.Max(10f, visualRadius)) + blurPadding;

        int centerX = point.x;
        int centerY = workingTexture.height - 1 - point.y;

        int xMin = Mathf.Max(0, centerX - gridHalf);
        int xMax = Mathf.Min(workingTexture.width - 1, centerX + gridHalf);
        int yMin = Mathf.Max(0, centerY - gridHalf);
        int yMax = Mathf.Min(workingTexture.height - 1, centerY + gridHalf);

        return new BlurRegion
        {
            x = xMin,
            y = yMin,
            width = xMax - xMin + 1,
            height = yMax - yMin + 1
        };
    }

    private static void MergeBlurRegion(ref BlurRegion target, BlurRegion incoming)
    {
        if (!incoming.IsValid)
            return;

        if (!target.IsValid)
        {
            target = incoming;
            return;
        }

        int xMin = Mathf.Min(target.x, incoming.x);
        int yMin = Mathf.Min(target.y, incoming.y);
        int xMax = Mathf.Max(target.x + target.width - 1, incoming.x + incoming.width - 1);
        int yMax = Mathf.Max(target.y + target.height - 1, incoming.y + incoming.height - 1);

        target.x = xMin;
        target.y = yMin;
        target.width = xMax - xMin + 1;
        target.height = yMax - yMin + 1;
    }

    private void EnsureBlurTextureInitialized()
    {
        if (workingTexture == null)
            return;

        bool needsNewTexture = workingBlurTexture == null
            || workingBlurTexture.width != workingTexture.width
            || workingBlurTexture.height != workingTexture.height;

        if (!needsNewTexture)
            return;

        if (workingBlurTexture != null)
            Destroy(workingBlurTexture);

        workingBlurTexture = new Texture2D(workingTexture.width, workingTexture.height, TextureFormat.RGBA32, false);
    }

    private void UpdateBlurRegion(BlurRegion region)
    {
        if (!region.IsValid || workingTexture == null || workingBlurTexture == null)
            return;

        int radius = Mathf.Max(0, blurRadiusForFocusLayer);
        int expandedX = Mathf.Max(0, region.x - radius * 2);
        int expandedY = Mathf.Max(0, region.y - radius * 2);
        int expandedMaxX = Mathf.Min(workingTexture.width - 1, region.x + region.width - 1 + radius * 2);
        int expandedMaxY = Mathf.Min(workingTexture.height - 1, region.y + region.height - 1 + radius * 2);
        int expandedWidth = expandedMaxX - expandedX + 1;
        int expandedHeight = expandedMaxY - expandedY + 1;

        Color[] patch = workingTexture.GetPixels(expandedX, expandedY, expandedWidth, expandedHeight);
        Color[] blurredPatch = CreateBlurredPixels(patch, expandedWidth, expandedHeight, radius);
        if (blurredPatch == null)
            return;

        int localX = region.x - expandedX;
        int localY = region.y - expandedY;
        Color[] finalPatch = new Color[region.width * region.height];

        for (int y = 0; y < region.height; y++)
        {
            int srcRow = (localY + y) * expandedWidth + localX;
            int dstRow = y * region.width;
            Array.Copy(blurredPatch, srcRow, finalPatch, dstRow, region.width);
        }

        workingBlurTexture.SetPixels(region.x, region.y, region.width, region.height, finalPatch);
        workingBlurTexture.Apply(false, false);
    }

    private Color[] CreateBlurredPixels(Color[] src, int w, int h, int radius)
    {
        if (src == null || src.Length != w * h)
            return null;

        Color[] a = new Color[src.Length];
        Color[] b = new Color[src.Length];
        Color[] c = new Color[src.Length];

        BoxBlurHorizontal(src, a, w, h, radius);
        BoxBlurVertical(a, b, w, h, radius);
        BoxBlurHorizontal(b, a, w, h, radius);
        BoxBlurVertical(a, c, w, h, radius);
        return c;
    }

    private string BuildSessionId()
    {
        return "SESS_" + DateTime.Now.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture);
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

    private void RefreshStatus(LaserShotParameters? lastParams, LaserShotMetrics lastMetrics)
    {
        if (statusText == null)
            return;

        string calibrationText = "Scale: default";
        if (fovController != null)
        {
            if (fovController.IsCalibrationMode)
            {
                calibrationText = $"Scale: calibration mode ({ReadOpticDiscDiameterUm():F0} um disc)";
            }
            else if (fovController.HasDiscCalibration)
            {
                calibrationText =
                    $"Scale: {fovController.CalibratedPixelToUmOriginal:F3} um/px " +
                    $"({fovController.CalibratedDiscDiameterPxOriginal:F1}px -> {fovController.CalibratedDiscDiameterUm:F0} um)";
            }
        }

        if (shotCount <= 0 || lastParams == null)
        {
            statusText.text = $"Ready. Press Space to fire.\n{calibrationText}";
            return;
        }

        LaserShotParameters p = lastParams.Value;
        string matrixText = string.Empty;
        if (p.mode == LaserMode.Matrix)
        {
            int effectiveShapeParam = GetEffectiveShapeParam(p);
            matrixText =
                $"\nMode: Matrix" +
                $"\nShape: {p.shape}" +
                $"\nshape_param: {p.shapeParam} -> {effectiveShapeParam} ({GetShapeParamMeaning(p.shape)}, range {GetShapeParamRangeText(p.shape)})" +
                $"\nGenerated shots: {GetGeneratedShotCount(p)}" +
                $"\nSpacing: {p.spacingXSpot:F2} x spot" +
                $"\nRotation: {p.rotationDeg:F1} deg" +
                $"\nOffset: ({p.offsetDx:F1}, {p.offsetDy:F1})";
        }
        else
        {
            matrixText = "\nMode: Single";
        }

        statusText.text =
            $"Shots: {shotCount}\n" +
            $"Last Grade: {lastMetrics.grade}\n" +
            $"Z: {lastMetrics.zValue:F2}\n" +
            $"Intensity: {lastMetrics.normalizedIntensity:F2}\n" +
            $"Power: {p.powerMw:F0} mW\n" +
            $"Duration: {p.durationMs:F0} ms\n" +
            $"Spot: {p.spotSizeUm:F0} um\n" +
            $"Wave: {p.wavelengthNm:F0} nm" +
            matrixText +
            $"\n{calibrationText}";
    }

    private Texture2D CloneTexture(Texture2D source, Color[] pixels = null)
    {
        Texture2D tex = new Texture2D(source.width, source.height, TextureFormat.RGBA32, false);
        tex.SetPixels(pixels ?? source.GetPixels());
        tex.Apply(false, false);
        return tex;
    }

    private Vector2Int GetCurrentAimPointTopLeft()
    {
        Vector2 center = fovController != null ? fovController.CurrentCenterPx : Vector2.zero;
        float diameterPx = fovController != null ? fovController.CurrentDiameterPx : 0f;
        Vector2 viewportDiameter = GetViewportDiameter();

        if (diameterPx <= 0.001f || viewportDiameter.x <= 0.001f || viewportDiameter.y <= 0.001f)
        {
            return new Vector2Int(
                Mathf.RoundToInt(center.x),
                Mathf.RoundToInt(center.y));
        }

        float viewportUiDiameter = Mathf.Min(viewportDiameter.x, viewportDiameter.y);
        float uiScale = viewportUiDiameter / diameterPx;
        Vector2 aimAnchoredPosition = GetAimAnchoredPosition();
        Vector2 localOffsetPx = aimAnchoredPosition / uiScale;

        return new Vector2Int(
            Mathf.RoundToInt(center.x + localOffsetPx.x),
            Mathf.RoundToInt(center.y - localOffsetPx.y));
    }

    private void HandleAimInput()
    {
        if (fovController == null || !fovController.IsReady)
            return;

        if (HasInteractiveUiFocus())
            return;

        Vector2 dir = Vector2.zero;

        if (Input.GetKey(KeyCode.UpArrow))
            dir.y += 1f;

        if (Input.GetKey(KeyCode.DownArrow))
            dir.y -= 1f;

        if (Input.GetKey(KeyCode.LeftArrow))
            dir.x -= 1f;

        if (Input.GetKey(KeyCode.RightArrow))
            dir.x += 1f;

        if (dir == Vector2.zero)
            return;

        Vector2 viewportDiameter = GetViewportDiameter();
        float speedMultiplier = (Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift))
            ? fineAimSpeedMultiplier
            : 1f;
        float moveDistance = aimMoveSpeedNormalized * speedMultiplier * Time.deltaTime * Mathf.Min(viewportDiameter.x, viewportDiameter.y);
        Vector2 candidate = GetAimAnchoredPosition() + dir.normalized * moveDistance;
        aimOffsetNormalized = ConvertAnchoredPositionToAimOffset(
            ClampAimAnchoredPositionToLitRegion(candidate),
            viewportDiameter);
    }

    private Vector2 ClampAimAnchoredPositionToLitRegion(Vector2 anchoredPosition)
    {
        Vector2 viewportDiameter = GetViewportDiameter();
        if (viewportDiameter.x <= 0.001f || viewportDiameter.y <= 0.001f)
            return Vector2.zero;

        float viewportRadius = Mathf.Min(viewportDiameter.x, viewportDiameter.y) * 0.5f;
        if (viewportRadius <= 0.001f)
            return Vector2.zero;

        float minX = -viewportRadius;
        float maxX = viewportRadius;
        if (slitLamp != null)
        {
            Vector2 slitBounds = slitLamp.GetReticleBoundsNormalized(reticleFadeZoneFraction);
            minX = Mathf.Max(minX, (slitBounds.x - 0.5f) * viewportDiameter.x);
            maxX = Mathf.Min(maxX, (slitBounds.y - 0.5f) * viewportDiameter.x);
        }

        if (minX > maxX)
        {
            float mid = (minX + maxX) * 0.5f;
            minX = mid;
            maxX = mid;
        }

        Vector2 clamped = anchoredPosition;
        clamped.x = Mathf.Clamp(clamped.x, minX, maxX);

        float radialYLimit = Mathf.Sqrt(Mathf.Max(0f, viewportRadius * viewportRadius - clamped.x * clamped.x));
        clamped.y = Mathf.Clamp(clamped.y, -radialYLimit, radialYLimit);

        return clamped;
    }

    private Vector2 ConvertAnchoredPositionToAimOffset(Vector2 anchoredPosition, Vector2 viewportDiameter)
    {
        if (viewportDiameter.x <= 0.001f || viewportDiameter.y <= 0.001f)
            return Vector2.zero;

        return new Vector2(
            Mathf.Clamp(anchoredPosition.x / viewportDiameter.x, -0.5f, 0.5f),
            Mathf.Clamp(anchoredPosition.y / viewportDiameter.y, -0.5f, 0.5f));
    }

    private Vector2 GetViewportDiameter()
    {
        if (circularViewportRect == null)
            return Vector2.zero;

        return new Vector2(
            circularViewportRect.rect.width,
            circularViewportRect.rect.height);
    }

    private float GetSlitOffsetUiX()
    {
        if (slitLamp == null || circularViewportRect == null)
            return 0f;

        Vector2 slitBounds = slitLamp.GetSlitBoundsNormalized();
        return ((slitBounds.x + slitBounds.y) * 0.5f - 0.5f) * circularViewportRect.rect.width;
    }

    private Vector2 GetAimAnchoredPosition()
    {
        Vector2 viewportDiameter = GetViewportDiameter();
        if (viewportDiameter.x <= 0f || viewportDiameter.y <= 0f)
            return Vector2.zero;

        return ClampAimAnchoredPositionToLitRegion(new Vector2(
            aimOffsetNormalized.x * viewportDiameter.x,
            aimOffsetNormalized.y * viewportDiameter.y));
    }

    private Texture2D CreateBlurredTexture(Texture2D source, int radius)
    {
        if (source == null)
            return null;

        Color[] blurred = CreateBlurredPixels(source.GetPixels(), source.width, source.height, radius);
        if (blurred == null)
            return null;

        Texture2D tex = new Texture2D(source.width, source.height, TextureFormat.RGBA32, false);
        tex.SetPixels(blurred);
        tex.Apply(false, false);
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
}