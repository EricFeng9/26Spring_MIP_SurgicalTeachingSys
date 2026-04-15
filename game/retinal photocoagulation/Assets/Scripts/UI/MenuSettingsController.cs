using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace RetinalPrototype
{
    public sealed class MenuSettingsController : MonoBehaviour
    {
        private const string VolumeKey = "Settings.MasterVolume";
        private const string FullScreenKey = "Settings.FullScreen";
        private const string QualityKey = "Settings.Quality";

        [Header("Settings Panel")]
        [SerializeField] private GameObject settingsPanelRoot;
        [SerializeField] private Slider masterVolumeSlider;
        [SerializeField] private Toggle fullScreenToggle;
        [SerializeField] private TMP_Dropdown qualityDropdown;

        [Header("Optional")]
        [SerializeField] private SceneTransitionController sceneTransition;

        private GameObject _returnPanel;
        private bool _isRefreshingUi;

        private void Awake()
        {
            if (settingsPanelRoot != null)
            {
                settingsPanelRoot.SetActive(false);
            }
        }

        public void OpenFrom(GameObject returnPanel)
        {
            _returnPanel = returnPanel;

            if (_returnPanel != null)
            {
                _returnPanel.SetActive(false);
            }

            if (settingsPanelRoot != null)
            {
                settingsPanelRoot.SetActive(true);
            }

            RefreshUiFromCurrentSettings();
        }

        public void CloseTo(GameObject returnPanel)
        {
            if (settingsPanelRoot != null)
            {
                settingsPanelRoot.SetActive(false);
            }

            if (returnPanel != null)
            {
                returnPanel.SetActive(true);
            }
        }

        public void OnClickBack()
        {
            CloseTo(_returnPanel);
        }

        public void OnMasterVolumeChanged(float value)
        {
            if (_isRefreshingUi)
            {
                return;
            }

            var clamped = Mathf.Clamp01(value);
            AudioListener.volume = clamped;
            PlayerPrefs.SetFloat(VolumeKey, clamped);
            PlayerPrefs.Save();
        }

        public void OnFullScreenChanged(bool isFullScreen)
        {
            if (_isRefreshingUi)
            {
                return;
            }

            Screen.fullScreen = isFullScreen;
            PlayerPrefs.SetInt(FullScreenKey, isFullScreen ? 1 : 0);
            PlayerPrefs.Save();
        }

        public void OnQualityChanged(int qualityIndex)
        {
            if (_isRefreshingUi)
            {
                return;
            }

            var maxIndex = Mathf.Max(0, QualitySettings.names.Length - 1);
            var safeIndex = Mathf.Clamp(qualityIndex, 0, maxIndex);
            QualitySettings.SetQualityLevel(safeIndex, true);
            PlayerPrefs.SetInt(QualityKey, safeIndex);
            PlayerPrefs.Save();
        }

        public void OnClickQuitGame()
        {
            #if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
            #else
            Application.Quit();
            #endif
        }

        public void ApplySavedSettings()
        {
            var volume = PlayerPrefs.GetFloat(VolumeKey, 1f);
            var fullScreen = PlayerPrefs.GetInt(FullScreenKey, Screen.fullScreen ? 1 : 0) == 1;
            var quality = PlayerPrefs.GetInt(QualityKey, QualitySettings.GetQualityLevel());

            AudioListener.volume = Mathf.Clamp01(volume);
            Screen.fullScreen = fullScreen;
            QualitySettings.SetQualityLevel(Mathf.Clamp(quality, 0, Mathf.Max(0, QualitySettings.names.Length - 1)), true);
        }

        public void GoToSceneFromSettings(string sceneName)
        {
            if (string.IsNullOrEmpty(sceneName))
            {
                return;
            }

            if (sceneTransition != null)
            {
                sceneTransition.LoadScene(sceneName);
                return;
            }

            UnityEngine.SceneManagement.SceneManager.LoadScene(sceneName);
        }

        private void RefreshUiFromCurrentSettings()
        {
            _isRefreshingUi = true;
            ApplySavedSettings();

            if (masterVolumeSlider != null)
            {
                masterVolumeSlider.value = AudioListener.volume;
            }

            if (fullScreenToggle != null)
            {
                fullScreenToggle.isOn = Screen.fullScreen;
            }

            if (qualityDropdown != null)
            {
                qualityDropdown.ClearOptions();
                qualityDropdown.AddOptions(new System.Collections.Generic.List<string>(QualitySettings.names));
                qualityDropdown.value = QualitySettings.GetQualityLevel();
                qualityDropdown.RefreshShownValue();
            }

            _isRefreshingUi = false;
        }
    }
}
