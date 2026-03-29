using UnityEngine;
using UnityEngine.SceneManagement;

namespace RetinalPrototype
{
    public sealed class SceneLoadButton : MonoBehaviour
    {
        [SerializeField] private string targetSceneName;
        [SerializeField] private bool verboseLog;

        public void SetTargetScene(string sceneName)
        {
            targetSceneName = sceneName;
        }

        public void LoadTargetScene()
        {
            if (string.IsNullOrEmpty(targetSceneName))
            {
                Debug.LogWarning("Target scene is empty.");
                return;
            }

            if (verboseLog)
            {
                Debug.Log("Load scene: " + targetSceneName);
            }

            SceneManager.LoadScene(targetSceneName);
        }
    }
}
