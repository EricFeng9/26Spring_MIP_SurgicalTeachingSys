using DG.Tweening;
using UnityEngine;
using UnityEngine.UI;

public class SceneNavigator : MonoBehaviour
{
    [Header("Root")]
    public RectTransform sceneRoot;

    [Header("Layers")]
    public CanvasGroup eyepieceGroup;
    public CanvasGroup surgeryGroup;

    [Header("Transition")]
    public Image transitionBlackScreen;

    [Header("Navigation Buttons")]
    public GameObject navButtonsContainer;

    [Header("View Params")]
    public float scaleMain = 1f;
    public Vector2 posMain = Vector2.zero;

    [Tooltip("Eyepiece zoom and position")]
    public float scaleEyepiece = 2.5f;
    public Vector2 posEyepiece = new Vector2(400f, -200f);

    [Tooltip("Monitor zoom and position")]
    public float scaleMonitor = 2.0f;
    public Vector2 posMonitor = new Vector2(-500f, -100f);

    public float moveDuration = 1.2f;

    private void Start()
    {
        sceneRoot.localScale = Vector3.one * scaleMain;
        sceneRoot.anchoredPosition = posMain;

        eyepieceGroup.alpha = 0f;
        eyepieceGroup.blocksRaycasts = false;
        surgeryGroup.alpha = 0f;
        surgeryGroup.blocksRaycasts = false;

        if (transitionBlackScreen != null)
        {
            transitionBlackScreen.color = new Color(0f, 0f, 0f, 0f);
            transitionBlackScreen.raycastTarget = false;
        }

        if (navButtonsContainer != null)
        {
            navButtonsContainer.SetActive(true);
        }
    }

    public void GoToEyepiece()
    {
        if (navButtonsContainer != null)
        {
            navButtonsContainer.SetActive(false);
        }

        if (transitionBlackScreen != null)
        {
            transitionBlackScreen.raycastTarget = true;
        }

        Sequence seq = DOTween.Sequence();
        seq.Append(sceneRoot.DOScale(scaleEyepiece, moveDuration).SetEase(Ease.InOutCubic));
        seq.Join(sceneRoot.DOAnchorPos(posEyepiece, moveDuration).SetEase(Ease.InOutCubic));

        if (transitionBlackScreen != null)
        {
            seq.Append(transitionBlackScreen.DOFade(1f, 0.3f));
        }

        seq.AppendCallback(() =>
        {
            sceneRoot.localScale = Vector3.one * scaleMain;
            sceneRoot.anchoredPosition = posMain;

            eyepieceGroup.alpha = 1f;
            surgeryGroup.alpha = 1f;
            surgeryGroup.blocksRaycasts = true;
        });

        if (transitionBlackScreen != null)
        {
            seq.Append(transitionBlackScreen.DOFade(0f, 0.5f));
        }

        seq.OnComplete(() =>
        {
            if (transitionBlackScreen != null)
            {
                transitionBlackScreen.raycastTarget = false;
            }
        });
    }

    public void GoToMonitor()
    {
        if (navButtonsContainer != null)
        {
            navButtonsContainer.SetActive(false);
        }

        sceneRoot.DOKill();
        sceneRoot.DOScale(scaleMonitor, moveDuration).SetEase(Ease.InOutCubic);
        sceneRoot.DOAnchorPos(posMonitor, moveDuration).SetEase(Ease.InOutCubic);
    }

    public void GoToMainView()
    {
        if (transitionBlackScreen != null)
        {
            transitionBlackScreen.raycastTarget = true;
        }

        Sequence seq = DOTween.Sequence();

        if (transitionBlackScreen != null)
        {
            seq.Append(transitionBlackScreen.DOFade(1f, 0.3f));
        }

        seq.AppendCallback(RestoreMainViewState);

        if (transitionBlackScreen != null)
        {
            seq.Append(transitionBlackScreen.DOFade(0f, 0.5f));
        }

        seq.OnComplete(() =>
        {
            if (transitionBlackScreen != null)
            {
                transitionBlackScreen.raycastTarget = false;
            }
        });
    }

    public void GoToMainViewWithoutBlackout()
    {
        RestoreMainViewState();

        if (transitionBlackScreen != null)
        {
            Color c = transitionBlackScreen.color;
            transitionBlackScreen.color = new Color(c.r, c.g, c.b, 0f);
            transitionBlackScreen.raycastTarget = false;
        }
    }

    private void RestoreMainViewState()
    {
        sceneRoot.DOKill();
        sceneRoot.localScale = Vector3.one * scaleMain;
        sceneRoot.anchoredPosition = posMain;

        eyepieceGroup.alpha = 0f;
        eyepieceGroup.blocksRaycasts = false;
        surgeryGroup.alpha = 0f;
        surgeryGroup.blocksRaycasts = false;

        if (navButtonsContainer != null)
        {
            navButtonsContainer.SetActive(true);
        }
    }
}
