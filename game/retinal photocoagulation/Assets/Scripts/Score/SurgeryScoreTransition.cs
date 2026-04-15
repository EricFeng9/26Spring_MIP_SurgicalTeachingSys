using DG.Tweening;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class SurgeryScoreTransition : MonoBehaviour
{
    [Header("Layer References")]
    public RectTransform eyepieceMask;
    public CanvasGroup eyepieceGroup;
    public RectTransform surgeryContainer;
    public CanvasGroup surgeryGroup;
    public Image dimOverlay;

    [Header("Scoreboard References")]
    public CanvasGroup scoreBoardGroup;
    public TextMeshProUGUI reportText;
    public TextMeshProUGUI finalScoreText;

    [Header("Linked Scripts")]
    public SceneNavigator sceneNavigator;

    [Header("Animation Params")]
    public float transitionDuration = 1.5f;
    public Vector3 targetEyepiecePos = new Vector3(-300f, 100f, 0f);

    [Header("Typing Params")]
    public float secondsPerCharacter = 0.06f;
    public int demoFinalScore = 88;

    private Sequence mainSequence;
    private Sequence scoreSequence;
    private Sequence stampSequence;
    private Sequence closeSequence;
    private Tween typewriterTween;

    private int cachedVisibleChars;
    private bool isScoreBoardOpen;
    private bool isTypingReport;
    private bool hasStampedFinalScore;

    private void Start()
    {
        ResetScoreBoardVisualState();
    }

    private void Update()
    {
        if (!isScoreBoardOpen || !isTypingReport)
        {
            return;
        }

        if (IsAnyPointerDownThisFrame())
        {
            SkipTypewriterAndShowFinal();
        }
    }

    public void TriggerSurgeryEnd()
    {
        KillRuntimeTweens();
        ResetReportRuntimeStateOnly();

        mainSequence = DOTween.Sequence();
        mainSequence.Join(eyepieceGroup.DOFade(0f, 0.3f));
        mainSequence.Join(surgeryGroup.DOFade(0f, 0.3f));
        mainSequence.Join(dimOverlay.DOFade(0.7f, transitionDuration));
        mainSequence.OnComplete(ShowScoreBoard);
    }

    public void CloseScoreBoard()
    {
        // Stop any running scoreboard flow immediately so next round always starts clean.
        mainSequence?.Kill();
        scoreSequence?.Kill();
        stampSequence?.Kill();
        typewriterTween?.Kill();

        isTypingReport = false;
        isScoreBoardOpen = false;
        hasStampedFinalScore = false;

        closeSequence?.Kill();
        closeSequence = DOTween.Sequence();

        scoreBoardGroup.interactable = false;
        scoreBoardGroup.blocksRaycasts = false;

        closeSequence.Append(scoreBoardGroup.DOFade(0f, 0.2f));
        closeSequence.Join(scoreBoardGroup.transform.DOLocalMoveY(-50f, 0.2f).SetEase(Ease.InCubic));
        closeSequence.Join(dimOverlay.DOFade(0f, 0.2f));

        closeSequence.OnComplete(() =>
        {
            ResetReportRuntimeStateOnly();

            if (sceneNavigator != null)
            {
                sceneNavigator.GoToMainViewWithoutBlackout();
            }
            else
            {
                Debug.LogError("SceneNavigator is not assigned, cannot return to main view.");
            }
        });
    }

    private void ShowScoreBoard()
    {
        scoreSequence?.Kill();
        scoreSequence = DOTween.Sequence();

        scoreBoardGroup.alpha = 0f;
        scoreBoardGroup.interactable = true;
        scoreBoardGroup.blocksRaycasts = true;
        scoreBoardGroup.transform.localPosition = new Vector3(scoreBoardGroup.transform.localPosition.x, -50f, 0f);

        isScoreBoardOpen = true;
        isTypingReport = true;
        hasStampedFinalScore = false;

        scoreSequence.Join(scoreBoardGroup.DOFade(1f, 0.5f));
        scoreSequence.Join(scoreBoardGroup.transform.DOLocalMoveY(0f, 0.5f).SetEase(Ease.OutCubic));

        string title = "<b>📋 眼底光凝评估报告</b>\n<color=#555555>--------------------------------</color>\n";
        string section1 =
            "<pos=0%><b>一、靶区覆盖评估</b>\n" +
            "<pos=0%>•宏观覆盖率(IoU: 81%)<color=#888888>........</color><pos=80%><color=#008000>+ 32</color>\n" +
            "<pos=0%>•大血管误击(0 次)<color=#888888>..............</color><pos=80%><color=#555555>- 0</color>\n\n";
        string section2 =
            "<pos=0%><b>二、激光参数控制</b>\n" +
            "<pos=0%>•功率控制 (精准)<color=#888888>................</color><pos=80%><color=#008000>+ 10</color>\n" +
            "<pos=0%>•曝光时间 (偏长)<color=#888888>................</color><pos=80%><color=#FF8C00>+ 6</color>\n\n";
        string section3 =
            "<pos=0%><b>三、空间分布质量</b>\n" +
            "<pos=0%>•疏密控制 (R=1.1)<color=#888888>...............</color><pos=80%><color=#008000>+ 12</color>\n" +
            "<pos=0%>•手法稳定 (方差达标)<color=#888888>............</color><pos=80%><color=#008000>+ 15</color>\n\n";

        string fullReport = title + section1 + section2 + section3;
        reportText.text = fullReport;
        reportText.ForceMeshUpdate();

        cachedVisibleChars = reportText.textInfo.characterCount;
        reportText.maxVisibleCharacters = 0;

        float typeDuration = Mathf.Max(0f, cachedVisibleChars * secondsPerCharacter);
        typewriterTween = DOTween.To(
                () => reportText.maxVisibleCharacters,
                value => reportText.maxVisibleCharacters = value,
                cachedVisibleChars,
                typeDuration)
            .SetEase(Ease.Linear);

        scoreSequence.Append(typewriterTween);
        scoreSequence.OnComplete(() =>
        {
            isTypingReport = false;
            StampFinalScore(demoFinalScore);
        });
    }

    private void SkipTypewriterAndShowFinal()
    {
        if (!isTypingReport)
        {
            return;
        }

        isTypingReport = false;
        scoreSequence?.Kill();
        typewriterTween?.Kill();

        reportText.maxVisibleCharacters = cachedVisibleChars;
        StampFinalScore(demoFinalScore);
    }

    private void StampFinalScore(int score)
    {
        if (hasStampedFinalScore)
        {
            return;
        }
        hasStampedFinalScore = true;

        finalScoreText.text = score.ToString();
        finalScoreText.transform.localScale = Vector3.one * 3f;
        finalScoreText.color = new Color(0.8f, 0.1f, 0.1f, 0f);

        stampSequence?.Kill();
        stampSequence = DOTween.Sequence();
        stampSequence.Append(finalScoreText.transform.DOScale(1f, 0.3f).SetEase(Ease.InExpo));
        stampSequence.Join(finalScoreText.DOFade(1f, 0.3f).SetEase(Ease.InExpo));
        stampSequence.Append(finalScoreText.transform.DOPunchScale(Vector3.one * 0.2f, 0.3f, 10, 1f));
    }

    private bool IsAnyPointerDownThisFrame()
    {
        if (Input.GetMouseButtonDown(0))
        {
            return true;
        }

        if (Input.touchCount > 0 && Input.GetTouch(0).phase == TouchPhase.Began)
        {
            return true;
        }

        return false;
    }

    private void KillRuntimeTweens()
    {
        mainSequence?.Kill();
        scoreSequence?.Kill();
        stampSequence?.Kill();
        closeSequence?.Kill();
        typewriterTween?.Kill();
    }

    private void ResetReportRuntimeStateOnly()
    {
        reportText.text = string.Empty;
        reportText.maxVisibleCharacters = 0;

        finalScoreText.text = string.Empty;
        finalScoreText.transform.localScale = Vector3.one;
        finalScoreText.color = new Color(0.8f, 0.1f, 0.1f, 0f);

        cachedVisibleChars = 0;
        isTypingReport = false;
        hasStampedFinalScore = false;
    }

    private void ResetScoreBoardVisualState()
    {
        KillRuntimeTweens();
        ResetReportRuntimeStateOnly();

        scoreBoardGroup.alpha = 0f;
        scoreBoardGroup.interactable = false;
        scoreBoardGroup.blocksRaycasts = false;
        scoreBoardGroup.transform.localPosition = new Vector3(scoreBoardGroup.transform.localPosition.x, -50f, 0f);

        dimOverlay.color = new Color(0f, 0f, 0f, 0f);
        isScoreBoardOpen = false;
    }
}
