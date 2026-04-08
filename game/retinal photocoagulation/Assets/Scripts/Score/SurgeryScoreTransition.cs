using UnityEngine;
using UnityEngine.UI;
using DG.Tweening;
using TMPro; // 引入 TextMeshPro

public class SurgeryScoreTransition : MonoBehaviour
{
    
    [Header("图层引用 (拖拽UI节点到这里)")]
    public RectTransform eyepieceMask;      // 目镜遮罩
    public CanvasGroup eyepieceGroup;       // 目镜遮罩的CanvasGroup
    public RectTransform surgeryContainer;  // 手术画面容器
    public CanvasGroup surgeryGroup;        // 手术画面的CanvasGroup
    public Image dimOverlay;                // 黑色暗化遮罩
    
    [Header("结算页面引用")]
    public CanvasGroup scoreBoardGroup;     // 夹板的CanvasGroup
    public TextMeshProUGUI reportText;      // 报告文本
    public TextMeshProUGUI finalScoreText;  // 右下角大分数

    [Header("脚本联动")]
    public SceneNavigator sceneNavigator;

    [Header("动画参数")]
    public float transitionDuration = 1.5f; // 抽离镜头的动画时间
    public Vector3 targetEyepiecePos = new Vector3(-300f, 100f, 0f); // 假设这是机器目镜在屏幕上的坐标

    private void Start()
    {
        // 这个脚本现在只负责初始化结算相关的状态
        scoreBoardGroup.alpha = 0f;
        scoreBoardGroup.blocksRaycasts = false;
        dimOverlay.color = new Color(0, 0, 0, 0);
        reportText.text = "";
        finalScoreText.text = "";
        
        // 删除了原本在这里强行放大 EyepieceMask 和 SurgeryContainer 的代码
        // 因为这些初始状态交给了新的导航脚本来管理
    }

    // 在你的游戏逻辑判定手术结束时，调用这个方法！
    // 可以在任何按钮的 OnClick 里绑定这个方法用来测试
    public void TriggerSurgeryEnd()
    {
        Sequence mainSeq = DOTween.Sequence();

        // 步骤 1：物理抽离错觉（同步进行）
        // 遮罩和手术画面一起缩小，并移动到“机器的目镜”位置
        // mainSeq.Join(eyepieceMask.DOScale(0f, transitionDuration).SetEase(Ease.InOutSine));
        // mainSeq.Join(eyepieceMask.DOLocalMove(targetEyepiecePos, transitionDuration).SetEase(Ease.InOutSine));
        // mainSeq.Join(eyepieceGroup.DOFade(0f, transitionDuration));

        // mainSeq.Join(surgeryContainer.DOScale(0f, transitionDuration).SetEase(Ease.InOutSine));
        // mainSeq.Join(surgeryContainer.DOLocalMove(targetEyepiecePos, transitionDuration).SetEase(Ease.InOutSine));
        // mainSeq.Join(surgeryGroup.DOFade(0f, transitionDuration));

        mainSeq.Join(eyepieceGroup.DOFade(0f, 0.3f));
        mainSeq.Join(surgeryGroup.DOFade(0f, 0.3f));

        // 步骤 2：背景暗化
        mainSeq.Join(dimOverlay.DOFade(0.7f, transitionDuration));

        // 步骤 3：动画完成后，弹出夹板并开始写字
        mainSeq.OnComplete(() =>
        {
            ShowScoreBoard();
        });
    }

    private void ShowScoreBoard()
    {
        Sequence scoreSeq = DOTween.Sequence();
        
        scoreBoardGroup.blocksRaycasts = true;
        
        // 夹板淡入并微微上浮
        scoreBoardGroup.transform.localPosition = new Vector3(scoreBoardGroup.transform.localPosition.x, -50f, 0f);
        scoreSeq.Join(scoreBoardGroup.DOFade(1f, 0.5f));
        scoreSeq.Join(scoreBoardGroup.transform.DOLocalMoveY(0f, 0.5f).SetEase(Ease.OutCubic));

        // 准备文本内容 (利用富文本设置颜色和排版)
        string title = "<b>📋 眼底光凝评估报告</b>\n<color=#555555>--------------------------------</color>\n";
        string section1 = "<pos=0%><b>一、 靶区覆盖评估</b>\n" + 
                        "<pos=0%>□ 宏观覆盖率 (IoU: 81%)<color=#888888>........</color><pos=80%><color=#008000>+ 32</color>\n" + 
                        "<pos=0%>□ 大血管误击 (0 处)<color=#888888>..............</color><pos=80%><color=#555555>- 0</color>\n\n";
                        
        string section2 = "<pos=0%><b>二、 激光参数控制</b>\n" + 
                        "<pos=0%>□ 功率控制 (精准)<color=#888888>................</color><pos=80%><color=#008000>+ 10</color>\n" + 
                        "<pos=0%>□ 曝光时间 (偏长)<color=#888888>................</color><pos=80%><color=#FF8C00>+ 6</color>\n\n";
                        
        string section3 = "<pos=0%><b>三、 空间分布质量</b>\n" + 
                        "<pos=0%>□ 疏密控制 (R=1.1)<color=#888888>...............</color><pos=80%><color=#008000>+ 12</color>\n" + 
                        "<pos=0%>□ 手法稳定 (方差达标)<color=#888888>............</color><pos=80%><color=#008000>+ 15</color>\n\n";

        string fullReport = title + section1 + section2 + section3;

        // 使用 DOTween 的 DOText 实现打字机效果
        // 参数说明：(目标字符串, 持续时间).SetEase(Linear)确保打字速度匀速
        // scoreSeq.Append(reportText.DOText(fullReport, 2.5f).SetEase(Ease.Linear));
        // 确保一开始文本是空的
        // 1. 把包含所有颜色、加粗标签的完整文本，一次性塞给文本框
        reportText.text = fullReport;

        // 2. 强制 TextMeshPro 刷新一下排版，这样它才能算出“到底有多少个真正的可见字”
        reportText.ForceMeshUpdate();
        int totalVisibleChars = reportText.textInfo.characterCount; // 拿到去除了标签后的纯净字数！

        // 3. 将当前可见字符设为 0 (此时文本框有内容，但全都隐身了)
        reportText.maxVisibleCharacters = 0;

        // 4. 根据“真实可见字数”计算时间，每个字 0.06 秒
        float typeDuration = totalVisibleChars * 0.06f; 

        // 5. 让 DOTween 去改变 maxVisibleCharacters 属性
        scoreSeq.Append(
            DOTween.To(
                () => reportText.maxVisibleCharacters,        // 初始值
                x => reportText.maxVisibleCharacters = x,     // 赋值给这个属性
                totalVisibleChars,                            // 目标值（全部显示）
                typeDuration                                  // 动画时间
            ).SetEase(Ease.Linear)
        );

        // 打字结束后，盖章出总分
        scoreSeq.OnComplete(() =>
        {
            StampFinalScore(88); // 假设总分88
        });
    }

    private void StampFinalScore(int score)
    {
        // 先设为透明且非常大
        finalScoreText.text = score.ToString();
        finalScoreText.transform.localScale = Vector3.one * 3f;
        finalScoreText.color = new Color(0.8f, 0.1f, 0.1f, 0f); // 红色透明

        Sequence stampSeq = DOTween.Sequence();
        
        // 瞬间缩小并变不透明，模拟“啪”地一下盖章
        stampSeq.Append(finalScoreText.transform.DOScale(1f, 0.3f).SetEase(Ease.InExpo));
        stampSeq.Join(finalScoreText.DOFade(1f, 0.3f).SetEase(Ease.InExpo));
        
        // 盖章后的微小震动反馈
        stampSeq.Append(finalScoreText.transform.DOPunchScale(Vector3.one * 0.2f, 0.3f, 10, 1f));
        
        // 可选：在这里播放“咚”的音效
        // GetComponent<AudioSource>().PlayOneShot(stampSound);
    }
    // 新增：关闭结算页面并返回全景
    public void CloseScoreBoard()
    {
        Sequence closeSeq = DOTween.Sequence();

        // 1. 瞬间关闭点击交互，防止玩家狂点退出按钮
        scoreBoardGroup.blocksRaycasts = false;

        // 2. 夹板淡出并向下沉降
        closeSeq.Append(scoreBoardGroup.DOFade(0f, 0.4f));
        closeSeq.Join(scoreBoardGroup.transform.DOLocalMoveY(-50f, 0.4f).SetEase(Ease.InCubic));

        // 3. 背景暗化层褪去 (变回完全透明)
        closeSeq.Join(dimOverlay.DOFade(0f, 0.4f));

        // 4. 动画结束后，通知 SceneNavigator 开始黑屏转场回到全景！
        closeSeq.OnComplete(() =>
        {
            if (sceneNavigator != null)
            {
                sceneNavigator.GoToMainView();
            }
            else
            {
                Debug.LogError("没有绑定 SceneNavigator，无法返回全景！");
            }
        });
    }
}