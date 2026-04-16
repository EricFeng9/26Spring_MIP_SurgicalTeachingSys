using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace RetinalPrototype
{
    public sealed class SceneTransitionController : MonoBehaviour
    {
        [Header("Fade Overlay")]
        [SerializeField] private CanvasGroup fadeCanvasGroup;
        [SerializeField] private Image fadeImage;
        [SerializeField] private float fadeOutSeconds = 0.25f;
        [SerializeField] private float fadeInSeconds = 0.25f;
        [SerializeField] private bool dontDestroyOnLoad = true;

        private bool _isTransitioning;

        private void Awake()
        {
            if (dontDestroyOnLoad)
            {
                DontDestroyOnLoad(gameObject);
            }

            if (fadeCanvasGroup != null)
            {
                fadeCanvasGroup.alpha = 0f;
                fadeCanvasGroup.blocksRaycasts = false;
                fadeCanvasGroup.interactable = false;
            }

            if (fadeImage != null)
            {
                fadeImage.raycastTarget = true;
            }
        }

        public void LoadScene(string sceneName)
        {
            if (_isTransitioning || string.IsNullOrEmpty(sceneName))
            {
                return;
            }

            StartCoroutine(LoadSceneRoutine(sceneName));
        }

        private IEnumerator LoadSceneRoutine(string sceneName)
        {
            _isTransitioning = true;

            yield return FadeTo(1f, Mathf.Max(0f, fadeOutSeconds), true);

            var loadOp = SceneManager.LoadSceneAsync(sceneName);
            while (loadOp != null && !loadOp.isDone)
            {
                yield return null;
            }

            yield return FadeTo(0f, Mathf.Max(0f, fadeInSeconds), false);
            _isTransitioning = false;
        }

        private IEnumerator FadeTo(float targetAlpha, float duration, bool blockInput)
        {
            if (fadeCanvasGroup == null)
            {
                yield break;
            }

            fadeCanvasGroup.blocksRaycasts = blockInput;
            fadeCanvasGroup.interactable = blockInput;

            var start = fadeCanvasGroup.alpha;
            if (duration <= 0.0001f)
            {
                fadeCanvasGroup.alpha = targetAlpha;
                yield break;
            }

            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.unscaledDeltaTime;
                var t = Mathf.Clamp01(elapsed / duration);
                fadeCanvasGroup.alpha = Mathf.Lerp(start, targetAlpha, t);
                yield return null;
            }

            fadeCanvasGroup.alpha = targetAlpha;
            if (Mathf.Approximately(targetAlpha, 0f))
            {
                fadeCanvasGroup.blocksRaycasts = false;
                fadeCanvasGroup.interactable = false;
            }
        }
    }
}
