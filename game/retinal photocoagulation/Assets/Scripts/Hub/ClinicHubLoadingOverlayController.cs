using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace RetinalPrototype.Hub
{
    public sealed class ClinicHubLoadingOverlayController : MonoBehaviour
    {
        [Header("Overlay")]
        [SerializeField] private GameObject overlayRoot;
        [SerializeField] private CanvasGroup overlayCanvasGroup;
        [SerializeField] private Image transitionBackgroundImage;
        [SerializeField] private bool overrideTransitionBackgroundColor;
        [SerializeField] private Color transitionBackgroundColor = new Color(0.137f, 0.180f, 0.255f, 1f);
        [SerializeField] private float fadeInSeconds = 0.15f;
        [SerializeField] private float fadeOutSeconds = 0.2f;
        [SerializeField] private bool dontDestroyOnLoad = true;

        [Header("Progress Bar")]
        [SerializeField] private Image progressFillImage;
        [SerializeField] private float minVisibleSeconds = 0.8f;
        [SerializeField] private float progressSmoothSpeed = 1.8f;
        [SerializeField, Range(0.5f, 0.99f)] private float waitingProgressCap = 0.95f;
        [SerializeField, Range(0.9f, 0.999f)] private float sceneActivationProgress = 0.98f;

        [Header("Character Animation")]
        [SerializeField] private RectTransform characterRectTransform;
        [SerializeField] private Animator characterAnimator;
        [SerializeField] private string actionStateParam = "ActionState";
        [SerializeField] private string isInteractingParam = "IsInteracting";
        [SerializeField] private bool centerCharacterOnShow = true;
        [SerializeField] private bool restartCharacterAnimationWhileLoading = true;
        [SerializeField] private float animationRestartSeconds = 1.2f;

        private static ClinicHubLoadingOverlayController _instance;
        private bool _isLoading;

        private void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }

            _instance = this;

            if (dontDestroyOnLoad)
            {
                DontDestroyOnLoad(gameObject);
            }

            HideImmediate();
        }

        public void LoadScene(string sceneName, ClinicHubAction loadingAction)
        {
            if (_isLoading || string.IsNullOrEmpty(sceneName))
            {
                return;
            }

            StartCoroutine(LoadSceneRoutine(sceneName, loadingAction));
        }

        private IEnumerator LoadSceneRoutine(string sceneName, ClinicHubAction loadingAction)
        {
            _isLoading = true;

            ShowImmediate();
            SetProgress(0f);
            SetCharacterAction(loadingAction);
            CenterCharacterIfNeeded();

            yield return FadeTo(1f, Mathf.Max(0f, fadeInSeconds), true);

            var loadOp = SceneManager.LoadSceneAsync(sceneName);
            if (loadOp == null)
            {
                yield return FadeTo(0f, Mathf.Max(0f, fadeOutSeconds), false);
                HideImmediate();
                _isLoading = false;
                yield break;
            }

            loadOp.allowSceneActivation = false;

            float elapsed = 0f;
            float displayedProgress = 0f;
            float animationRestartTimer = 0f;

            while (loadOp.progress < 0.9f || elapsed < minVisibleSeconds)
            {
                elapsed += Time.unscaledDeltaTime;
                animationRestartTimer += Time.unscaledDeltaTime;

                float loadProgress = Mathf.Clamp01(loadOp.progress / 0.9f);
                float timeProgress = minVisibleSeconds <= 0.0001f ? 1f : Mathf.Clamp01(elapsed / minVisibleSeconds);
                float targetProgress = Mathf.Min(loadProgress, timeProgress, waitingProgressCap);

                displayedProgress = Mathf.MoveTowards(
                    displayedProgress,
                    targetProgress,
                    Time.unscaledDeltaTime * Mathf.Max(0.01f, progressSmoothSpeed)
                );

                SetProgress(displayedProgress);

                if (restartCharacterAnimationWhileLoading && animationRestartTimer >= Mathf.Max(0.1f, animationRestartSeconds))
                {
                    RestartCurrentCharacterAnimation();
                    animationRestartTimer = 0f;
                }

                yield return null;
            }

            SetProgress(Mathf.Max(waitingProgressCap, sceneActivationProgress));
            yield return null;

            loadOp.allowSceneActivation = true;
            while (!loadOp.isDone)
            {
                yield return null;
            }

            SetProgress(1f);
            yield return null;

            yield return FadeTo(0f, Mathf.Max(0f, fadeOutSeconds), false);
            SetCharacterAction(ClinicHubAction.Idle);
            HideImmediate();
            _isLoading = false;
        }

        private void SetCharacterAction(ClinicHubAction action)
        {
            if (characterAnimator == null)
            {
                return;
            }

            characterAnimator.SetInteger(actionStateParam, (int)action);
            characterAnimator.SetBool(isInteractingParam, action != ClinicHubAction.Idle && action != ClinicHubAction.Walk);
        }

        private void RestartCurrentCharacterAnimation()
        {
            if (characterAnimator == null)
            {
                return;
            }

            var stateInfo = characterAnimator.GetCurrentAnimatorStateInfo(0);
            if (stateInfo.shortNameHash == 0)
            {
                return;
            }

            characterAnimator.Play(stateInfo.shortNameHash, 0, 0f);
            characterAnimator.Update(0f);
        }

        private void CenterCharacterIfNeeded()
        {
            if (!centerCharacterOnShow || characterRectTransform == null)
            {
                return;
            }

            characterRectTransform.anchorMin = new Vector2(0.5f, 0.5f);
            characterRectTransform.anchorMax = new Vector2(0.5f, 0.5f);
            characterRectTransform.pivot = new Vector2(0.5f, 0.5f);
            characterRectTransform.anchoredPosition = Vector2.zero;
        }

        private void SetProgress(float progress)
        {
            if (progressFillImage == null)
            {
                return;
            }

            progressFillImage.fillAmount = Mathf.Clamp01(progress);
        }

        private IEnumerator FadeTo(float targetAlpha, float duration, bool blockInput)
        {
            if (overlayCanvasGroup == null)
            {
                yield break;
            }

            overlayCanvasGroup.blocksRaycasts = blockInput;
            overlayCanvasGroup.interactable = blockInput;

            float startAlpha = overlayCanvasGroup.alpha;
            if (duration <= 0.0001f)
            {
                overlayCanvasGroup.alpha = targetAlpha;
                yield break;
            }

            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.unscaledDeltaTime;
                float t = Mathf.Clamp01(elapsed / duration);
                overlayCanvasGroup.alpha = Mathf.Lerp(startAlpha, targetAlpha, t);
                yield return null;
            }

            overlayCanvasGroup.alpha = targetAlpha;
            if (Mathf.Approximately(targetAlpha, 0f))
            {
                overlayCanvasGroup.blocksRaycasts = false;
                overlayCanvasGroup.interactable = false;
            }
        }

        private void ShowImmediate()
        {
            if (overlayRoot != null && overlayRoot != gameObject)
            {
                overlayRoot.SetActive(true);
            }

            if (overlayCanvasGroup != null)
            {
                overlayCanvasGroup.blocksRaycasts = true;
                overlayCanvasGroup.interactable = true;
            }

            if (transitionBackgroundImage != null)
            {
                if (overrideTransitionBackgroundColor)
                {
                    transitionBackgroundImage.color = transitionBackgroundColor;
                }

                transitionBackgroundImage.raycastTarget = true;
            }
        }

        private void HideImmediate()
        {
            if (overlayCanvasGroup != null)
            {
                overlayCanvasGroup.alpha = 0f;
                overlayCanvasGroup.blocksRaycasts = false;
                overlayCanvasGroup.interactable = false;
            }

            SetProgress(0f);

            if (overlayRoot != null && overlayRoot != gameObject)
            {
                overlayRoot.SetActive(false);
            }
        }
    }
}
