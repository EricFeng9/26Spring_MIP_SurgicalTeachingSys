using TMPro;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    [RequireComponent(typeof(TMP_Text))]
    public sealed class RecordTextSlot : MonoBehaviour
    {
        [SerializeField] private TMP_Text targetText;
        [SerializeField] private bool enableAutoSize = true;
        [SerializeField] private float minFontSize = 12f;
        [SerializeField] private float maxFontSize = 28f;
        [SerializeField] private TextOverflowModes overflowMode = TextOverflowModes.Ellipsis;

        private void Reset()
        {
            targetText = GetComponent<TMP_Text>();
        }

        private void Awake()
        {
            if (targetText == null)
            {
                targetText = GetComponent<TMP_Text>();
            }

            ApplyTextSettings();
        }

        public void SetText(string value)
        {
            if (targetText == null)
            {
                return;
            }

            ApplyTextSettings();
            targetText.text = string.IsNullOrWhiteSpace(value) ? "暂无记录" : value;
        }

        public float GetResolvedFontSize()
        {
            if (targetText == null)
            {
                return 0f;
            }

            targetText.ForceMeshUpdate();
            return targetText.fontSize;
        }

        public void SetSharedFontSize(float fontSize)
        {
            if (targetText == null || fontSize <= 0f)
            {
                return;
            }

            targetText.enableAutoSizing = false;
            targetText.fontSize = fontSize;
            targetText.overflowMode = overflowMode;
            targetText.enableWordWrapping = true;
            targetText.ForceMeshUpdate();
        }

        private void ApplyTextSettings()
        {
            if (targetText == null)
            {
                return;
            }

            targetText.enableAutoSizing = enableAutoSize;
            targetText.fontSizeMin = minFontSize;
            targetText.fontSizeMax = maxFontSize;
            targetText.overflowMode = overflowMode;
            targetText.enableWordWrapping = true;
        }
    }
}
