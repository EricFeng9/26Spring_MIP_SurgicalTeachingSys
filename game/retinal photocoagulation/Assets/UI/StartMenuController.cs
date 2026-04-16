using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace RetinalPrototype
{
    public sealed class StartMenuController : MonoBehaviour
    {
        [Header("Panels")]
        [SerializeField] private GameObject mainPanel;
        [SerializeField] private GameObject creditsPanel;
        [SerializeField] private MenuSettingsController settingsPanel;

        [Header("Buttons")]
        [SerializeField] private Button continueButton;

        [Header("Scene Targets")]
        [SerializeField] private string newGameSceneName = PrototypeSceneNames.SaveSelect;
        [SerializeField] private string continueSceneName = PrototypeSceneNames.InGameComputer;

        [Header("Optional")]
        [SerializeField] private TextMeshProUGUI statusText;
        [SerializeField] private float statusAutoClearSeconds = 3f;
        [SerializeField] private SceneTransitionController sceneTransition;

        private float _statusExpireAt = -1f;

        private void Awake()
        {
            ShowMainPanel();
            RefreshContinueState();
        }

        private void Update()
        {
            if (_statusExpireAt < 0f || Time.unscaledTime < _statusExpireAt || statusText == null)
            {
                return;
            }

            statusText.text = string.Empty;
            _statusExpireAt = -1f;
        }

        public void OnClickNewGame()
        {
            LoadScene(newGameSceneName);
        }

        public void OnClickContinue()
        {
            if (!PrototypeSaveSystem.HasAnySave())
            {
                SetStatus("No save data found. Please start a new game first.");
                RefreshContinueState();
                return;
            }

            if (PrototypeSaveSystem.CurrentSlot <= 0 &&
                PrototypeSaveSystem.TryGetAnySavedSlot(out var firstSlot))
            {
                PrototypeSaveSystem.ActivateSlot(firstSlot);
            }

            LoadScene(continueSceneName);
        }

        public void OnClickCredits()
        {
            if (creditsPanel != null)
            {
                creditsPanel.SetActive(true);
            }

            if (mainPanel != null)
            {
                mainPanel.SetActive(false);
            }
        }

        public void OnClickSettings()
        {
            if (settingsPanel != null)
            {
                settingsPanel.OpenFrom(mainPanel);
            }
        }

        public void OnClickBackFromCredits()
        {
            ShowMainPanel();
        }

        public void ShowMainPanel()
        {
            if (mainPanel != null)
            {
                mainPanel.SetActive(true);
            }

            if (creditsPanel != null)
            {
                creditsPanel.SetActive(false);
            }

            if (settingsPanel != null)
            {
                settingsPanel.CloseTo(mainPanel);
            }

            RefreshContinueState();
        }

        private void RefreshContinueState()
        {
            if (continueButton != null)
            {
                continueButton.interactable = PrototypeSaveSystem.HasAnySave();
            }
        }

        private void LoadScene(string sceneName)
        {
            if (string.IsNullOrEmpty(sceneName))
            {
                SetStatus("Target scene is not configured.");
                return;
            }

            if (sceneTransition != null)
            {
                sceneTransition.LoadScene(sceneName);
                return;
            }

            UnityEngine.SceneManagement.SceneManager.LoadScene(sceneName);
        }

        private void SetStatus(string message)
        {
            if (statusText == null)
            {
                return;
            }

            statusText.text = message;
            _statusExpireAt = string.IsNullOrEmpty(message)
                ? -1f
                : Time.unscaledTime + Mathf.Max(0.5f, statusAutoClearSeconds);
        }
    }
}
