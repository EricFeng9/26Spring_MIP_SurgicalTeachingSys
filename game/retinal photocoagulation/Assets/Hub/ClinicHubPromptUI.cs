using TMPro;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    public sealed class ClinicHubPromptUI : MonoBehaviour
    {
        [SerializeField] private CanvasGroup rootCanvasGroup;
        [SerializeField] private TextMeshProUGUI promptText;

        private void Awake()
        {
            HideImmediate();
        }

        public void Show(string textValue)
        {
            if (promptText != null)
            {
                promptText.text = string.IsNullOrEmpty(textValue) ? "[E] 交互" : textValue;
            }

            if (rootCanvasGroup == null)
            {
                gameObject.SetActive(true);
                return;
            }

            rootCanvasGroup.alpha = 1f;
            rootCanvasGroup.blocksRaycasts = false;
            rootCanvasGroup.interactable = false;
        }

        public void HideImmediate()
        {
            if (rootCanvasGroup == null)
            {
                gameObject.SetActive(false);
                return;
            }

            rootCanvasGroup.alpha = 0f;
            rootCanvasGroup.blocksRaycasts = false;
            rootCanvasGroup.interactable = false;
        }
    }
}
