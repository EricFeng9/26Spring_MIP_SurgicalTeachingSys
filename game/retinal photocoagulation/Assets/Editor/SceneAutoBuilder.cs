using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using System.Collections.Generic;

public class SceneAutoBuilderInteractive : EditorWindow
{
    private static Font _legacyFont;
    private static Color _panelBgColor = new Color(0.96f, 0.96f, 0.96f); 
    private static Color _darkTextColor = new Color(0.2f, 0.2f, 0.2f); // 统一使用深色文字

    [MenuItem("Tools/一比一复刻UI + 真实参数控制面板")]
    public static void BuildScene()
    {
        Scene newScene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        newScene.name = "LaserSimulation_Interactive";

        _legacyFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        // ================= 1. 3D 渲染空间 =================
        GameObject renderCamObj = new GameObject("RetinaCamera");
        Camera renderCam = renderCamObj.AddComponent<Camera>();
        renderCam.clearFlags = CameraClearFlags.SolidColor;
        renderCam.backgroundColor = Color.black;
        renderCam.transform.position = new Vector3(0, 0, -10);

        RenderTexture rt = new RenderTexture(2048, 2048, 24); 
        rt.name = "RetinaRenderTexture";
        renderCam.targetTexture = rt;

        GameObject retinaObj = GameObject.CreatePrimitive(PrimitiveType.Quad);
        retinaObj.name = "Retina3DCanvas";
        retinaObj.transform.position = Vector3.zero;
        retinaObj.transform.localScale = new Vector3(16f, 16f, 1f); 

        // ================= 2. 主 Canvas 框架 =================
        GameObject canvasObj = new GameObject("MainCanvas");
        Canvas canvas = canvasObj.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvasObj.AddComponent<CanvasScaler>().uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        canvasObj.GetComponent<CanvasScaler>().referenceResolution = new Vector2(1920, 1080);
        canvasObj.AddComponent<GraphicRaycaster>();

        GameObject eventSystem = new GameObject("EventSystem");
        eventSystem.AddComponent<UnityEngine.EventSystems.EventSystem>();
        eventSystem.AddComponent<UnityEngine.EventSystems.StandaloneInputModule>();

        // --- A. 左侧操作面板 ---
        BuildLeftPanel(canvasObj.transform);

        // --- B. 中间视野区 ---
        BuildCenterViewport(canvasObj.transform, rt);

        // --- C. 右侧参数控制面板 ---
        BuildRightControlPanel(canvasObj.transform);

        EditorSceneManager.MarkSceneDirty(newScene);
        Debug.Log("✅ UI 风格已统一优化，长文本自动缩放已开启，导出按钮已重命名！");
    }

    // =========================================================
    // UI 构建模块
    // =========================================================

    private static void BuildLeftPanel(Transform parent)
    {
        GameObject leftPanel = new GameObject("LeftPanel");
        leftPanel.transform.SetParent(parent, false);
        RectTransform leftRect = leftPanel.AddComponent<RectTransform>();
        leftRect.anchorMin = new Vector2(0, 0); leftRect.anchorMax = new Vector2(0.15f, 1);
        leftRect.offsetMin = leftRect.offsetMax = Vector2.zero;
        leftPanel.AddComponent<Image>().color = _panelBgColor;

        VerticalLayoutGroup vlg = leftPanel.AddComponent<VerticalLayoutGroup>();
        vlg.childForceExpandHeight = false; vlg.childControlHeight = true;
        vlg.spacing = 20; // 稍微缩小间距，让按钮有更好的呼吸感
        vlg.padding = new RectOffset(20, 20, 50, 50);

        CreateButton("Btn_Back", leftPanel.transform, "返回选择治疗", 60);

        GameObject gridPanel = new GameObject("DirectionalGrid");
        gridPanel.transform.SetParent(leftPanel.transform, false);
        gridPanel.AddComponent<LayoutElement>().minHeight = 160;
        GridLayoutGroup glg = gridPanel.AddComponent<GridLayoutGroup>();
        // 适当拉宽方向键，避免太方正
        glg.cellSize = new Vector2(110, 70); 
        glg.spacing = new Vector2(10, 10);
        glg.constraint = GridLayoutGroup.Constraint.FixedColumnCount; glg.constraintCount = 2;

        CreateButton("Btn_Up", gridPanel.transform, "上", 70);
        CreateButton("Btn_Left", gridPanel.transform, "左", 70);
        CreateButton("Btn_Down", gridPanel.transform, "下", 70);
        CreateButton("Btn_Right", gridPanel.transform, "右", 70);

        CreateButton("Btn_Calib", leftPanel.transform, "点击进行视盘标定", 60);
        CreateButton("Btn_Focus", leftPanel.transform, "调焦 (拉动)", 60);
        CreateButton("Btn_Reset", leftPanel.transform, "重置图像", 60);
    }

    private static void BuildCenterViewport(Transform parent, RenderTexture rt)
    {
        GameObject centerView = new GameObject("CenterViewport");
        centerView.transform.SetParent(parent, false);
        RectTransform centerRect = centerView.AddComponent<RectTransform>();
        centerRect.anchorMin = new Vector2(0.15f, 0); centerRect.anchorMax = new Vector2(0.75f, 1);
        centerRect.offsetMin = centerRect.offsetMax = Vector2.zero;
        centerView.AddComponent<RawImage>().texture = rt;

        GameObject viewLabel = new GameObject("Label");
        viewLabel.transform.SetParent(centerView.transform, false);
        Text vTxt = viewLabel.AddComponent<Text>();
        vTxt.text = "视野区 (接收射线检测)";
        vTxt.alignment = TextAnchor.MiddleCenter; vTxt.color = new Color(1,1,1,0.5f);
        vTxt.font = _legacyFont; vTxt.fontSize = 32;
        RectTransform vTxtRect = viewLabel.GetComponent<RectTransform>();
        vTxtRect.anchorMin = Vector2.zero; vTxtRect.anchorMax = Vector2.one;
        vTxtRect.offsetMin = vTxtRect.offsetMax = Vector2.zero;
    }

    private static void BuildRightControlPanel(Transform parent)
    {
        GameObject rightPanel = new GameObject("RightPanel");
        rightPanel.transform.SetParent(parent, false);
        RectTransform rightRect = rightPanel.AddComponent<RectTransform>();
        rightRect.anchorMin = new Vector2(0.75f, 0); rightRect.anchorMax = new Vector2(1f, 1);
        rightRect.offsetMin = rightRect.offsetMax = Vector2.zero;
        rightPanel.AddComponent<Image>().color = _panelBgColor;

        VerticalLayoutGroup vlg = rightPanel.AddComponent<VerticalLayoutGroup>();
        vlg.childForceExpandHeight = false; vlg.childControlHeight = true;
        vlg.spacing = 15; vlg.padding = new RectOffset(30, 30, 50, 50);

        // 1. 任务信息区
        CreateText("Lbl_TaskInfo", rightPanel.transform, "任务 ID: 未知\n已击发: 0 点", 60, true);
        CreateToggle("Chk_Trial", rightPanel.transform, "当前为试打模式");

        CreateDivider(rightPanel.transform);

        // 2. 激光参数设定区
        CreateText("Lbl_ParamsTitle", rightPanel.transform, "--- 激光参数设定 ---", 30, true);
        
        CreateSlider("Slider_Power", rightPanel.transform, "功率 (P): 200 mW", 50, 400, 200);
        CreateSlider("Slider_Spot", rightPanel.transform, "设定光斑 (S): 200 μm", 50, 400, 200);
        CreateSlider("Slider_Duration", rightPanel.transform, "曝光时间 (T): 100 ms", 10, 500, 100);
        
        CreateDropdown("Drop_Wave", rightPanel.transform, "波长 (λ):", new List<string> { "532 (Green)", "672 (Red)" });

        CreateDivider(rightPanel.transform);

        // 3. 系统焦点与结束
        CreateText("Lbl_Focus", rightPanel.transform, "系统焦段 (Z): 0.0\n当前比例: 1px = ? μm", 60, false);
        
        // 【已修改】结束治疗按钮，换用稍柔和的红色，文字设为纯白
        CreateButton("Btn_EndTreatment", rightPanel.transform, "结束治疗", 60, new Color(0.85f, 0.4f, 0.4f), Color.white); 
    }

    // =========================================================
    // 基础控件工厂函数 (已全面升级视觉效果)
    // =========================================================

    private static void CreateButton(string objName, Transform parent, string text, float height, Color? bgColor = null, Color? txtColor = null)
    {
        GameObject btnObj = new GameObject(objName);
        btnObj.transform.SetParent(parent, false);
        
        // 【升级】使用 Unity 标准的圆角切片贴图
        Image img = btnObj.AddComponent<Image>();
        img.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
        img.type = Image.Type.Sliced;
        // 默认背景改为纯白，使其与右侧控件风格一致
        img.color = bgColor ?? Color.white; 

        btnObj.AddComponent<Button>();
        btnObj.AddComponent<LayoutElement>().minHeight = height;

        GameObject textObj = new GameObject("Text");
        textObj.transform.SetParent(btnObj.transform, false);
        Text txt = textObj.AddComponent<Text>();
        txt.text = text; txt.alignment = TextAnchor.MiddleCenter;
        
        // 默认文字颜色改为深灰
        txt.color = txtColor ?? _darkTextColor; 
        txt.font = _legacyFont; 
        
        // 【升级】开启文本自适应缩放，彻底解决“返回选择治疗”换行问题
        txt.resizeTextForBestFit = true;
        txt.resizeTextMinSize = 14;
        txt.resizeTextMaxSize = 22;

        RectTransform txtRect = textObj.GetComponent<RectTransform>();
        txtRect.anchorMin = Vector2.zero; txtRect.anchorMax = Vector2.one;
        // 增加内边距，防止文本贴合到按钮边缘
        txtRect.offsetMin = new Vector2(10, 5); 
        txtRect.offsetMax = new Vector2(-10, -5);
    }

    private static void CreateText(string objName, Transform parent, string text, float height, bool bold)
    {
        GameObject textObj = new GameObject(objName);
        textObj.transform.SetParent(parent, false);
        textObj.AddComponent<LayoutElement>().minHeight = height;
        Text txt = textObj.AddComponent<Text>();
        txt.text = text; txt.font = _legacyFont; 
        txt.fontStyle = bold ? FontStyle.Bold : FontStyle.Normal;
        txt.color = _darkTextColor; txt.fontSize = 20;
    }

    private static void CreateSlider(string objName, Transform parent, string label, float min, float max, float val)
    {
        CreateText(objName + "_Label", parent, label, 30, false);
        
        DefaultControls.Resources res = new DefaultControls.Resources();
        res.standard = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
        GameObject sliderObj = DefaultControls.CreateSlider(res);
        sliderObj.name = objName;
        sliderObj.transform.SetParent(parent, false);
        sliderObj.AddComponent<LayoutElement>().minHeight = 30;
        
        Slider s = sliderObj.GetComponent<Slider>();
        s.minValue = min; s.maxValue = max; s.value = val;
    }

    private static void CreateToggle(string objName, Transform parent, string label)
    {
        DefaultControls.Resources res = new DefaultControls.Resources();
        res.standard = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
        res.checkmark = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Checkmark.psd");
        GameObject toggleObj = DefaultControls.CreateToggle(res);
        toggleObj.name = objName;
        toggleObj.transform.SetParent(parent, false);
        toggleObj.AddComponent<LayoutElement>().minHeight = 30;
        
        FixFonts(toggleObj);
        Text t = toggleObj.GetComponentInChildren<Text>();
        t.text = label; t.color = _darkTextColor; t.fontSize = 18;
    }

    private static void CreateDropdown(string objName, Transform parent, string label, List<string> options)
    {
        CreateText(objName + "_Label", parent, label, 30, false);

        DefaultControls.Resources res = new DefaultControls.Resources();
        res.standard = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
        res.dropdown = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/DropdownArrow.psd");
        res.mask = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UIMask.psd");
        
        GameObject dropObj = DefaultControls.CreateDropdown(res);
        dropObj.name = objName;
        dropObj.transform.SetParent(parent, false);
        dropObj.AddComponent<LayoutElement>().minHeight = 40;

        Dropdown d = dropObj.GetComponent<Dropdown>();
        d.ClearOptions(); d.AddOptions(options);
        
        FixFonts(dropObj);
        foreach(var t in dropObj.GetComponentsInChildren<Text>(true)) {
            t.color = _darkTextColor; t.fontSize = 18;
        }
    }

    private static void CreateDivider(Transform parent)
    {
        GameObject div = new GameObject("Divider");
        div.transform.SetParent(parent, false);
        div.AddComponent<LayoutElement>().minHeight = 2;
        div.AddComponent<Image>().color = new Color(0, 0, 0, 0.15f); // 颜色调淡一点，更精细
    }

    private static void FixFonts(GameObject root)
    {
        Text[] texts = root.GetComponentsInChildren<Text>(true);
        foreach (Text t in texts) t.font = _legacyFont;
    }
}