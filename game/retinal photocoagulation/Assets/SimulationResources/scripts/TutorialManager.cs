using UnityEngine;
using UnityEngine.UI;
using System.Collections.Generic;
using TMPro;

public class TutorialManager : MonoBehaviour
{
    [Header("--- 教程基础组件 ---")]
    public GameObject tutorialCanvas;
    public GameObject darkOverlay;
    
    [Header("--- 唯一的提示文本组件 (拖入 PromptText) ---")]
    public TMP_Text promptText; 

    [Header("--- Target GameObjects (需要高亮的游戏真实物体) ---")]
    public Button calibrationButton;      
    public GameObject controlPanelArea;   
    public GameObject miniMapArea;        
    public GameObject infoBarArea;        
    public GameObject fovViewport; 
    public Button endSurgeryButton;       

    private int currentStep = 0;
    private FundusFovController fovController;

    private class HighlightData
    {
        public GameObject target;
        public Canvas canvas;
        public GraphicRaycaster raycaster;
        public bool addedCanvas;
        public bool addedRaycaster;
        public int originalSortingOrder;
        public bool originalOverrideSorting;
    }
    
    private List<HighlightData> activeHighlights = new List<HighlightData>();
    private Image darkOverlayImage;

    void Start()
    {
        fovController = FindObjectOfType<FundusFovController>();
        if (fovController != null)
            fovController.DiscCalibrationLineCompleted += OnCalibrationFinished;

        if (darkOverlay != null) 
        {
            darkOverlay.SetActive(true);
            darkOverlayImage = darkOverlay.GetComponent<Image>();
        }

        if (calibrationButton != null)
            calibrationButton.onClick.AddListener(OnCalibrationButtonClicked);

        // 【核心修复】：解决文字被高亮物体遮挡的问题
        // 给提示文字单独加一个 Canvas，把层级设为 105（永远在最顶层）
        if (promptText != null)
        {
            Canvas textCanvas = promptText.gameObject.GetComponent<Canvas>();
            if (textCanvas == null) textCanvas = promptText.gameObject.AddComponent<Canvas>();
            textCanvas.overrideSorting = true;
            textCanvas.sortingOrder = 105; 
        }
            
        // 游戏开始，直接进入第 0 步
        GoToStep(0); 
    }

    void OnDestroy()
    {
        if (fovController != null)
            fovController.DiscCalibrationLineCompleted -= OnCalibrationFinished;
    }

    void Update()
    {
        if (currentStep == 0 && Input.GetKeyDown(KeyCode.H))
        {
            GoToStep(1);
        }
        // 【逻辑修改】：现在第 3 到第 6 步，全都是“点击屏幕任意位置继续/结束”
        else if ((currentStep >= 3 && currentStep <= 6) && Input.GetMouseButtonDown(0))
        {
            if (currentStep == 6) 
                EndTutorial(); // 第 6 步点完直接结束，开始游戏！
            else 
                GoToStep(currentStep + 1); 
        }
    }

    private void GoToStep(int stepIndex)
    {
        currentStep = stepIndex;

        switch (currentStep)
        {
            case 0:
                promptText.text = "欢迎进入视网膜光凝手术模拟系统！\n\n为了获得更专业的沉浸式视野，请先按下键盘上的 <color=#47A5AE>[H]</color> 键展开设备控制面板。";
                ChangeHighlights(); 
                break;

            case 1:
                promptText.text = "手术的第一步是校准视盘比例，以确保激光光斑大小的精确度。\n\n请点击右侧操作台中的 <color=#47A5AE>[START DISC CALIBRATION]</color> 按钮进入标定模式。";
                ChangeHighlights(calibrationButton.gameObject, fovViewport);
                break;

            case 2:
                promptText.text = "现在进入视盘标定模式。\n\n你可以使用键盘的 <color=#47A5AE>[W][A][S][D]</color> 键移动视野找到视盘（眼底发亮的圆形区域）。\n然后在视盘边缘的两端分别点击一下，画出一条穿过视盘的直径线段即可完成校准。";
                ChangeHighlights(fovViewport); 
                if (darkOverlayImage != null) darkOverlayImage.raycastTarget = false; 
                break;

            case 3:
                // 【文案增加焦点引导】：非常醒目地告诉玩家失去焦点怎么办
                promptText.text = "校准成功！这里是【激光控制台】。\n在这里调节激光的工作模式、波长、功率等参数。\n\n<color=#E75A31>💡 操作提示：当你点击这些UI控件后，键盘移动会暂时锁定。如需继续使用 [W][A][S][D] 移动视野，请在左侧手术画面任意位置点击鼠标左键找回焦点。</color>\n\n<size=80%><color=#AAAAAA>(点击屏幕任意位置继续)</color></size>";
                ChangeHighlights(controlPanelArea);
                break;

            case 4:
                promptText.text = "这是【全局小地图 (Mini Map)】。\n\n在手术过程中，它会为你提供俯瞰视角，实时显示你当前的视野位置以及已经完成的激光击打点，防止漏打或重打。\n\n<size=80%><color=#AAAAAA>(点击屏幕任意位置继续)</color></size>";
                ChangeHighlights(miniMapArea);
                break;

            case 5:
                promptText.text = "这是【状态信息栏】。\n\n它会实时记录你的手术已用时间、总击打次数，并评估你上一发激光的能量等级。\n\n<size=80%><color=#AAAAAA>(点击屏幕任意位置继续)</color></size>";
                ChangeHighlights(infoBarArea);
                break;
                
            case 6:
                // 【文案修改】：仅作介绍，点击任意位置结束教程
                promptText.text = "所有操作完成后，点击此处的 <color=#E75A31>[END SURGERY]</color> 按钮即可结束手术。\n\n系统将自动进行结算，并为你生成本次手术的详细评估报告。\n\n<size=80%><color=#AAAAAA>(点击屏幕任意位置结束教程，正式开始手术！)</color></size>";
                ChangeHighlights(endSurgeryButton.gameObject);
                break;
        }
    }

    private void OnCalibrationButtonClicked()
    {
        if (currentStep == 1) GoToStep(2); 
    }

    private void OnCalibrationFinished(float distancePx)
    {
        if (currentStep == 2)
        {
            if (darkOverlayImage != null) darkOverlayImage.raycastTarget = true; 
            GoToStep(3); 
        }
    }

    private void ChangeHighlights(params GameObject[] newTargets)
    {
        List<HighlightData> toRemove = new List<HighlightData>();
        foreach (var data in activeHighlights)
        {
            bool keep = false;
            foreach (var target in newTargets)
            {
                if (data.target == target) { keep = true; break; }
            }
            if (!keep) toRemove.Add(data);
        }

        foreach (var data in toRemove)
        {
            if (data.raycaster != null && data.addedRaycaster) Destroy(data.raycaster);
            if (data.canvas != null)
            {
                if (data.addedCanvas) Destroy(data.canvas);
                else
                {
                    data.canvas.overrideSorting = data.originalOverrideSorting;
                    data.canvas.sortingOrder = data.originalSortingOrder;
                }
            }
            activeHighlights.Remove(data);
        }

        foreach (var target in newTargets)
        {
            if (target == null) continue;

            bool alreadyHighlighted = false;
            foreach (var data in activeHighlights)
            {
                if (data.target == target) { alreadyHighlighted = true; break; }
            }
            if (alreadyHighlighted) continue;

            HighlightData newData = new HighlightData { target = target };

            newData.canvas = target.GetComponent<Canvas>();
            if (newData.canvas == null)
            {
                newData.canvas = target.AddComponent<Canvas>();
                newData.addedCanvas = true;
            }
            else
            {
                newData.addedCanvas = false;
                newData.originalOverrideSorting = newData.canvas.overrideSorting;
                newData.originalSortingOrder = newData.canvas.sortingOrder;
            }
            newData.canvas.overrideSorting = true;
            newData.canvas.sortingOrder = 101; 

            newData.raycaster = target.GetComponent<GraphicRaycaster>();
            if (newData.raycaster == null)
            {
                newData.raycaster = target.AddComponent<GraphicRaycaster>();
                newData.addedRaycaster = true;
            }
            else
            {
                newData.addedRaycaster = false;
            }

            activeHighlights.Add(newData);
        }
    }

    private void EndTutorial()
    {
        ChangeHighlights(); 
        if (darkOverlay != null) darkOverlay.SetActive(false);
        if (tutorialCanvas != null) tutorialCanvas.SetActive(false);
        else gameObject.SetActive(false);
    }
}