using System;
using System.IO;
using RetinalPrototype.Hub;
using UnityEngine;
using UnityEngine.UI;

namespace RetinalPrototype
{
    public sealed class SurgeryLaserSpotRenderer : MonoBehaviour
    {
        private const float OpticDiscDiameterMm = 1.5f;
        private const float UmPerMm = 1000f;
        private const float OpticDiscDiameterUm = OpticDiscDiameterMm * UmPerMm;
        private const float AreaDilutionExponent = 0.8f;
        private const float DefaultSlitWidthNormalized = 0.10f;
        private const float MinSlitWidthNormalized = 0.06f;
        private const float MaxSlitWidthNormalized = 0.16f;
        private const float SlitMaskOpacity = 0.92f;

        [SerializeField] private RawImage fundusImage;
        [SerializeField] private SurgeryFundusInteractionOverlay fundusOverlay;
        [SerializeField] private SurgeryLaserControlPanelController controlPanel;
        [SerializeField] private Text statusText;
        [SerializeField] private float pixelToUm = 2.0f;

        private Texture2D _baseTexture;
        private Texture2D _workingTexture;
        private RectTransform _fundusRect;
        private string _statusMessage = "准备就绪";
        private bool _isCalibrationMode;
        private float _defaultPixelToUm;
        private string _currentImageSourceTag;
        private bool _slitLensEnabled;
        private bool _flashEnabled = true;
        private bool _aimDotEnabled = true;
        private float _slitCenterNormalized = 0.5f;
        private float _slitWidthNormalized = DefaultSlitWidthNormalized;
        private float _flashIntensity;
        private Vector2 _aimLocalPoint;

        private Image _slitMaskLeft;
        private Image _slitMaskRight;
        private Image _flashOverlay;
        private Image _aimDot;

        private readonly string[] _candidateRelativePaths =
        {
            "fundus.jpg",
            "fundus.png",
            "Retina/fundus.jpg",
            "Retina/fundus.png"
        };

        private void Start()
        {
            GameFlowSession.Instance.BeginSurgerySession();
            _defaultPixelToUm = pixelToUm;
            EnsureReferences();

            if (controlPanel != null)
            {
                controlPanel.ParametersChanged += OnParametersChanged;
            }

            if (fundusOverlay != null)
            {
                fundusOverlay.FireClicked += OnFundusClicked;
                fundusOverlay.CalibrationLineFinished += OnCalibrationLineFinished;
                fundusOverlay.PointerMoved += OnPointerMoved;
            }

            LoadOrCreateFundusImage();
        }

        private void Update()
        {
            if (_flashOverlay == null)
            {
                return;
            }

            if (_flashIntensity <= 0.001f)
            {
                _flashOverlay.gameObject.SetActive(false);
                return;
            }

            _flashIntensity = Mathf.MoveTowards(_flashIntensity, 0f, Time.unscaledDeltaTime * 6f);
            var c = _flashOverlay.color;
            c.a = _flashIntensity;
            _flashOverlay.color = c;
        }

        private void OnDestroy()
        {
            if (controlPanel != null)
            {
                controlPanel.ParametersChanged -= OnParametersChanged;
            }

            if (fundusOverlay != null)
            {
                fundusOverlay.FireClicked -= OnFundusClicked;
                fundusOverlay.CalibrationLineFinished -= OnCalibrationLineFinished;
                fundusOverlay.PointerMoved -= OnPointerMoved;
            }
        }

        public void ToggleSlitLens()
        {
            _slitLensEnabled = !_slitLensEnabled;
            UpdateLensVisuals();
            SetStatus(_slitLensEnabled ? "裂隙镜：开启" : "裂隙镜：关闭");
        }

        public void MoveSlitLensLeft()
        {
            var halfWidth = Mathf.Clamp(_slitWidthNormalized, MinSlitWidthNormalized, MaxSlitWidthNormalized) * 0.5f;
            _slitCenterNormalized = Mathf.Clamp(_slitCenterNormalized - 0.05f, halfWidth, 1f - halfWidth);
            UpdateLensVisuals();
            SetStatus($"裂隙镜位置：{_slitCenterNormalized:F2}");
        }

        public void MoveSlitLensRight()
        {
            var halfWidth = Mathf.Clamp(_slitWidthNormalized, MinSlitWidthNormalized, MaxSlitWidthNormalized) * 0.5f;
            _slitCenterNormalized = Mathf.Clamp(_slitCenterNormalized + 0.05f, halfWidth, 1f - halfWidth);
            UpdateLensVisuals();
            SetStatus($"裂隙镜位置：{_slitCenterNormalized:F2}");
        }

        public void ToggleFlashEffect()
        {
            _flashEnabled = !_flashEnabled;
            if (!_flashEnabled && _flashOverlay != null)
            {
                _flashIntensity = 0f;
                _flashOverlay.gameObject.SetActive(false);
            }

            SetStatus(_flashEnabled ? "击发闪光：开启" : "击发闪光：关闭");
        }

        public void ToggleAimDot()
        {
            _aimDotEnabled = !_aimDotEnabled;
            UpdateAimDotVisual();
            SetStatus(_aimDotEnabled ? "红点瞄准：开启" : "红点瞄准：关闭");
        }

        public void ReloadFundusImage()
        {
            LoadOrCreateFundusImage();
        }

        public void ResetRenderedSpots()
        {
            if (_baseTexture == null || _workingTexture == null)
            {
                return;
            }

            _workingTexture.SetPixels(_baseTexture.GetPixels());
            _workingTexture.Apply(false);
            SetStatus("图像已重置，可继续击发");
        }

        public void BeginOpticDiscCalibration()
        {
            _isCalibrationMode = true;
            if (fundusOverlay != null)
            {
                fundusOverlay.SetCalibrationMode(true);
            }

            SetStatus($"标定模式：在视盘上拖拽一条直径线（标准 {OpticDiscDiameterMm:F1}mm / {OpticDiscDiameterUm:F0}um）");
        }

        private void EnsureReferences()
        {
            if (fundusImage == null)
            {
                var go = GameObject.Find("FundusImage");
                if (go != null)
                {
                    fundusImage = go.GetComponent<RawImage>();
                }
            }

            if (fundusImage == null)
            {
                CreateRuntimeViewport();
            }

            if (controlPanel == null)
            {
                controlPanel = FindFirstObjectByType<SurgeryLaserControlPanelController>();
            }

            if (statusText == null)
            {
                var go = GameObject.Find("LaserStatusText");
                if (go != null)
                {
                    statusText = go.GetComponent<Text>();
                }
            }

            EnsureStatusBarLayout();

            if (fundusImage != null)
            {
                _fundusRect = fundusImage.rectTransform;

                if (fundusOverlay == null)
                {
                    fundusOverlay = fundusImage.GetComponent<SurgeryFundusInteractionOverlay>();
                    if (fundusOverlay == null)
                    {
                        fundusOverlay = fundusImage.gameObject.AddComponent<SurgeryFundusInteractionOverlay>();
                    }
                }

                EnsureOpticVisualOverlays();
            }

            SetStatus(_statusMessage);
        }

        private void EnsureStatusBarLayout()
        {
            var canvas = FindFirstObjectByType<Canvas>();
            if (canvas == null)
            {
                return;
            }

            if (statusText == null)
            {
                var bar = new GameObject("StatusBar", typeof(RectTransform), typeof(Image));
                bar.transform.SetParent(canvas.transform, false);
                var barRect = bar.GetComponent<RectTransform>();
                barRect.anchorMin = new Vector2(0.5f, 0f);
                barRect.anchorMax = new Vector2(0.5f, 0f);
                barRect.pivot = new Vector2(0.5f, 0f);
                barRect.sizeDelta = new Vector2(1760f, 60f);
                barRect.anchoredPosition = new Vector2(0f, 72f);
                bar.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.92f);

                var textObj = new GameObject("LaserStatusText", typeof(RectTransform), typeof(Text));
                textObj.transform.SetParent(bar.transform, false);
                var textRect = textObj.GetComponent<RectTransform>();
                textRect.anchorMin = new Vector2(0.5f, 0.5f);
                textRect.anchorMax = new Vector2(0.5f, 0.5f);
                textRect.pivot = new Vector2(0.5f, 0.5f);
                textRect.sizeDelta = new Vector2(1680f, 52f);
                textRect.anchoredPosition = Vector2.zero;

                statusText = textObj.GetComponent<Text>();
                statusText.font = GetBuiltinFont();
                statusText.fontSize = 22;
                statusText.alignment = TextAnchor.MiddleCenter;
                statusText.color = new Color(0.18f, 0.22f, 0.24f, 0.92f);
                statusText.raycastTarget = false;
                return;
            }

            var statusRt = statusText.rectTransform;
            if (statusRt == null)
            {
                return;
            }

            var parentName = statusRt.parent != null ? statusRt.parent.name : string.Empty;
            if (parentName == "FundusViewport")
            {
                var bar = new GameObject("StatusBar", typeof(RectTransform), typeof(Image));
                bar.transform.SetParent(canvas.transform, false);
                var barRect = bar.GetComponent<RectTransform>();
                barRect.anchorMin = new Vector2(0.5f, 0f);
                barRect.anchorMax = new Vector2(0.5f, 0f);
                barRect.pivot = new Vector2(0.5f, 0f);
                barRect.sizeDelta = new Vector2(1760f, 60f);
                barRect.anchoredPosition = new Vector2(0f, 72f);
                bar.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.92f);

                statusRt.SetParent(bar.transform, false);
                statusRt.anchorMin = new Vector2(0.5f, 0.5f);
                statusRt.anchorMax = new Vector2(0.5f, 0.5f);
                statusRt.pivot = new Vector2(0.5f, 0.5f);
                statusRt.sizeDelta = new Vector2(1680f, 52f);
                statusRt.anchoredPosition = Vector2.zero;
                statusText.alignment = TextAnchor.MiddleCenter;
            }
        }

        private void CreateRuntimeViewport()
        {
            var canvas = FindFirstObjectByType<Canvas>();
            if (canvas == null)
            {
                return;
            }

            var viewport = new GameObject("FundusViewport", typeof(RectTransform), typeof(Image));
            viewport.transform.SetParent(canvas.transform, false);

            var viewportRect = viewport.GetComponent<RectTransform>();
            viewportRect.anchorMin = new Vector2(0.5f, 0.5f);
            viewportRect.anchorMax = new Vector2(0.5f, 0.5f);
            viewportRect.pivot = new Vector2(0.5f, 0.5f);
            viewportRect.sizeDelta = new Vector2(700f, 700f);
            viewportRect.anchoredPosition = new Vector2(220f, -20f);

            var viewportImage = viewport.GetComponent<Image>();
            viewportImage.color = new Color(0.08f, 0.14f, 0.22f, 0.93f);

            var imageObj = new GameObject("FundusImage", typeof(RectTransform), typeof(RawImage), typeof(AspectRatioFitter));
            imageObj.transform.SetParent(viewport.transform, false);
            var imageRect = imageObj.GetComponent<RectTransform>();
            imageRect.anchorMin = new Vector2(0.5f, 0.5f);
            imageRect.anchorMax = new Vector2(0.5f, 0.5f);
            imageRect.pivot = new Vector2(0.5f, 0.5f);
            imageRect.sizeDelta = new Vector2(620f, 620f);
            imageRect.anchoredPosition = new Vector2(0f, 12f);

            fundusImage = imageObj.GetComponent<RawImage>();
            var fitter = imageObj.GetComponent<AspectRatioFitter>();
            fitter.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
            fitter.aspectRatio = 1f;

            var statusObj = new GameObject("LaserStatusText", typeof(RectTransform), typeof(Text));
            statusObj.transform.SetParent(canvas.transform, false);
            var statusRect = statusObj.GetComponent<RectTransform>();
            statusRect.anchorMin = new Vector2(0.5f, 0f);
            statusRect.anchorMax = new Vector2(0.5f, 0f);
            statusRect.pivot = new Vector2(0.5f, 0f);
            statusRect.sizeDelta = new Vector2(1680f, 52f);
            statusRect.anchoredPosition = new Vector2(0f, 76f);

            statusText = statusObj.GetComponent<Text>();
            statusText.font = GetBuiltinFont();
            statusText.fontSize = 20;
            statusText.alignment = TextAnchor.MiddleCenter;
            statusText.color = new Color(0.74f, 0.96f, 0.84f, 1f);
            statusText.raycastTarget = false;
            statusText.text = "准备就绪";
        }

        private void LoadOrCreateFundusImage()
        {
            EnsureReferences();
            if (fundusImage == null)
            {
                return;
            }

            Texture2D loaded = null;
            var loadedSourceTag = string.Empty;
            foreach (var relativePath in _candidateRelativePaths)
            {
                var fullPath = Path.Combine(Application.streamingAssetsPath, relativePath);
                if (!File.Exists(fullPath))
                {
                    continue;
                }

                try
                {
                    var bytes = File.ReadAllBytes(fullPath);
                    var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                    if (tex.LoadImage(bytes, false))
                    {
                        loaded = tex;
                        var ticks = File.GetLastWriteTimeUtc(fullPath).Ticks;
                        loadedSourceTag = fullPath + "|" + bytes.Length + "|" + ticks;
                        SetStatus("已加载图像: " + relativePath);

                        break;
                    }
                }
                catch (Exception)
                {
                    // Ignore and continue fallback.
                }
            }

            if (loaded == null)
            {
                loaded = CreateFallbackFundusTexture(1024, 1024);
                loadedSourceTag = "fallback|1024|1024";
                SetStatus("未找到外部图像，已使用内置眼底占位图");
            }

            if (!string.Equals(_currentImageSourceTag, loadedSourceTag, StringComparison.Ordinal))
            {
                _currentImageSourceTag = loadedSourceTag;
                pixelToUm = _defaultPixelToUm;
            }

            _baseTexture = loaded;
            _workingTexture = new Texture2D(_baseTexture.width, _baseTexture.height, TextureFormat.RGBA32, false);
            _workingTexture.SetPixels(_baseTexture.GetPixels());
            _workingTexture.Apply(false);

            fundusImage.texture = _workingTexture;
            ApplyStatusText();
        }

        private void UpdateScaleLabel()
        {
            ApplyStatusText();
        }

        private void OnFundusClicked(Vector2 localPoint)
        {
            if (_isCalibrationMode || _fundusRect == null || _workingTexture == null)
            {
                return;
            }

            if (!TryLocalPointToTexturePixel(localPoint, out var px, out var py))
            {
                return;
            }

            var power = controlPanel != null ? controlPanel.PowerMw : 150;
            var durationMs = controlPanel != null ? controlPanel.DurationMs : 15;
            var spotSizeUm = controlPanel != null ? controlPanel.DiameterUm : 200;
            var wavelength = controlPanel != null ? controlPanel.WavelengthNm : 577;

            RenderLaserSpot(_workingTexture, px, py, power, durationMs / 1000f, spotSizeUm, wavelength, pixelToUm);
            _workingTexture.Apply(false);
            GameFlowSession.Instance.RecordShot(
                new Vector2(px, py),
                false,
                0,
                power,
                spotSizeUm,
                durationMs,
                wavelength
            );

            TriggerShotFlash();

            SetStatus($"已击发 ({px}, {py}) | {power}mW / {durationMs}ms / {spotSizeUm}um / {wavelength}nm");
        }

        private void OnPointerMoved(Vector2 localPoint)
        {
            _aimLocalPoint = localPoint;
            UpdateAimDotVisual();
        }

        private void EnsureOpticVisualOverlays()
        {
            if (fundusImage == null)
            {
                return;
            }

            var root = fundusImage.rectTransform;
            _slitMaskLeft ??= CreateOverlayImage(root, "SlitMaskLeft", new Color(0f, 0f, 0f, SlitMaskOpacity));
            _slitMaskRight ??= CreateOverlayImage(root, "SlitMaskRight", new Color(0f, 0f, 0f, SlitMaskOpacity));
            _flashOverlay ??= CreateOverlayImage(root, "ShotFlash", new Color(1f, 0.72f, 0.22f, 0f));
            _aimDot ??= CreateOverlayImage(root, "AimDot", new Color(0.96f, 0.15f, 0.15f, 0.98f));

            var dotRt = _aimDot.rectTransform;
            dotRt.anchorMin = new Vector2(0.5f, 0.5f);
            dotRt.anchorMax = new Vector2(0.5f, 0.5f);
            dotRt.pivot = new Vector2(0.5f, 0.5f);
            dotRt.sizeDelta = new Vector2(12f, 12f);

            _flashOverlay.raycastTarget = false;
            _slitMaskLeft.raycastTarget = false;
            _slitMaskRight.raycastTarget = false;
            _aimDot.raycastTarget = false;

            _flashOverlay.transform.SetAsLastSibling();
            _aimDot.transform.SetAsLastSibling();

            UpdateLensVisuals();
            UpdateAimDotVisual();
        }

        private Image CreateOverlayImage(RectTransform parent, string name, Color color)
        {
            var obj = new GameObject(name, typeof(RectTransform), typeof(Image));
            obj.transform.SetParent(parent, false);
            var rt = obj.GetComponent<RectTransform>();
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;
            var image = obj.GetComponent<Image>();
            image.color = color;
            return image;
        }

        private void UpdateLensVisuals()
        {
            if (_slitMaskLeft == null || _slitMaskRight == null)
            {
                return;
            }

            _slitMaskLeft.gameObject.SetActive(_slitLensEnabled);
            _slitMaskRight.gameObject.SetActive(_slitLensEnabled);
            if (!_slitLensEnabled)
            {
                return;
            }

            _slitWidthNormalized = Mathf.Clamp(_slitWidthNormalized, MinSlitWidthNormalized, MaxSlitWidthNormalized);
            var halfWidth = _slitWidthNormalized * 0.5f;
            _slitCenterNormalized = Mathf.Clamp(_slitCenterNormalized, halfWidth, 1f - halfWidth);

            var leftEdge = Mathf.Clamp01(_slitCenterNormalized - _slitWidthNormalized * 0.5f);
            var rightEdge = Mathf.Clamp01(_slitCenterNormalized + _slitWidthNormalized * 0.5f);

            var l = _slitMaskLeft.rectTransform;
            l.anchorMin = new Vector2(0f, 0f);
            l.anchorMax = new Vector2(leftEdge, 1f);
            l.offsetMin = Vector2.zero;
            l.offsetMax = Vector2.zero;

            var r = _slitMaskRight.rectTransform;
            r.anchorMin = new Vector2(rightEdge, 0f);
            r.anchorMax = new Vector2(1f, 1f);
            r.offsetMin = Vector2.zero;
            r.offsetMax = Vector2.zero;
        }

        private void TriggerShotFlash()
        {
            if (!_flashEnabled || _flashOverlay == null)
            {
                return;
            }

            _flashIntensity = 0.88f;
            _flashOverlay.gameObject.SetActive(true);
            var c = _flashOverlay.color;
            c.a = _flashIntensity;
            _flashOverlay.color = c;
            _flashOverlay.transform.SetAsLastSibling();
            if (_aimDot != null)
            {
                _aimDot.transform.SetAsLastSibling();
            }
        }

        private void UpdateAimDotVisual()
        {
            if (_aimDot == null || _fundusRect == null)
            {
                return;
            }

            _aimDot.gameObject.SetActive(_aimDotEnabled);
            if (!_aimDotEnabled)
            {
                return;
            }

            var rect = _fundusRect.rect;
            var clamped = new Vector2(
                Mathf.Clamp(_aimLocalPoint.x, rect.xMin, rect.xMax),
                Mathf.Clamp(_aimLocalPoint.y, rect.yMin, rect.yMax));

            _aimDot.rectTransform.anchoredPosition = clamped;
        }

        private void OnCalibrationLineFinished(Vector2 localStart, Vector2 localEnd)
        {
            _isCalibrationMode = false;

            if (!TryClippedCalibrationLineToTexture(localStart, localEnd, out var startX, out var startY, out var endX, out var endY))
            {
                SetStatus("标定失败：线段不在图像范围内");
                return;
            }

            var dx = endX - startX;
            var dy = endY - startY;
            var pixelDistance = Mathf.Sqrt(dx * dx + dy * dy);
            if (pixelDistance < 1f)
            {
                SetStatus("标定失败：线段太短");
                return;
            }

            // Unit conversion is explicit: 1.5 mm -> 1500 um.
            pixelToUm = OpticDiscDiameterUm / pixelDistance;
            SetStatus($"标定成功 | 视盘直径={OpticDiscDiameterMm:F1}mm({OpticDiscDiameterUm:F0}um) | 量测像素={pixelDistance:F1}px");
        }

        private bool TryClippedCalibrationLineToTexture(
            Vector2 localStart,
            Vector2 localEnd,
            out float startX,
            out float startY,
            out float endX,
            out float endY)
        {
            startX = 0f;
            startY = 0f;
            endX = 0f;
            endY = 0f;

            if (_fundusRect == null || _workingTexture == null)
            {
                return false;
            }

            var rect = _fundusRect.rect;
            var x0 = localStart.x;
            var y0 = localStart.y;
            var x1 = localEnd.x;
            var y1 = localEnd.y;

            if (!ClipLineToRect(rect.xMin, rect.yMin, rect.xMax, rect.yMax, ref x0, ref y0, ref x1, ref y1))
            {
                return false;
            }

            var u0 = Mathf.InverseLerp(rect.xMin, rect.xMax, x0);
            var v0 = Mathf.InverseLerp(rect.yMin, rect.yMax, y0);
            var u1 = Mathf.InverseLerp(rect.xMin, rect.xMax, x1);
            var v1 = Mathf.InverseLerp(rect.yMin, rect.yMax, y1);

            startX = u0 * (_workingTexture.width - 1);
            startY = v0 * (_workingTexture.height - 1);
            endX = u1 * (_workingTexture.width - 1);
            endY = v1 * (_workingTexture.height - 1);
            return true;
        }

        private static bool ClipLineToRect(
            float xmin,
            float ymin,
            float xmax,
            float ymax,
            ref float x0,
            ref float y0,
            ref float x1,
            ref float y1)
        {
            var dx = x1 - x0;
            var dy = y1 - y0;
            var t0 = 0f;
            var t1 = 1f;

            if (!ClipTest(-dx, x0 - xmin, ref t0, ref t1)) return false;
            if (!ClipTest(dx, xmax - x0, ref t0, ref t1)) return false;
            if (!ClipTest(-dy, y0 - ymin, ref t0, ref t1)) return false;
            if (!ClipTest(dy, ymax - y0, ref t0, ref t1)) return false;

            if (t1 < 1f)
            {
                x1 = x0 + t1 * dx;
                y1 = y0 + t1 * dy;
            }

            if (t0 > 0f)
            {
                x0 = x0 + t0 * dx;
                y0 = y0 + t0 * dy;
            }

            return true;
        }

        private static bool ClipTest(float p, float q, ref float t0, ref float t1)
        {
            if (Mathf.Approximately(p, 0f))
            {
                return q >= 0f;
            }

            var r = q / p;
            if (p < 0f)
            {
                if (r > t1) return false;
                if (r > t0) t0 = r;
            }
            else
            {
                if (r < t0) return false;
                if (r < t1) t1 = r;
            }

            return true;
        }

        private bool TryLocalPointToTexturePixel(Vector2 localPoint, out int px, out int py)
        {
            px = 0;
            py = 0;

            if (_fundusRect == null || _workingTexture == null)
            {
                return false;
            }

            var rect = _fundusRect.rect;
            if (!rect.Contains(localPoint))
            {
                return false;
            }

            var u = Mathf.InverseLerp(rect.xMin, rect.xMax, localPoint.x);
            var v = Mathf.InverseLerp(rect.yMin, rect.yMax, localPoint.y);

            px = Mathf.Clamp(Mathf.RoundToInt(u * (_workingTexture.width - 1)), 0, _workingTexture.width - 1);
            py = Mathf.Clamp(Mathf.RoundToInt(v * (_workingTexture.height - 1)), 0, _workingTexture.height - 1);
            return true;
        }

        private void SetStatus(string message)
        {
            _statusMessage = string.IsNullOrEmpty(message) ? "准备就绪" : message;
            ApplyStatusText();
        }

        private void ApplyStatusText()
        {
            if (statusText == null)
            {
                return;
            }

            var mmPerPx = pixelToUm / 1000f;
            var pxPerMm = 1000f / Mathf.Max(0.0001f, pixelToUm);
            var spotUm = controlPanel != null ? controlPanel.DiameterUm : 100;
            var spotDiameterPx = spotUm / Mathf.Max(0.0001f, pixelToUm);

            statusText.text = _statusMessage
                + $" | 1px={pixelToUm:F2}um ({mmPerPx:F4}mm)"
                + $" | 1mm={pxPerMm:F1}px"
                + $" | 当前光斑约={spotDiameterPx:F1}px";
        }

        private static Texture2D CreateFallbackFundusTexture(int width, int height)
        {
            var tex = new Texture2D(width, height, TextureFormat.RGBA32, false);
            var cx = width * 0.5f;
            var cy = height * 0.5f;
            var radius = Mathf.Min(width, height) * 0.47f;

            var pixels = new Color[width * height];
            for (var y = 0; y < height; y++)
            {
                for (var x = 0; x < width; x++)
                {
                    var dx = x - cx;
                    var dy = y - cy;
                    var dist = Mathf.Sqrt(dx * dx + dy * dy);
                    var t = Mathf.Clamp01(dist / radius);

                    var inside = dist <= radius;
                    var baseColor = Color.Lerp(new Color(0.90f, 0.46f, 0.20f, 1f), new Color(0.65f, 0.21f, 0.12f, 1f), t);
                    pixels[y * width + x] = inside ? baseColor : new Color(0.08f, 0.09f, 0.12f, 1f);
                }
            }

            tex.SetPixels(pixels);
            tex.Apply(false);
            return tex;
        }

        private static Font GetBuiltinFont()
        {
            var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (font != null)
            {
                return font;
            }

            return Resources.GetBuiltinResource<Font>("Arial.ttf");
        }

        private static void RenderLaserSpot(
            Texture2D texture,
            int centerX,
            int centerY,
            float powerMw,
            float durationS,
            float spotSizeUm,
            int wavelengthNm,
            float pixelToUm)
        {
            var radiusUm = spotSizeUm / 2f;
            var radiusPx = Mathf.Max(1, Mathf.FloorToInt(radiusUm / Mathf.Max(0.0001f, pixelToUm)));

            var isGreen = wavelengthNm <= 577;
            var scatterMultiplier = isGreen ? 1.3f : 0.9f;
            var absorptionEfficiency = isGreen ? 1.0f : 0.7f;

            var effectiveRadiusPx = radiusPx * scatterMultiplier;
            var area = Mathf.PI * radiusUm * radiusUm;
            if (Mathf.Approximately(area, 0f))
            {
                return;
            }

            // Reduced dilution: area exponent < 1 weakens intensity drop for larger spots.
            var effectiveArea = Mathf.Pow(area, AreaDilutionExponent);
            var energyDensity = (powerMw * durationS) / Mathf.Max(0.0001f, effectiveArea);
            var damageIndex = energyDensity * absorptionEfficiency * 400f;

            var gridHalf = Mathf.FloorToInt(effectiveRadiusPx * 3f);
            var xMin = Mathf.Max(0, centerX - gridHalf);
            var xMax = Mathf.Min(texture.width, centerX + gridHalf);
            var yMin = Mathf.Max(0, centerY - gridHalf);
            var yMax = Mathf.Min(texture.height, centerY + gridHalf);

            if (xMin >= xMax || yMin >= yMax)
            {
                return;
            }

            var sigmaSq = effectiveRadiusPx > 0f
                ? (effectiveRadiusPx / 2f) * (effectiveRadiusPx / 2f)
                : 1f;
            var burnColor = new Color(230f / 255f, 230f / 255f, 230f / 255f, 1f);

            for (var y = yMin; y < yMax; y++)
            {
                for (var x = xMin; x < xMax; x++)
                {
                    var dx = x - centerX;
                    var dy = y - centerY;
                    var distSq = dx * dx + dy * dy;

                    var localDamage = Mathf.Exp(-distSq / (2f * sigmaSq)) * damageIndex;
                    var alpha = Mathf.Pow(Mathf.Clamp01(localDamage), 1.2f);
                    if (alpha <= 0.0001f)
                    {
                        continue;
                    }

                    var src = texture.GetPixel(x, y);
                    var blended = Color.Lerp(src, burnColor, alpha);
                    texture.SetPixel(x, y, blended);
                }
            }
        }

        private void OnParametersChanged(int wavelengthNm, int powerMw, int durationMs, int diameterUm)
        {
            SetStatus($"参数更新 | {powerMw}mW / {durationMs}ms / {diameterUm}um / {wavelengthNm}nm");
        }
    }
}

