using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace RetinalPrototype
{
    public sealed class MainMenuFlowController : MonoBehaviour
    {
        [SerializeField] private Text statusText;
        [SerializeField] private string saveSelectSceneName = PrototypeSceneNames.SaveSelect;
        [SerializeField] private float statusAutoClearSeconds = 3f;

        private float _statusExpireTime = -1f;

        private void Update()
        {
            if (_statusExpireTime < 0f)
            {
                return;
            }

            if (Time.unscaledTime < _statusExpireTime)
            {
                return;
            }

            _statusExpireTime = -1f;
            SetStatus(string.Empty);
        }

        public void StartNewGame()
        {
            SceneManager.LoadScene(saveSelectSceneName);
        }

        public void ContinueGame()
        {
            if (PrototypeSaveSystem.HasAnySave())
            {
                SceneManager.LoadScene(saveSelectSceneName);
                return;
            }

            SetStatus("未检测到可继续的进度，请先创建一个存档。");
        }

        private void SetStatus(string message)
        {
            if (statusText == null)
            {
                return;
            }

            statusText.text = message;
            _statusExpireTime = string.IsNullOrEmpty(message)
                ? -1f
                : Time.unscaledTime + Mathf.Max(0.5f, statusAutoClearSeconds);
        }
    }
}
