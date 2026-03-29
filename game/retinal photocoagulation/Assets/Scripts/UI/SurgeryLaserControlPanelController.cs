using UnityEngine;
using UnityEngine.UI;

namespace RetinalPrototype
{
    public sealed class SurgeryLaserControlPanelController : MonoBehaviour
    {
        private readonly int[] _wavelengthOptions = { 532, 672 };

        private GameObject _panelRoot;
        private CanvasGroup _panelCanvasGroup;
        private Text _wavelengthText;
        private Text _powerText;
        private Text _durationText;
        private Text _diameterText;
        private bool _isPanelVisible;
        private bool _buttonsAutoWired;

        private int _wavelengthIndex;
        private int _powerMw = 100;
        private int _durationMs = 100;
        private int _diameterUm = 100;

        public delegate void ParametersChangedHandler(int wavelengthNm, int powerMw, int durationMs, int diameterUm);
        public event ParametersChangedHandler ParametersChanged;

        public int PowerMw => _powerMw;
        public int DurationMs => _durationMs;
        public int DiameterUm => _diameterUm;
        public int WavelengthNm => _wavelengthOptions[_wavelengthIndex];

        private void Awake()
        {
            EnsureBindings();
        }

        public void Configure(
            GameObject panelRoot,
            Text wavelengthText,
            Text powerText,
            Text durationText,
            Text diameterText)
        {
            _panelRoot = panelRoot;
            _wavelengthText = wavelengthText;
            _powerText = powerText;
            _durationText = durationText;
            _diameterText = diameterText;

            BindCanvasGroup();
            SetPanelVisible(false);

            RefreshLabels();
        }

        public void TogglePanel()
        {
            EnsureBindings();
            if (_panelCanvasGroup == null)
            {
                return;
            }

            SetPanelVisible(!_isPanelVisible);
        }

        public void ClosePanel()
        {
            EnsureBindings();
            if (_panelCanvasGroup == null)
            {
                return;
            }

            SetPanelVisible(false);
        }

        public void NextWavelength()
        {
            _wavelengthIndex = (_wavelengthIndex + 1) % _wavelengthOptions.Length;
            OnValuesChanged();
        }

        public void PreviousWavelength()
        {
            _wavelengthIndex = (_wavelengthIndex - 1 + _wavelengthOptions.Length) % _wavelengthOptions.Length;
            OnValuesChanged();
        }

        public void IncreasePower()
        {
            _powerMw = Mathf.Clamp(_powerMw + 10, 50, 300);
            OnValuesChanged();
        }

        public void DecreasePower()
        {
            _powerMw = Mathf.Clamp(_powerMw - 10, 50, 300);
            OnValuesChanged();
        }

        public void IncreaseDuration()
        {
            _durationMs = Mathf.Clamp(_durationMs + 5, 10, 200);
            OnValuesChanged();
        }

        public void DecreaseDuration()
        {
            _durationMs = Mathf.Clamp(_durationMs - 5, 10, 200);
            OnValuesChanged();
        }

        public void IncreaseDiameter()
        {
            _diameterUm = Mathf.Clamp(_diameterUm + 10, 50, 300);
            OnValuesChanged();
        }

        public void DecreaseDiameter()
        {
            _diameterUm = Mathf.Clamp(_diameterUm - 10, 50, 300);
            OnValuesChanged();
        }

        private void RefreshLabels()
        {
            if (_wavelengthText != null)
            {
                _wavelengthText.text = _wavelengthOptions[_wavelengthIndex] + " nm";
            }

            if (_powerText != null)
            {
                _powerText.text = $"{_powerMw} mW";
            }

            if (_durationText != null)
            {
                _durationText.text = $"{_durationMs} ms";
            }

            if (_diameterText != null)
            {
                _diameterText.text = $"{_diameterUm} um";
            }
        }

        private void OnValuesChanged()
        {
            RefreshLabels();
            ParametersChanged?.Invoke(WavelengthNm, PowerMw, DurationMs, DiameterUm);
        }

        private void SetPanelVisible(bool visible)
        {
            if (_panelCanvasGroup == null)
            {
                return;
            }

            _isPanelVisible = visible;
            _panelCanvasGroup.alpha = visible ? 1f : 0f;
            _panelCanvasGroup.interactable = visible;
            _panelCanvasGroup.blocksRaycasts = visible;
        }

        private void BindCanvasGroup()
        {
            if (_panelRoot == null)
            {
                return;
            }

            _panelCanvasGroup = _panelRoot.GetComponent<CanvasGroup>();
            if (_panelCanvasGroup == null)
            {
                _panelCanvasGroup = _panelRoot.AddComponent<CanvasGroup>();
            }
        }

        private void EnsureBindings()
        {
            if (_panelRoot == null)
            {
                _panelRoot = gameObject;
            }

            if (_panelCanvasGroup == null)
            {
                BindCanvasGroup();
            }

            if (_wavelengthText == null)
            {
                _wavelengthText = FindValueText("Row_波长 (lambda)");
            }

            if (_powerText == null)
            {
                _powerText = FindValueText("Row_功率 (POWER)");
            }

            if (_durationText == null)
            {
                _durationText = FindValueText("Row_时长 (DURATION)");
            }

            if (_diameterText == null)
            {
                _diameterText = FindValueText("Row_直径 (DIAMETER)");
                if (_diameterText == null)
                {
                    _diameterText = FindValueText("Row_光斑直径");
                }
            }

            if (_wavelengthText == null)
            {
                _wavelengthText = FindValueText("Row_波长");
            }

            if (_powerText == null)
            {
                _powerText = FindValueText("Row_功率");
            }

            if (_durationText == null)
            {
                _durationText = FindValueText("Row_时长");
            }

            AutoWireButtons();

            _isPanelVisible = _panelCanvasGroup != null && _panelCanvasGroup.alpha > 0.5f;
            if (_panelCanvasGroup != null && _panelCanvasGroup.alpha < 0.001f)
            {
                _panelCanvasGroup.interactable = false;
                _panelCanvasGroup.blocksRaycasts = false;
            }

            RefreshLabels();
        }

        private Text FindValueText(string rowName)
        {
            var row = transform.Find("PanelContent/" + rowName + "/Value");
            if (row == null)
            {
                return null;
            }

            return row.GetComponent<Text>();
        }

        private void AutoWireButtons()
        {
            if (_buttonsAutoWired)
            {
                return;
            }

            // Runtime fallback: if persistent UnityEvent wiring is missing,
            // bind row buttons by hierarchy so parameter controls always work.
            WireRowButtons("Row_波长", PreviousWavelength, NextWavelength);
            WireRowButtons("Row_功率", DecreasePower, IncreasePower);
            WireRowButtons("Row_时长", DecreaseDuration, IncreaseDuration);
            WireRowButtons("Row_光斑直径", DecreaseDiameter, IncreaseDiameter);
            _buttonsAutoWired = true;
        }

        private void WireRowButtons(string rowName, UnityEngine.Events.UnityAction leftAction, UnityEngine.Events.UnityAction rightAction)
        {
            var row = transform.Find("PanelContent/" + rowName);
            if (row == null)
            {
                return;
            }

            var buttons = row.GetComponentsInChildren<Button>(true);
            if (buttons.Length < 2)
            {
                return;
            }

            var left = buttons[0];
            var right = buttons[buttons.Length - 1];

            left.onClick.RemoveListener(leftAction);
            left.onClick.AddListener(leftAction);

            right.onClick.RemoveListener(rightAction);
            right.onClick.AddListener(rightAction);
        }
    }
}
