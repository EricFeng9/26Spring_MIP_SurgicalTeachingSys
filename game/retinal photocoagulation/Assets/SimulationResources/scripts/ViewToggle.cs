using UnityEngine;
using UnityEngine.UI;
using System.Collections; // 引入协程库

public class ViewToggle : MonoBehaviour
{
    [Header("只需要拖动这一个：黑色眼底图所在的容器")]
    public RectTransform targetView; 
    
    [Header("全屏快捷键")]
    public KeyCode toggleKey = KeyCode.H;

    private Transform originalParent;
    private Vector2 originalAnchorMin, originalAnchorMax, originalSizeDelta, originalPos;
    private bool isFullscreen = false;
    
    private GameObject blocker;
    
    // 获取核心控制器
    private FundusFovController fovController;
    private SlitLampOverlayController slitLampController;

    void Start()
    {
        // 记录初始的父节点和排版属性
        originalParent = targetView.parent;
        originalAnchorMin = targetView.anchorMin;
        originalAnchorMax = targetView.anchorMax;
        originalSizeDelta = targetView.sizeDelta;
        originalPos = targetView.anchoredPosition;
        
        // 自动寻找并绑定控制器
        fovController = FindObjectOfType<FundusFovController>();
        slitLampController = FindObjectOfType<SlitLampOverlayController>();
    }

    void Update()
    {
        if (Input.GetKeyDown(toggleKey))
        {
            isFullscreen = !isFullscreen;

            if (isFullscreen)
            {
                if (blocker == null) CreateBlocker();
                blocker.SetActive(true);

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
                
                targetView.SetParent(originalParent, false);
                targetView.anchorMin = originalAnchorMin;
                targetView.anchorMax = originalAnchorMax;
                targetView.sizeDelta = originalSizeDelta;
                targetView.anchoredPosition = originalPos;
            }

            // 【终极修复】：开启协程，等待 UI 布局更新完毕后再刷新画面
            StartCoroutine(RefreshAfterLayoutUpdate());
        }
    }

    // 协程：等待当前帧渲染结束
    IEnumerator RefreshAfterLayoutUpdate()
    {
        // WaitForEndOfFrame 会等待 Unity 把所有的 UI 拉伸、排版彻底计算完毕
        yield return new WaitForEndOfFrame();
        
        // 此时获取的 rect.width 和 rect.height 绝对是完全准确的！
        if (fovController != null) fovController.RefreshFovOnly();
        if (slitLampController != null) slitLampController.Refresh();
    }

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