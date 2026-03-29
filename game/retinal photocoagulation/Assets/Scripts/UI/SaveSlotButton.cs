using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace RetinalPrototype
{
    public sealed class SaveSlotButton : MonoBehaviour
    {
        [SerializeField] private int slotIndex = 1;
        [SerializeField] private string destinationSceneName = PrototypeSceneNames.InGameComputer;
        [SerializeField] private Text labelText;

        private void OnEnable()
        {
            RefreshLabel();
        }

        private void Start()
        {
            RefreshLabel();
        }

        public void OnClickSelectSlot()
        {
            PrototypeSaveSystem.ActivateSlot(slotIndex);
            SceneManager.LoadScene(destinationSceneName);
        }

        public void RefreshLabel()
        {
            if (labelText == null)
            {
                return;
            }

            var hasSave = PrototypeSaveSystem.HasSave(slotIndex);
            var isCurrent = PrototypeSaveSystem.CurrentSlot == slotIndex;
            var slotState = hasSave ? "已有进度" : "空白";
            var current = isCurrent ? " | 当前使用" : string.Empty;
            labelText.text = $"存档位 {slotIndex} | {slotState}{current}";
        }

        public void Configure(int index, string destination, Text textRef)
        {
            slotIndex = index;
            destinationSceneName = destination;
            labelText = textRef;
            RefreshLabel();
        }
    }
}
