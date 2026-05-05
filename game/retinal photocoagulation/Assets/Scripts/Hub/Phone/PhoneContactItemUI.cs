using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace RetinalPrototype.Hub.Phone
{
    public sealed class PhoneContactItemUI : MonoBehaviour
    {
        [Header("Required")]
        [SerializeField] private Button button;
        [SerializeField] private Image background;
        [SerializeField] private Image avatarImage;
        [SerializeField] private TMP_Text nameText;
        [SerializeField] private TMP_Text remarkText;
        [SerializeField] private TMP_Text previewText;

        private int _index;
        private System.Action<int> _onClick;

        public void Setup(int index, PhoneTaskData data, System.Action<int> onClick)
        {
            _index = index;
            _onClick = onClick;

            if (avatarImage != null)
            {
                avatarImage.sprite = data != null ? data.avatar : null;
                avatarImage.preserveAspect = true;
            }

            if (nameText != null)
            {
                nameText.text = data != null ? data.displayName : string.Empty;
            }

            if (remarkText != null)
            {
                remarkText.text = data != null ? data.remark : string.Empty;
            }

            if (previewText != null)
            {
                previewText.text = data != null ? data.lastMessagePreview : string.Empty;
            }

            if (button != null)
            {
                button.onClick.RemoveAllListeners();
                button.onClick.AddListener(HandleClick);
            }
        }

        public void SetSelected(bool selected, Sprite normalBg, Sprite selectedBg)
        {
            if (background == null)
            {
                return;
            }

            background.sprite = selected ? selectedBg : normalBg;
        }

        private void HandleClick()
        {
            _onClick?.Invoke(_index);
        }
    }
}
