using UnityEngine;
using DG.Tweening;

public class UICameraController : MonoBehaviour
{
    [Header("全场景根节点")]
    public RectTransform sceneRoot;

    [Header("视角参数 (在运行模式下手调试好填进来)")]
    // 1. 全景状态 (默认)
    public float scaleMain = 1f;
    public Vector2 posMain = Vector2.zero;

    // 2. 靠近目镜状态
    [Tooltip("目镜放大倍数，比如 2.5")]
    public float scaleEyepiece = 2.5f;
    [Tooltip("把场景往右下角推的坐标，比如 X: 400, Y: -200")]
    public Vector2 posEyepiece; 

    // 3. 靠近显示屏状态
    [Tooltip("显示屏放大倍数，比如 2.0")]
    public float scaleMonitor = 2.0f;
    [Tooltip("把场景往左边推的坐标，比如 X: -500, Y: -100")]
    public Vector2 posMonitor;

    [Header("运镜时间")]
    public float moveDuration = 1f;

    // --- 给按钮绑定的公共方法 ---
    public void GoToMainView()
    {
        MoveScene(posMain, scaleMain);
    }

    public void GoToEyepiece()
    {
        MoveScene(posEyepiece, scaleEyepiece);
    }

    public void GoToMonitor()
    {
        MoveScene(posMonitor, scaleMonitor);
    }

    // --- 核心 UI 运镜逻辑 ---
    private void MoveScene(Vector2 targetPos, float targetScale)
    {
        // 杀掉正在进行的动画，防止抽搐
        sceneRoot.DOKill();

        // 放大/缩小容器
        sceneRoot.DOScale(targetScale, moveDuration).SetEase(Ease.InOutCubic);
        // 移动容器 (使用 DOAnchorPos 更适合 UI)
        sceneRoot.DOAnchorPos(targetPos, moveDuration).SetEase(Ease.InOutCubic);
    }
}