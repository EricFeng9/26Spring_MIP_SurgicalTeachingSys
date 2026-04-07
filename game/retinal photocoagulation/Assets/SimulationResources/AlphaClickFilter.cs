using UnityEngine;
using UnityEngine.UI;

[RequireComponent(typeof(Image))]
public class AlphaClickFilter : MonoBehaviour
{
    void Start()
    {
        // 核心：设置透明度阈值
        // 0.1f 表示：如果这个像素的透明度(Alpha)小于 10%，鼠标点击就会直接穿透它！
        // 如果大于 10%（实心部分），点击就会被这个图片死死挡住。
        GetComponent<Image>().alphaHitTestMinimumThreshold = 0.1f;
    }
}