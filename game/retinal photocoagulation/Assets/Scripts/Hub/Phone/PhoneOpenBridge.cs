using UnityEngine;

namespace RetinalPrototype.Hub.Phone
{
    public sealed class PhoneOpenBridge : MonoBehaviour
    {
        [SerializeField] private PhonePanelController phonePanelController;

        public void OpenPhone()
        {
            if (phonePanelController != null)
            {
                phonePanelController.OpenPhone();
            }
        }

        public void ClosePhone()
        {
            if (phonePanelController != null)
            {
                phonePanelController.ClosePhone();
            }
        }
    }
}
