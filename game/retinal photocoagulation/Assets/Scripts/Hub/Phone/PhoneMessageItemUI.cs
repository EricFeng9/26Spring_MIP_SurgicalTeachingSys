using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace RetinalPrototype.Hub.Phone
{
    public sealed class PhoneMessageItemUI : MonoBehaviour
    {
        [Header("Required")]
        [SerializeField] private TMP_Text contentText;
        [SerializeField] private Image contentImage;
        [SerializeField] private LayoutElement imageLayout;

        [Header("Image Size Clamp")]
        [SerializeField] private float maxImageWidth = 360f;
        [SerializeField] private float maxImageHeight = 220f;
        [SerializeField] private float minImageHeight = 80f;

        public void Setup(PhoneMessageData data)
        {
            if (data == null)
            {
                SetTextVisible(false);
                SetImageVisible(false);
                return;
            }

            bool hasText = !string.IsNullOrWhiteSpace(data.text);
            bool hasImage = data.useImage && data.image != null;

            SetTextVisible(hasText);
            SetImageVisible(hasImage);

            if (hasText && contentText != null)
            {
                contentText.text = data.text;
            }

            if (hasImage && contentImage != null)
            {
                contentImage.sprite = data.image;
                contentImage.preserveAspect = true;
                ApplyImageSize(data.image);
            }
        }

        private void SetTextVisible(bool visible)
        {
            if (contentText != null)
            {
                contentText.gameObject.SetActive(visible);
            }
        }

        private void SetImageVisible(bool visible)
        {
            if (contentImage != null)
            {
                contentImage.gameObject.SetActive(visible);
            }
        }

        private void ApplyImageSize(Sprite sprite)
        {
            if (imageLayout == null || sprite == null)
            {
                return;
            }

            float srcW = Mathf.Max(1f, sprite.rect.width);
            float srcH = Mathf.Max(1f, sprite.rect.height);
            float scale = Mathf.Min(maxImageWidth / srcW, maxImageHeight / srcH);

            float targetW = srcW * scale;
            float targetH = srcH * scale;

            if (targetH < minImageHeight)
            {
                float ratio = minImageHeight / Mathf.Max(1f, targetH);
                targetH = minImageHeight;
                targetW *= ratio;
                if (targetW > maxImageWidth)
                {
                    targetW = maxImageWidth;
                }
            }

            imageLayout.preferredWidth = targetW;
            imageLayout.preferredHeight = targetH;
        }
    }
}
