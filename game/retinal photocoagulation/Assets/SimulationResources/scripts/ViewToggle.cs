using UnityEngine;
using UnityEngine.UI;
using System.Collections;

public class ViewToggle : MonoBehaviour
{
    [Header("只需要拖动这一个：黑色眼底图所在的容器")]
    public RectTransform targetView; 
    
    [Header("全屏快捷键")]
    public KeyCode toggleKey = KeyCode.H;

    [Header("是否在进入场景时默认全屏")]
    public bool startInFullscreen = true; // 默认勾选，一进场景就全屏

    private Transform originalParent;
    private Vector2 originalAnchorMin, originalAnchorMax, originalSizeDelta, originalPos;
    private bool isFullscreen = false;
    
    private GameObject blocker;
    
    // 获取核心控制器
    private FundusFovController fovController;
    private SlitLampOverlayController slitLampController;

    void Start()
    {
        // 1. 先记录初始的父节点和排版属性（记住它缩小在面板里的样子）
        originalParent = targetView.parent;
        originalAnchorMin = targetView.anchorMin;
        originalAnchorMax = targetView.anchorMax;
        originalSizeDelta = targetView.sizeDelta;
        originalPos = targetView.anchoredPosition;
        
        // 2. 自动寻找并绑定控制器
        fovController = FindObjectOfType<FundusFovController>();
        slitLampController = FindObjectOfType<SlitLampOverlayController>();

        // 3. 如果勾选了默认全屏，立刻执行一次切换
        if (startInFullscreen)
        {
            ToggleView();
        }
    }

    void Update()
    {
        // 按下快捷键时，也执行同样的切换逻辑
        if (Input.GetKeyDown(toggleKey))
        {
            ToggleView();
        }
    }

    // 将原本的切换逻辑打包成一个独立的方法
    private void ToggleView()
    {
        isFullscreen = !isFullscreen;

        if (isFullscreen)
        {
            if (blocker == null) CreateBlocker();
            blocker.SetActive(true);

            // 提到最外层并拉伸
            targetView.SetParent(targetView.GetComponentInParent<Canvas>().transform, false);
            targetView.anchorMin = Vector2.zero;
            targetView.anchorMax = Vector2.one;
            targetView.sizeDelta = Vector2.zero;
            targetView.anchoredPosition = Vector2.zero;
            
            blocker.transform.SetAsLastSibling();
            targetView.SetAsLastSibling(); 
        }
        else
        {
            if (blocker != null) blocker.SetActive(false);
            
            // 放回原处并恢复尺寸
            targetView.SetParent(originalParent, false);
            targetView.anchorMin = originalAnchorMin;
            targetView.anchorMax = originalAnchorMax;
            targetView.sizeDelta = originalSizeDelta;
            targetView.anchoredPosition = originalPos;
        }

        // 开启协程，等待 UI 布局更新完毕后再刷新画面
        StartCoroutine(RefreshAfterLayoutUpdate());
    }

    // 协程：等待当前帧渲染结束，确保视野自适应比例正确
    IEnumerator RefreshAfterLayoutUpdate()
    {
        yield return new WaitForEndOfFrame();
        
        if (fovController != null) fovController.RefreshFovOnly();
        if (slitLampController != null) slitLampController.Refresh();
    }

    // 自动生成黑底背景
    void CreateBlocker()
    {
        blocker = new GameObject("FullscreenBlocker");
        blocker.transform.SetParent(targetView.GetComponentInParent<Canvas>().transform, false);
        
        RectTransform rect = blocker.AddComponent<RectTransform>();
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.sizeDelta = Vector2.zero;
        rect.anchoredPosition = Vector2.zero;

        Image img = blocker.AddComponent<Image>();
        img.color = new Color(0.04f, 0.08f, 0.11f, 1f);
        img.raycastTarget = true; 
    }
}