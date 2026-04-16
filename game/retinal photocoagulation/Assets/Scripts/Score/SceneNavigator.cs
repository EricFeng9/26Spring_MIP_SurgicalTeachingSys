using UnityEngine;
using UnityEngine.UI; // 注意：需要引入 UI 命名空间来控制 Image
using DG.Tweening;

public class SceneNavigator : MonoBehaviour
{
    [Header("全场景根节点")]
    public RectTransform sceneRoot;

    [Header("需要开关的图层")]
    public CanvasGroup eyepieceGroup;  // 黑圈遮罩
    public CanvasGroup surgeryGroup;   // 手术画面

    [Header("黑屏过渡遮罩")]
    public Image transitionBlackScreen; // 纯黑的过渡幕布

    [Header("导航按钮容器")]
    public GameObject navButtonsContainer; // 👈 新增：用来一键开关所有隐形按钮

    [Header("视角参数 (需在运行模式下自己微调)")]
    public float scaleMain = 1f;
    public Vector2 posMain = Vector2.zero;

    [Tooltip("靠近目镜的放大倍数和位置")]
    public float scaleEyepiece = 2.5f;
    public Vector2 posEyepiece = new Vector2(400f, -200f); 

    [Tooltip("靠近显示屏的放大倍数和位置")]
    public float scaleMonitor = 2.0f;
    public Vector2 posMonitor = new Vector2(-500f, -100f);

    public float moveDuration = 1.2f;

    private void Start()
    {
        // 游戏一开始：强制进入全局视角
        sceneRoot.localScale = Vector3.one * scaleMain;
        sceneRoot.anchoredPosition = posMain;

        // 隐藏目镜黑圈和手术画面，防止挡住后面的机器
        eyepieceGroup.alpha = 0f;
        eyepieceGroup.blocksRaycasts = false;
        surgeryGroup.alpha = 0f;
        surgeryGroup.blocksRaycasts = false;

        // 确保黑屏遮罩一开始是透明的且不挡点击
        if (transitionBlackScreen != null)
        {
            transitionBlackScreen.color = new Color(0, 0, 0, 0);
            transitionBlackScreen.raycastTarget = false;
        }

        // 👈 新增：确保一开始在全局视角时，导航按钮是可以点的
        if (navButtonsContainer != null) navButtonsContainer.SetActive(true);
    }

    public void GoToEyepiece()
    {
        // 👈 新增：玩家进入目镜后，立刻关掉所有导航按钮，彻底杜绝误触！
        if (navButtonsContainer != null) navButtonsContainer.SetActive(false); 

        // 开启防误触：动画期间黑屏遮挡点击，防止玩家狂点
        if (transitionBlackScreen != null) transitionBlackScreen.raycastTarget = true;
        
        // 创建一个严格排序的动画序列
        Sequence seq = DOTween.Sequence();

        // 步骤 1：镜头推进 (放大并平移)。此时手术页面是透明的，绝不会穿帮。
        seq.Append(sceneRoot.DOScale(scaleEyepiece, moveDuration).SetEase(Ease.InOutCubic));
        seq.Join(sceneRoot.DOAnchorPos(posEyepiece, moveDuration).SetEase(Ease.InOutCubic));

        // 步骤 2：全屏幕变黑 (用 0.3 秒瞬间拉下纯黑幕布)
        seq.Append(transitionBlackScreen.DOFade(1f, 0.3f));

        // 步骤 3：狸猫换太子 (在黑屏的掩护下，瞬间重置所有尺寸！)
        seq.AppendCallback(() => 
        {
            // A. 瞬间把场景尺寸恢复回 1 倍 (完美解决 UI 跟着变巨大的问题)
            sceneRoot.localScale = Vector3.one * scaleMain;
            sceneRoot.anchoredPosition = posMain;

            // B. 瞬间激活手术页面和黑圈遮罩 (由于当前屏幕是纯黑的，玩家看不见这瞬间的切换)
            eyepieceGroup.alpha = 1f;
            surgeryGroup.alpha = 1f;
            surgeryGroup.blocksRaycasts = true;
        });

        // 步骤 4：黑屏散去 (用 0.5 秒淡出黑屏，露出完美尺寸的手术视野)
        seq.Append(transitionBlackScreen.DOFade(0f, 0.5f));

        // 步骤 5：动画彻底结束，解除防误触
        seq.OnComplete(() => 
        {
            if (transitionBlackScreen != null) transitionBlackScreen.raycastTarget = false;
        });
    }

    public void GoToMonitor()
    {
        // 进入显示屏时，同样关掉导航按钮避免误触
        if (navButtonsContainer != null) navButtonsContainer.SetActive(false);

        sceneRoot.DOKill();
        sceneRoot.DOScale(scaleMonitor, moveDuration).SetEase(Ease.InOutCubic);
        sceneRoot.DOAnchorPos(posMonitor, moveDuration).SetEase(Ease.InOutCubic);
    }

    // 新增：返回全局视角的方法
    public void GoToMainView()
    {
        // 开启防误触：动画期间黑屏遮挡
        if (transitionBlackScreen != null) transitionBlackScreen.raycastTarget = true;
        
        Sequence seq = DOTween.Sequence();

        // 步骤 1：全屏幕变黑 (用 0.3 秒瞬间拉下幕布)
        seq.Append(transitionBlackScreen.DOFade(1f, 0.3f));

        // 步骤 2：在黑屏掩护下，重置所有状态回初始模样
        seq.AppendCallback(() => 
        {
            // A. 尺寸重置回全景
            sceneRoot.localScale = Vector3.one * scaleMain;
            sceneRoot.anchoredPosition = posMain;

            // B. 彻底隐藏手术图层和目镜遮罩
            eyepieceGroup.alpha = 0f;
            eyepieceGroup.blocksRaycasts = false;
            surgeryGroup.alpha = 0f;
            surgeryGroup.blocksRaycasts = false;

            // C. 重新开启导航按钮，让玩家可以再次点击机器其他部位！
            if (navButtonsContainer != null) navButtonsContainer.SetActive(true);
        });

        // 步骤 3：黑屏散去，露出干净的全景机器
        seq.Append(transitionBlackScreen.DOFade(0f, 0.5f));

        // 步骤 4：解除防误触
        seq.OnComplete(() => 
        {
            if (transitionBlackScreen != null) transitionBlackScreen.raycastTarget = false;
        });
    }
}