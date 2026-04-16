using UnityEngine;
using UnityEditor;
using UnityEngine.UI;
using TMPro;

public static class ReplaceTextWithTMP
{
    [MenuItem("Tools/Replace/All Text To TMP In Scene")]
    public static void ReplaceAllTextToTMPInScene()
    {
        Text[] texts = Object.FindObjectsOfType<Text>(true);
        int count = 0;

        foreach (var oldText in texts)
        {
            var go = oldText.gameObject;

            // 已经有 TMP 就跳过
            if (go.GetComponent<TextMeshProUGUI>() != null)
                continue;

            string value = oldText.text;
            int fontSize = oldText.fontSize;
            Color color = oldText.color;
            FontStyle fontStyle = oldText.fontStyle;
            TextAnchor anchor = oldText.alignment;
            bool raycastTarget = oldText.raycastTarget;

            var rect = go.GetComponent<RectTransform>();
            Vector2 anchorMin = rect.anchorMin;
            Vector2 anchorMax = rect.anchorMax;
            Vector2 anchoredPosition = rect.anchoredPosition;
            Vector2 sizeDelta = rect.sizeDelta;
            Vector2 pivot = rect.pivot;
            Vector3 localScale = rect.localScale;
            Quaternion localRotation = rect.localRotation;

            Object.DestroyImmediate(oldText, true);

            var tmp = go.AddComponent<TextMeshProUGUI>();
            tmp.text = value;
            tmp.fontSize = fontSize;
            tmp.color = color;
            tmp.raycastTarget = raycastTarget;
            tmp.enableWordWrapping = false;

            // 粗略映射字体样式
            if (fontStyle == FontStyle.Bold || fontStyle == FontStyle.BoldAndItalic)
                tmp.fontStyle = FontStyles.Bold;
            else if (fontStyle == FontStyle.Italic)
                tmp.fontStyle = FontStyles.Italic;
            else
                tmp.fontStyle = FontStyles.Normal;

            // 对齐映射
            tmp.alignment = ConvertAlignment(anchor);

            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.anchoredPosition = anchoredPosition;
            rect.sizeDelta = sizeDelta;
            rect.pivot = pivot;
            rect.localScale = localScale;
            rect.localRotation = localRotation;

            count++;
        }

        Debug.Log($"替换完成：{count} 个 Text -> TextMeshProUGUI");
    }

    static TextAlignmentOptions ConvertAlignment(TextAnchor anchor)
    {
        switch (anchor)
        {
            case TextAnchor.UpperLeft: return TextAlignmentOptions.TopLeft;
            case TextAnchor.UpperCenter: return TextAlignmentOptions.Top;
            case TextAnchor.UpperRight: return TextAlignmentOptions.TopRight;
            case TextAnchor.MiddleLeft: return TextAlignmentOptions.Left;
            case TextAnchor.MiddleCenter: return TextAlignmentOptions.Center;
            case TextAnchor.MiddleRight: return TextAlignmentOptions.Right;
            case TextAnchor.LowerLeft: return TextAlignmentOptions.BottomLeft;
            case TextAnchor.LowerCenter: return TextAlignmentOptions.Bottom;
            case TextAnchor.LowerRight: return TextAlignmentOptions.BottomRight;
            default: return TextAlignmentOptions.Center;
        }
    }
}