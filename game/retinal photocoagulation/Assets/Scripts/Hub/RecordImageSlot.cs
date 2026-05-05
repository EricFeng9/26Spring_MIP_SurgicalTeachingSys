using UnityEngine;
using UnityEngine.UI;

namespace RetinalPrototype.Hub
{
    [RequireComponent(typeof(Image))]
    public sealed class RecordImageSlot : MonoBehaviour
    {
        private enum ImageFitMode
        {
            PreserveAspectInsideSlot = 0,
            StretchToSlot = 1
        }

        [SerializeField] private Image targetImage;
        [SerializeField] private ImageFitMode fitMode = ImageFitMode.StretchToSlot;
        [SerializeField] private bool cropTransparentBorder = true;
        [SerializeField, Range(0f, 1f)] private float alphaThreshold = 0.02f;
        [SerializeField] private Sprite fallbackSprite;

        private void Reset()
        {
            targetImage = GetComponent<Image>();
        }

        private void Awake()
        {
            if (targetImage == null)
            {
                targetImage = GetComponent<Image>();
            }
        }

        public void SetSprite(Sprite sprite)
        {
            if (targetImage == null)
            {
                return;
            }

            Sprite displaySprite = sprite != null ? sprite : fallbackSprite;
            if (displaySprite != null && cropTransparentBorder)
            {
                displaySprite = SpriteTransparentCropper.GetCroppedSprite(displaySprite, alphaThreshold);
            }

            targetImage.sprite = displaySprite;
            targetImage.enabled = displaySprite != null;
            targetImage.preserveAspect = fitMode == ImageFitMode.PreserveAspectInsideSlot;
            targetImage.type = Image.Type.Simple;
        }
    }
}
