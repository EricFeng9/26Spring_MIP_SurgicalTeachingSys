using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class UIValueLinker : MonoBehaviour
{
    public Slider slider;
    public TMP_InputField inputField;

    void Awake()
    {
        if (slider == null || inputField == null) return;

        // 初始化数值
        inputField.text = slider.value.ToString();

        // 绑定：Slider 变，Input 跟随
        slider.onValueChanged.AddListener((val) => {
            inputField.text = val.ToString("0"); // "0" 表示取整
        });

        // 绑定：Input 变，Slider 跟随
        inputField.onEndEdit.AddListener((text) => {
            if (float.TryParse(text, out float result))
            {
                slider.value = result;
            }
        });
    }
}