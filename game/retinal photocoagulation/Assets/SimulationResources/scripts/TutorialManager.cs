using UnityEngine;
using UnityEngine.UI;
using System.Collections.Generic;

public class TutorialManager : MonoBehaviour
{
    [Header("--- 教程基础组件 ---")]
    public GameObject tutorialCanvas;
    public GameObject darkOverlay;

    [Header("--- Tutorial UI (教程的提示文字) ---")]
    public GameObject step0_PressH;
    public GameObject step1_ClickCalibration;
    public GameObject step1_5_DrawLine;     
    public GameObject step2_ControlPanel;
    public GameObject step3_MiniMap;
    public GameObject step4_InfoBar;

    [Header("--- Target GameObjects (需要高亮的游戏真实物体) ---")]
    public Button calibrationButton;      
    public GameObject controlPanelArea;   
    public GameObject miniMapArea;        
    public GameObject infoBarArea;        
    
    [Header("--- 新增：眼底画面的容器 ---")]
    public GameObject fovViewport; // 把 Panel_ViewportContainer 拖到这里

    private int currentStep = 0;
    private FundusFovController fovController;

    // 用一个类来记录所有被提层级的物体状态，支持同时高亮无限个物体！
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
    
    // 记录当前处于高亮状态的物体列表
    private List<HighlightData> activeHighlights = new List<HighlightData>();

    void Start()
    {
        fovController = FindObjectOfType<FundusFovController>();
        if (fovController != null)
            fovController.DiscCalibrationLineCompleted += OnCalibrationFinished;

        if (darkOverlay != null) darkOverlay.SetActive(true);
        
        HideAllSteps();
        if (step0_PressH != null) step0_PressH.SetActive(true);

        if (calibrationButton != null)
            calibrationButton.onClick.AddListener(OnCalibrationButtonClicked);
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
        else if ((currentStep >= 2 && currentStep <= 4) && Input.GetMouseButtonDown(0))
        {
            if (currentStep == 4) 
                EndTutorial(); 
            else 
                GoToStep(currentStep + 1); 
        }
    }

    private void GoToStep(int stepIndex)
    {
        currentStep = stepIndex;
        HideAllSteps();
        RemoveAllHighlights(); // 切换步骤前，清理上一步的所有高亮

        switch (currentStep)
        {
            case 1:
                if (step1_ClickCalibration != null) step1_ClickCalibration.SetActive(true);
                // 【魔法在此】：把按钮 和 眼底画面 一起提到黑布上面！
                HighlightObjects(calibrationButton.gameObject, fovViewport);
                break;
            case 2:
                if (step2_ControlPanel != null) step2_ControlPanel.SetActive(true);
                HighlightObjects(controlPanelArea);
                break;
            case 3:
                if (step3_MiniMap != null) step3_MiniMap.SetActive(true);
                HighlightObjects(miniMapArea);
                break;
            case 4:
                if (step4_InfoBar != null) step4_InfoBar.SetActive(true);
                HighlightObjects(infoBarArea);
                break;
        }
    }

    private void OnCalibrationButtonClicked()
    {
        if (currentStep == 1)
        {
            RemoveAllHighlights();
            if (step1_ClickCalibration != null) step1_ClickCalibration.SetActive(false);
            if (step1_5_DrawLine != null) step1_5_DrawLine.SetActive(true);
            
            // 1.5 步：只需要高亮眼底画面，让玩家可以自由移动和画线。
            // 此时其他 UI（包括标定按钮）都会被黑布阻挡，防止乱点出 Bug。
            HighlightObjects(fovViewport);
        }
    }

    private void OnCalibrationFinished(float distancePx)
    {
        if (currentStep == 1)
        {
            if (step1_5_DrawLine != null) step1_5_DrawLine.SetActive(false);
            GoToStep(2); 
        }
    }

    // --- 核心魔法：支持传入多个物体进行高亮 ---
    private void HighlightObjects(params GameObject[] targets)
    {
        foreach (var target in targets)
        {
            if (target == null) continue;

            HighlightData data = new HighlightData { target = target };

            data.canvas = target.GetComponent<Canvas>();
            if (data.canvas == null)
            {
                data.canvas = target.AddComponent<Canvas>();
                data.addedCanvas = true;
            }
            else
            {
                data.addedCanvas = false;
                data.originalOverrideSorting = data.canvas.overrideSorting;
                data.originalSortingOrder = data.canvas.sortingOrder;
            }

            data.canvas.overrideSorting = true;
            data.canvas.sortingOrder = 101; 

            data.raycaster = target.GetComponent<GraphicRaycaster>();
            if (data.raycaster == null)
            {
                data.raycaster = target.AddComponent<GraphicRaycaster>();
                data.addedRaycaster = true;
            }
            else
            {
                data.addedRaycaster = false;
            }

            activeHighlights.Add(data);
        }
    }

    private void RemoveAllHighlights()
    {
        // 必须倒序清理组件，先销毁 Raycaster，再处理 Canvas，否则 Unity 会报错
        foreach (var data in activeHighlights)
        {
            if (data.target == null) continue;

            if (data.raycaster != null)
            {
                if (data.addedRaycaster) Destroy(data.raycaster);
            }

            if (data.canvas != null)
            {
                if (data.addedCanvas) Destroy(data.canvas);
                else
                {
                    data.canvas.overrideSorting = data.originalOverrideSorting;
                    data.canvas.sortingOrder = data.originalSortingOrder;
                }
            }
        }
        activeHighlights.Clear();
    }

    private void HideAllSteps()
    {
        if (step0_PressH != null) step0_PressH.SetActive(false);
        if (step1_ClickCalibration != null) step1_ClickCalibration.SetActive(false);
        if (step1_5_DrawLine != null) step1_5_DrawLine.SetActive(false);
        if (step2_ControlPanel != null) step2_ControlPanel.SetActive(false);
        if (step3_MiniMap != null) step3_MiniMap.SetActive(false);
        if (step4_InfoBar != null) step4_InfoBar.SetActive(false);
    }

    private void EndTutorial()
    {
        RemoveAllHighlights();
        HideAllSteps();
        if (darkOverlay != null) darkOverlay.SetActive(false);
        if (tutorialCanvas != null) tutorialCanvas.SetActive(false);
        else gameObject.SetActive(false);
    }
}