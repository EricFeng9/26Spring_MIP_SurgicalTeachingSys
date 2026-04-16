using TMPro;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    public sealed class ClinicHubArrivalNotifier : MonoBehaviour
    {
        [SerializeField] private GameObject patientHalfBodyAtDoor;
        [SerializeField] private CanvasGroup noticeCanvasGroup;
        [SerializeField] private TextMeshProUGUI noticeText;
        [SerializeField] private float autoHideSeconds = 3f;
        [SerializeField] private string arrivedMessage = "患者已到场，可开始治疗";

        private float _hideAt = -1f;

        private void Awake()
        {
            if (patientHalfBodyAtDoor != null)
            {
                patientHalfBodyAtDoor.SetActive(false);
            }

            SetNoticeVisible(false);
        }

        private void Update()
        {
            if (_hideAt > 0f && Time.unscaledTime >= _hideAt)
            {
                _hideAt = -1f;
                SetNoticeVisible(false);
            }
        }

        public void MarkPatientArrived()
        {
            if (patientHalfBodyAtDoor != null)
            {
                patientHalfBodyAtDoor.SetActive(true);
            }

            if (noticeText != null)
            {
                noticeText.text = arrivedMessage;
            }

            SetNoticeVisible(true);
            _hideAt = autoHideSeconds > 0f ? Time.unscaledTime + autoHideSeconds : -1f;
        }

        public void ClearArrival()
        {
            if (patientHalfBodyAtDoor != null)
            {
                patientHalfBodyAtDoor.SetActive(false);
            }

            _hideAt = -1f;
            SetNoticeVisible(false);
        }

        private void SetNoticeVisible(bool visible)
        {
            if (noticeCanvasGroup == null)
            {
                return;
            }

            noticeCanvasGroup.alpha = visible ? 1f : 0f;
            noticeCanvasGroup.blocksRaycasts = false;
            noticeCanvasGroup.interactable = false;
        }
    }
}
