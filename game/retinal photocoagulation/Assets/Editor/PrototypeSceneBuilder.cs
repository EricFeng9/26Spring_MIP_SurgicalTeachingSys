#if UNITY_EDITOR
using System.Collections.Generic;
using RetinalPrototype;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public static class PrototypeSceneBuilder
{
    private const string SceneFolder = "Assets/Scenes/Prototype";

    private static readonly Color PageBackground = new Color(0.94f, 0.95f, 0.92f, 1f);
    private static readonly Color LayerInk = new Color(0.05f, 0.07f, 0.08f, 0.08f);
    private static readonly Color LayerAccent = new Color(0.18f, 0.44f, 0.37f, 0.14f);
    private static readonly Color CardColor = new Color(1f, 1f, 1f, 0.92f);
    private static readonly Color CardStroke = new Color(0.10f, 0.14f, 0.14f, 0.18f);
    private static readonly Color TextPrimary = new Color(0.08f, 0.10f, 0.11f, 1f);
    private static readonly Color TextSecondary = new Color(0.18f, 0.22f, 0.24f, 0.82f);
    private static readonly Color ActionNormal = new Color(0.11f, 0.17f, 0.18f, 0.95f);
    private static readonly Color ActionHover = new Color(0.14f, 0.22f, 0.24f, 1f);
    private static readonly Color ActionPressed = new Color(0.07f, 0.11f, 0.12f, 1f);

    [MenuItem("Tools/Retinal/Create Prototype Scenes")]
    public static void CreatePrototypeScenes()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        {
            EditorUtility.DisplayDialog("Cannot Create Scenes", "请先退出 Play 模式。", "OK");
            return;
        }

        EnsureSceneFolder();

        BuildMainMenu();
        BuildSaveSelect();
        BuildDeveloperTeam();
        BuildSettings();
        BuildInGameComputer();
        BuildDesktop();
        BuildGuidance(PrototypeSceneNames.GuidanceDiabeticRetinopathy, "糖尿病视网膜病变");
        BuildGuidance(PrototypeSceneNames.GuidanceRetinalVeinOcclusion, "视网膜静脉阻塞");
        BuildGuidance(PrototypeSceneNames.GuidanceRetinalTear, "视网膜裂孔");
        BuildGuidance(PrototypeSceneNames.GuidanceMacularEdema, "黄斑水肿");
        BuildHistoryRecords();
        BuildOrderPlatform();
        BuildSurgerySimulation();
        BuildLaserParameterUI();
        BuildSurgicalFieldView();
        BuildFundusImaging();
        BuildSpotSimulation();
        BuildTreatmentReport();
        BuildDeviceAndPatient();

        UpdateBuildSettings();
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        EditorUtility.DisplayDialog(
            "Prototype Ready",
            "所有页面已重构为统一极简风格。请直接 Play 预览。",
            "OK");
    }

    [MenuItem("Tools/Retinal/Create Prototype Scenes", true)]
    private static bool ValidateCreatePrototypeScenes()
    {
        return !EditorApplication.isPlayingOrWillChangePlaymode;
    }

    private static void BuildMainMenu()
    {
        var scene = NewStyledScene(PrototypeSceneNames.MainMenu, "Retinal Photocoagulation", "极简临床训练原型", out var canvasRoot);
        var menu = CreateMenuPanel(canvasRoot, new Vector2(-430f, -20f), new Vector2(520f, 470f));

        var flow = canvasRoot.gameObject.AddComponent<MainMenuFlowController>();
        var status = CreateText(canvasRoot, "StatusText", string.Empty, 24, TextAnchor.MiddleLeft, new Vector2(-430f, -280f), new Vector2(0.45f, 0.08f), TextSecondary);
        AssignSerializedObjectReference(flow, "statusText", status);

        var newGame = CreateButton(menu, "新游戏");
        UnityEventTools.AddPersistentListener(newGame.onClick, flow.StartNewGame);

        var continueGame = CreateButton(menu, "继续游戏");
        UnityEventTools.AddPersistentListener(continueGame.onClick, flow.ContinueGame);

        CreateSceneButton(menu, "开发团队", PrototypeSceneNames.DevTeam);
        CreateSceneButton(menu, "设置", PrototypeSceneNames.Settings);

        SaveScene(scene, PrototypeSceneNames.MainMenu);
    }

    private static void BuildSaveSelect()
    {
        var scene = NewStyledScene(PrototypeSceneNames.SaveSelect, "选择存档", "从 3 个槽位中继续或开始", out var canvasRoot);
        var menu = CreateMenuPanel(canvasRoot, new Vector2(-350f, -10f), new Vector2(620f, 560f));

        for (var i = 1; i <= PrototypeSaveSystem.SlotCount; i++)
        {
            var button = CreateButton(menu, string.Empty);
            var label = button.GetComponentInChildren<Text>();
            var saveSlotButton = button.gameObject.AddComponent<SaveSlotButton>();
            saveSlotButton.Configure(i, PrototypeSceneNames.InGameComputer, label);
            UnityEventTools.AddPersistentListener(button.onClick, saveSlotButton.OnClickSelectSlot);
        }

        CreateSceneButton(menu, "返回主菜单", PrototypeSceneNames.MainMenu);
        SaveScene(scene, PrototypeSceneNames.SaveSelect);
    }

    private static void BuildDeveloperTeam()
    {
        var scene = NewStyledScene(PrototypeSceneNames.DevTeam, "开发团队", "本页展示角色分工与版本方向", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "视觉与交互：极简信息表达",
                "场景系统：一键自动生成",
                "模拟逻辑：参数驱动光斑反馈"
            },
            new[] { new NavSpec("返回主菜单", PrototypeSceneNames.MainMenu) });
        SaveScene(scene, PrototypeSceneNames.DevTeam);
    }

    private static void BuildSettings()
    {
        var scene = NewStyledScene(PrototypeSceneNames.Settings, "设置", "训练体验与显示偏好", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "交互速度：标准 / 精细",
                "界面缩放：自动适配分辨率",
                "渲染反馈：高对比度可视化"
            },
            new[] { new NavSpec("返回主菜单", PrototypeSceneNames.MainMenu) });
        SaveScene(scene, PrototypeSceneNames.Settings);
    }

    private static void BuildInGameComputer()
    {
        var scene = NewStyledScene(PrototypeSceneNames.InGameComputer, "游戏内电脑", "信息中枢", out var canvasRoot);
        var menu = CreateMenuPanel(canvasRoot, new Vector2(-470f, -10f), new Vector2(500f, 620f));

        CreateSceneButton(menu, "电脑桌面", PrototypeSceneNames.Desktop);
        CreateSceneButton(menu, "历史诊疗记录", PrototypeSceneNames.HistoryRecords);
        CreateSceneButton(menu, "接单平台", PrototypeSceneNames.OrderPlatform);
        CreateSceneButton(menu, "进入光凝术模拟", PrototypeSceneNames.SurgerySimulation);
        CreateSceneButton(menu, "返回主菜单", PrototypeSceneNames.MainMenu);

        SaveScene(scene, PrototypeSceneNames.InGameComputer);
    }

    private static void BuildDesktop()
    {
        var scene = NewStyledScene(PrototypeSceneNames.Desktop, "电脑桌面", "任务入口一屏聚合", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "病例管理",
                "手术模拟",
                "报告中心"
            },
            new[] { new NavSpec("返回游戏内电脑", PrototypeSceneNames.InGameComputer) });
        SaveScene(scene, PrototypeSceneNames.Desktop);
    }

    private static void BuildGuidance(string sceneName, string diseaseName)
    {
        var scene = NewStyledScene(sceneName, "指导性训练", diseaseName, out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "步骤 1：识别病灶区域",
                "步骤 2：设定激光参数",
                "步骤 3：执行与复盘"
            },
            new[]
            {
                new NavSpec("返回游戏内电脑", PrototypeSceneNames.InGameComputer),
                new NavSpec("进入光凝术模拟", PrototypeSceneNames.SurgerySimulation)
            });
        SaveScene(scene, sceneName);
    }

    private static void BuildHistoryRecords()
    {
        var scene = NewStyledScene(PrototypeSceneNames.HistoryRecords, "历史诊疗记录", "病例轨迹可追溯", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "病例 DR-01 | 评分 82",
                "病例 RVO-02 | 评分 88",
                "病例 RT-03 | 评分 79"
            },
            new[] { new NavSpec("返回游戏内电脑", PrototypeSceneNames.InGameComputer) });
        SaveScene(scene, PrototypeSceneNames.HistoryRecords);
    }

    private static void BuildOrderPlatform()
    {
        var scene = NewStyledScene(PrototypeSceneNames.OrderPlatform, "接单平台", "待处理任务队列", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "工单 #001 糖网病 轻度",
                "工单 #002 视网膜静脉阻塞",
                "工单 #003 黄斑水肿"
            },
            new[]
            {
                new NavSpec("返回游戏内电脑", PrototypeSceneNames.InGameComputer),
                new NavSpec("进入光凝术模拟", PrototypeSceneNames.SurgerySimulation)
            });
        SaveScene(scene, PrototypeSceneNames.OrderPlatform);
    }

    private static void BuildSurgerySimulation()
    {
        var scene = NewStyledScene(PrototypeSceneNames.SurgerySimulation, "光凝术模拟", "参数驱动 + 眼底点击反馈", out var canvasRoot);

        var viewportCard = CreateCard(canvasRoot, "FundusViewport", new Vector2(0f, -8f), new Vector2(1760f, 900f));

        var fundusImageObject = new GameObject("FundusImage", typeof(RectTransform), typeof(RawImage), typeof(AspectRatioFitter));
        fundusImageObject.transform.SetParent(viewportCard, false);
        var fundusRect = fundusImageObject.GetComponent<RectTransform>();
        fundusRect.anchorMin = new Vector2(0.5f, 0.52f);
        fundusRect.anchorMax = new Vector2(0.5f, 0.52f);
        fundusRect.pivot = new Vector2(0.5f, 0.5f);
        fundusRect.sizeDelta = new Vector2(1640f, 860f);

        var fundusImage = fundusImageObject.GetComponent<RawImage>();
        fundusImage.color = Color.white;
        var fitter = fundusImageObject.GetComponent<AspectRatioFitter>();
        fitter.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
        fitter.aspectRatio = 1f;

        CreateText(viewportCard, "Tip", "点击眼底图以渲染光斑", 24, TextAnchor.MiddleCenter, new Vector2(0f, -404f), new Vector2(0.8f, 0.08f), TextSecondary);

        var statusBar = CreateCard(canvasRoot, "StatusBar", new Vector2(0f, -500f), new Vector2(1760f, 60f));
        var statusText = CreateText(statusBar, "LaserStatusText", "准备就绪", 22, TextAnchor.MiddleCenter, new Vector2(0f, 0f), new Vector2(0.90f, 0.06f), TextSecondary);

        var panelRect = CreateCard(canvasRoot, "LaserControlPanel", new Vector2(760f, 140f), new Vector2(520f, 620f));
        panelRect.pivot = new Vector2(1f, 1f);
        panelRect.anchorMin = new Vector2(1f, 1f);
        panelRect.anchorMax = new Vector2(1f, 1f);
        panelRect.anchoredPosition = new Vector2(-24f, -24f);

        var panelController = panelRect.gameObject.AddComponent<SurgeryLaserControlPanelController>();
        CreateText(panelRect, "PanelTitle", "参数面板", 30, TextAnchor.MiddleLeft, new Vector2(-140f, 250f), new Vector2(0.62f, 0.08f), TextPrimary);

        var closeButton = CreateAnchoredButton(panelRect, "ClosePanelButton", "x", new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(42f, 42f), new Vector2(-14f, -14f), 22);
        closeButton.GetComponent<Image>().color = new Color(0.2f, 0.24f, 0.25f, 0.95f);

        var content = new GameObject("PanelContent", typeof(RectTransform), typeof(VerticalLayoutGroup));
        content.transform.SetParent(panelRect, false);
        var contentRect = content.GetComponent<RectTransform>();
        contentRect.anchorMin = new Vector2(0f, 0f);
        contentRect.anchorMax = new Vector2(1f, 1f);
        contentRect.offsetMin = new Vector2(20f, 90f);
        contentRect.offsetMax = new Vector2(-20f, -70f);

        var contentLayout = content.GetComponent<VerticalLayoutGroup>();
        contentLayout.spacing = 12f;
        contentLayout.padding = new RectOffset(0, 0, 0, 0);
        contentLayout.childControlHeight = true;
        contentLayout.childControlWidth = true;
        contentLayout.childForceExpandHeight = false;
        contentLayout.childForceExpandWidth = true;

        var wavelengthText = CreateAdjustRow(content.transform, "波长", "<", ">", out var prevWave, out var nextWave);
        var powerText = CreateAdjustRow(content.transform, "功率", "-", "+", out var powerMinus, out var powerPlus);
        var durationText = CreateAdjustRow(content.transform, "时长", "-", "+", out var durationMinus, out var durationPlus);
        var diameterText = CreateAdjustRow(content.transform, "光斑直径", "-", "+", out var diameterMinus, out var diameterPlus);

        var bottomBar = new GameObject("BottomBar", typeof(RectTransform), typeof(Image), typeof(HorizontalLayoutGroup));
        bottomBar.transform.SetParent(canvasRoot, false);
        var bottomRect = bottomBar.GetComponent<RectTransform>();
        bottomRect.anchorMin = new Vector2(0.5f, 0f);
        bottomRect.anchorMax = new Vector2(0.5f, 0f);
        bottomRect.pivot = new Vector2(0.5f, 0f);
        bottomRect.sizeDelta = new Vector2(1760f, 56f);
        bottomRect.anchoredPosition = new Vector2(0f, 8f);
        bottomBar.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.90f);

        var bottomLayout = bottomBar.GetComponent<HorizontalLayoutGroup>();
        bottomLayout.spacing = 8f;
        bottomLayout.padding = new RectOffset(10, 10, 6, 6);
        bottomLayout.childControlWidth = false;
        bottomLayout.childControlHeight = true;
        bottomLayout.childForceExpandWidth = false;
        bottomLayout.childForceExpandHeight = false;

        var backButton = CreateInlineActionButton(bottomBar.transform, "返回", 88f);
        var reportButton = CreateInlineActionButton(bottomBar.transform, "报告", 88f);
        var toggleButton = CreateInlineActionButton(bottomBar.transform, "参数", 88f);
        var loadButton = CreateInlineActionButton(bottomBar.transform, "加载", 88f);
        var resetButton = CreateInlineActionButton(bottomBar.transform, "重置", 88f);
        var calibrateButton = CreateInlineActionButton(bottomBar.transform, "视盘标定", 118f);
        var slitToggleButton = CreateInlineActionButton(bottomBar.transform, "镜子开关", 106f);
        var slitLeftButton = CreateInlineActionButton(bottomBar.transform, "镜左", 70f);
        var slitRightButton = CreateInlineActionButton(bottomBar.transform, "镜右", 70f);
        var aimDotToggleButton = CreateInlineActionButton(bottomBar.transform, "红点开关", 106f);
        var flashToggleButton = CreateInlineActionButton(bottomBar.transform, "闪光开关", 106f);

        panelController.Configure(panelRect.gameObject, wavelengthText, powerText, durationText, diameterText);

        UnityEventTools.AddPersistentListener(toggleButton.onClick, panelController.TogglePanel);
        UnityEventTools.AddPersistentListener(closeButton.onClick, panelController.ClosePanel);
        UnityEventTools.AddPersistentListener(prevWave.onClick, panelController.PreviousWavelength);
        UnityEventTools.AddPersistentListener(nextWave.onClick, panelController.NextWavelength);
        UnityEventTools.AddPersistentListener(powerMinus.onClick, panelController.DecreasePower);
        UnityEventTools.AddPersistentListener(powerPlus.onClick, panelController.IncreasePower);
        UnityEventTools.AddPersistentListener(durationMinus.onClick, panelController.DecreaseDuration);
        UnityEventTools.AddPersistentListener(durationPlus.onClick, panelController.IncreaseDuration);
        UnityEventTools.AddPersistentListener(diameterMinus.onClick, panelController.DecreaseDiameter);
        UnityEventTools.AddPersistentListener(diameterPlus.onClick, panelController.IncreaseDiameter);

        var rendererHost = new GameObject("SurgeryLaserSpotRenderer", typeof(SurgeryLaserSpotRenderer));
        rendererHost.transform.SetParent(canvasRoot, false);
        var renderer = rendererHost.GetComponent<SurgeryLaserSpotRenderer>();
        AssignSerializedObjectReference(renderer, "fundusImage", fundusImage);
        AssignSerializedObjectReference(renderer, "controlPanel", panelController);
        AssignSerializedObjectReference(renderer, "statusText", statusText);

        var backLoader = backButton.gameObject.AddComponent<SceneLoadButton>();
        backLoader.SetTargetScene(PrototypeSceneNames.InGameComputer);
        UnityEventTools.AddPersistentListener(backButton.onClick, backLoader.LoadTargetScene);

        var reportLoader = reportButton.gameObject.AddComponent<SceneLoadButton>();
        reportLoader.SetTargetScene(PrototypeSceneNames.TreatmentReport);
        UnityEventTools.AddPersistentListener(reportButton.onClick, reportLoader.LoadTargetScene);

        UnityEventTools.AddPersistentListener(loadButton.onClick, renderer.ReloadFundusImage);
        UnityEventTools.AddPersistentListener(resetButton.onClick, renderer.ResetRenderedSpots);
        UnityEventTools.AddPersistentListener(calibrateButton.onClick, renderer.BeginOpticDiscCalibration);
        UnityEventTools.AddPersistentListener(slitToggleButton.onClick, renderer.ToggleSlitLens);
        UnityEventTools.AddPersistentListener(slitLeftButton.onClick, renderer.MoveSlitLensLeft);
        UnityEventTools.AddPersistentListener(slitRightButton.onClick, renderer.MoveSlitLensRight);
        UnityEventTools.AddPersistentListener(aimDotToggleButton.onClick, renderer.ToggleAimDot);
        UnityEventTools.AddPersistentListener(flashToggleButton.onClick, renderer.ToggleFlashEffect);

        SaveScene(scene, PrototypeSceneNames.SurgerySimulation);
    }

    private static void BuildLaserParameterUI()
    {
        var scene = NewStyledScene(PrototypeSceneNames.LaserParameterUI, "激光参数 UI", "参数含义预览页", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "功率：决定单次能量输出",
                "时长：决定能量累积",
                "光斑直径：决定作用面积"
            },
            new[] { new NavSpec("返回光凝术模拟", PrototypeSceneNames.SurgerySimulation) });
        SaveScene(scene, PrototypeSceneNames.LaserParameterUI);
    }

    private static void BuildSurgicalFieldView()
    {
        var scene = NewStyledScene(PrototypeSceneNames.SurgicalFieldView, "手术视野", "术中观察层", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "中心焦点区域",
                "边缘病灶高亮",
                "操作轨迹回放"
            },
            new[] { new NavSpec("返回光凝术模拟", PrototypeSceneNames.SurgerySimulation) });
        SaveScene(scene, PrototypeSceneNames.SurgicalFieldView);
    }

    private static void BuildFundusImaging()
    {
        var scene = NewStyledScene(PrototypeSceneNames.FundusImaging, "眼底成像", "采集与预览", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "采集参数：曝光 / 对焦",
                "预览结果：病灶可见性",
                "存档关联：病例时间轴"
            },
            new[] { new NavSpec("返回光凝术模拟", PrototypeSceneNames.SurgerySimulation) });
        SaveScene(scene, PrototypeSceneNames.FundusImaging);
    }

    private static void BuildSpotSimulation()
    {
        var scene = NewStyledScene(PrototypeSceneNames.SpotSimulation, "光斑模拟", "参数变化效果比较", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "低参数：作用浅、范围小",
                "中参数：标准治疗区",
                "高参数：需避免过度灼伤"
            },
            new[] { new NavSpec("返回光凝术模拟", PrototypeSceneNames.SurgerySimulation) });
        SaveScene(scene, PrototypeSceneNames.SpotSimulation);
    }

    private static void BuildTreatmentReport()
    {
        var scene = NewStyledScene(PrototypeSceneNames.TreatmentReport, "诊疗报告以及得分", "结果复盘", out var canvasRoot);

        var reportCard = CreateCard(canvasRoot, "ReportCard", new Vector2(-150f, -20f), new Vector2(980f, 560f));
        CreateText(reportCard, "CaseName", "病例 DR-Case-01", 34, TextAnchor.MiddleLeft, new Vector2(-360f, 170f), new Vector2(0.72f, 0.1f), TextPrimary);
        CreateText(reportCard, "ParamSummary", "参数：220mW / 150ms / 120um", 28, TextAnchor.MiddleLeft, new Vector2(-360f, 90f), new Vector2(0.72f, 0.1f), TextSecondary);
        CreateText(reportCard, "Score", "总分 82 / 100", 54, TextAnchor.MiddleLeft, new Vector2(-360f, -20f), new Vector2(0.72f, 0.12f), new Color(0.09f, 0.35f, 0.26f, 1f));
        CreateText(reportCard, "Advice", "建议：降低时长并适度缩小光斑直径以提升精准度。", 24, TextAnchor.MiddleLeft, new Vector2(-360f, -120f), new Vector2(0.82f, 0.09f), TextSecondary);

        var menu = CreateMenuPanel(canvasRoot, new Vector2(640f, -20f), new Vector2(320f, 260f));
        CreateSceneButton(menu, "返回游戏内电脑", PrototypeSceneNames.InGameComputer);
        CreateSceneButton(menu, "返回主菜单", PrototypeSceneNames.MainMenu);

        SaveScene(scene, PrototypeSceneNames.TreatmentReport);
    }

    private static void BuildDeviceAndPatient()
    {
        var scene = NewStyledScene(PrototypeSceneNames.DeviceAndPatient, "仪器与受试患者", "结构展示页", out var canvasRoot);
        BuildStandardInfoPage(canvasRoot,
            new[]
            {
                "设备模块：激光源 / 控制台 / 光路",
                "患者模型：体位与眼位基准",
                "安全项：照射阈值提示"
            },
            new[]
            {
                new NavSpec("返回主菜单", PrototypeSceneNames.MainMenu),
                new NavSpec("返回游戏内电脑", PrototypeSceneNames.InGameComputer)
            });
        SaveScene(scene, PrototypeSceneNames.DeviceAndPatient);
    }

    private static void BuildStandardInfoPage(RectTransform canvasRoot, string[] lines, NavSpec[] navs)
    {
        CreateCard(canvasRoot, "InfoCard", new Vector2(-120f, -10f), new Vector2(980f, 540f));

        var menu = CreateMenuPanel(canvasRoot, new Vector2(650f, -20f), new Vector2(320f, 380f));
        foreach (var nav in navs)
        {
            CreateSceneButton(menu, nav.Label, nav.TargetScene);
        }
    }

    private static Scene NewStyledScene(string sceneName, string title, string subtitle, out RectTransform canvasRoot)
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
        ConfigureCameraAndLight();

        canvasRoot = CreateCanvas();
        CreateBackground(canvasRoot);

        CreateText(canvasRoot, "Title", title, 64, TextAnchor.MiddleLeft, new Vector2(-740f, 430f), new Vector2(0.7f, 0.11f), TextPrimary);
        CreateText(canvasRoot, "Subtitle", subtitle, 28, TextAnchor.MiddleLeft, new Vector2(-740f, 375f), new Vector2(0.7f, 0.08f), TextSecondary);

        return scene;
    }

    private static void ConfigureCameraAndLight()
    {
        var camera = Camera.main;
        if (camera != null)
        {
            camera.transform.position = new Vector3(0f, 1.2f, -10f);
            camera.transform.rotation = Quaternion.Euler(3f, 0f, 0f);
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.88f, 0.90f, 0.87f, 1f);
        }

        var lightObject = GameObject.Find("Directional Light");
        if (lightObject == null)
        {
            lightObject = new GameObject("Directional Light");
            lightObject.AddComponent<Light>();
        }

        var light = lightObject.GetComponent<Light>();
        light.type = LightType.Directional;
        light.intensity = 0.9f;
        light.color = Color.white;
        lightObject.transform.rotation = Quaternion.Euler(45f, -35f, 0f);
    }

    private static RectTransform CreateCanvas()
    {
        var canvasObject = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        var canvas = canvasObject.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;

        var scaler = canvasObject.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920f, 1080f);
        scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
        scaler.matchWidthOrHeight = 0.5f;

        if (Object.FindFirstObjectByType<EventSystem>() == null)
        {
            new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
        }

        return canvasObject.GetComponent<RectTransform>();
    }

    private static void CreateBackground(RectTransform canvasRoot)
    {
        var fill = new GameObject("Background", typeof(RectTransform), typeof(Image));
        fill.transform.SetParent(canvasRoot, false);
        var fillRect = fill.GetComponent<RectTransform>();
        fillRect.anchorMin = Vector2.zero;
        fillRect.anchorMax = Vector2.one;
        fillRect.offsetMin = Vector2.zero;
        fillRect.offsetMax = Vector2.zero;
        var fillImage = fill.GetComponent<Image>();
        fillImage.color = PageBackground;
        fillImage.raycastTarget = false;
        fill.transform.SetAsFirstSibling();

        CreateBlob(canvasRoot, "Blob1", new Vector2(-520f, 260f), new Vector2(640f, 640f), LayerAccent);
        CreateBlob(canvasRoot, "Blob2", new Vector2(620f, -180f), new Vector2(720f, 720f), LayerInk);
        CreateBlob(canvasRoot, "Blob3", new Vector2(220f, 330f), new Vector2(380f, 380f), new Color(0.86f, 0.89f, 0.84f, 0.9f));
    }

    private static void CreateBlob(RectTransform parent, string name, Vector2 position, Vector2 size, Color color)
    {
        var blob = new GameObject(name, typeof(RectTransform), typeof(Image));
        blob.transform.SetParent(parent, false);
        var rect = blob.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.5f, 0.5f);
        rect.anchorMax = new Vector2(0.5f, 0.5f);
        rect.pivot = new Vector2(0.5f, 0.5f);
        rect.anchoredPosition = position;
        rect.sizeDelta = size;

        var image = blob.GetComponent<Image>();
        image.color = color;
        image.raycastTarget = false;
    }

    private static RectTransform CreateMenuPanel(RectTransform parent, Vector2 position, Vector2 size)
    {
        var panel = CreateCard(parent, "MenuPanel", position, size);
        var layout = panel.gameObject.AddComponent<VerticalLayoutGroup>();
        layout.spacing = 10f;
        layout.padding = new RectOffset(16, 16, 16, 16);
        layout.childControlHeight = true;
        layout.childControlWidth = true;
        layout.childForceExpandHeight = false;
        layout.childForceExpandWidth = true;

        // Keep menu above decorative cards so buttons remain visible/clickable.
        panel.SetAsLastSibling();
        return panel;
    }

    private static RectTransform CreateCard(RectTransform parent, string name, Vector2 position, Vector2 size)
    {
        var card = new GameObject(name, typeof(RectTransform), typeof(Image), typeof(Shadow), typeof(Outline));
        card.transform.SetParent(parent, false);

        var rect = card.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.5f, 0.5f);
        rect.anchorMax = new Vector2(0.5f, 0.5f);
        rect.pivot = new Vector2(0.5f, 0.5f);
        rect.anchoredPosition = position;
        rect.sizeDelta = size;

        var image = card.GetComponent<Image>();
        image.color = CardColor;

        var shadow = card.GetComponent<Shadow>();
        shadow.effectColor = new Color(0f, 0f, 0f, 0.18f);
        shadow.effectDistance = new Vector2(0f, -8f);

        var outline = card.GetComponent<Outline>();
        outline.effectColor = CardStroke;
        outline.effectDistance = new Vector2(1f, -1f);

        return rect;
    }

    private static void CreateHeroCard(RectTransform parent, string title, string body, Vector2 position, Vector2 size)
    {
        var card = CreateCard(parent, "HeroCard", position, size);
        CreateText(card, "HeroTitle", title, 36, TextAnchor.MiddleLeft, new Vector2(-220f, 0f), new Vector2(0.75f, 0.12f), TextSecondary);
    }

    private static Button CreateButton(Transform parent, string label)
    {
        var buttonObject = new GameObject("Button_" + label, typeof(RectTransform), typeof(Image), typeof(Button), typeof(LayoutElement));
        buttonObject.transform.SetParent(parent, false);

        var image = buttonObject.GetComponent<Image>();
        image.color = ActionNormal;

        var button = buttonObject.GetComponent<Button>();
        button.transition = Selectable.Transition.ColorTint;
        button.navigation = new Navigation { mode = Navigation.Mode.None };

        var colors = button.colors;
        colors.normalColor = ActionNormal;
        colors.highlightedColor = ActionHover;
        colors.pressedColor = ActionPressed;
        colors.selectedColor = ActionHover;
        colors.disabledColor = new Color(0.35f, 0.38f, 0.39f, 0.5f);
        colors.colorMultiplier = 1f;
        colors.fadeDuration = 0.08f;
        button.colors = colors;

        var layout = buttonObject.GetComponent<LayoutElement>();
        layout.minWidth = 0f;
        layout.preferredWidth = 0f;
        layout.flexibleWidth = 1f;
        layout.minHeight = 62f;
        layout.preferredHeight = 62f;

        var textObject = new GameObject("Label", typeof(RectTransform), typeof(Text));
        textObject.transform.SetParent(buttonObject.transform, false);
        var textRect = textObject.GetComponent<RectTransform>();
        textRect.anchorMin = Vector2.zero;
        textRect.anchorMax = Vector2.one;
        textRect.offsetMin = new Vector2(14f, 0f);
        textRect.offsetMax = new Vector2(-14f, 0f);

        var text = textObject.GetComponent<Text>();
        text.text = label;
        text.font = GetBuiltinFont();
        text.fontSize = 24;
        text.color = Color.white;
        text.alignment = TextAnchor.MiddleCenter;
        text.raycastTarget = false;

        return button;
    }

    private static Button CreateAnchoredButton(
        RectTransform parent,
        string objectName,
        string label,
        Vector2 anchorMin,
        Vector2 anchorMax,
        Vector2 size,
        Vector2 anchoredPosition,
        int fontSize)
    {
        var buttonObject = new GameObject(objectName, typeof(RectTransform), typeof(Image), typeof(Button), typeof(Shadow));
        buttonObject.transform.SetParent(parent, false);

        var rect = buttonObject.GetComponent<RectTransform>();
        rect.anchorMin = anchorMin;
        rect.anchorMax = anchorMax;
        rect.pivot = anchorMax;
        rect.sizeDelta = size;
        rect.anchoredPosition = anchoredPosition;

        var image = buttonObject.GetComponent<Image>();
        image.color = ActionNormal;

        var shadow = buttonObject.GetComponent<Shadow>();
        shadow.effectColor = new Color(0f, 0f, 0f, 0.2f);
        shadow.effectDistance = new Vector2(0f, -3f);

        var textObject = new GameObject("Label", typeof(RectTransform), typeof(Text));
        textObject.transform.SetParent(buttonObject.transform, false);
        var textRect = textObject.GetComponent<RectTransform>();
        textRect.anchorMin = Vector2.zero;
        textRect.anchorMax = Vector2.one;
        textRect.offsetMin = Vector2.zero;
        textRect.offsetMax = Vector2.zero;

        var text = textObject.GetComponent<Text>();
        text.text = label;
        text.font = GetBuiltinFont();
        text.fontSize = fontSize;
        text.color = Color.white;
        text.alignment = TextAnchor.MiddleCenter;
        text.raycastTarget = false;

        var button = buttonObject.GetComponent<Button>();
        var colors = button.colors;
        colors.normalColor = ActionNormal;
        colors.highlightedColor = ActionHover;
        colors.pressedColor = ActionPressed;
        colors.selectedColor = ActionHover;
        button.colors = colors;
        button.navigation = new Navigation { mode = Navigation.Mode.None };

        return button;
    }

    private static Button CreateInlineActionButton(Transform parent, string label, float width)
    {
        var button = CreateButton(parent, label);
        var layout = button.GetComponent<LayoutElement>();
        layout.preferredWidth = width;
        layout.minHeight = 50f;
        layout.preferredHeight = 50f;

        var text = button.GetComponentInChildren<Text>();
        text.fontSize = 20;
        return button;
    }

    private static Text CreateAdjustRow(
        Transform parent,
        string label,
        string leftButtonLabel,
        string rightButtonLabel,
        out Button leftButton,
        out Button rightButton)
    {
        var row = new GameObject("Row_" + label, typeof(RectTransform), typeof(Image), typeof(HorizontalLayoutGroup), typeof(LayoutElement));
        row.transform.SetParent(parent, false);

        var rowImage = row.GetComponent<Image>();
        rowImage.color = new Color(0.96f, 0.97f, 0.94f, 0.98f);

        var rowLayout = row.GetComponent<HorizontalLayoutGroup>();
        rowLayout.padding = new RectOffset(12, 12, 8, 8);
        rowLayout.spacing = 8f;
        rowLayout.childControlWidth = false;
        rowLayout.childControlHeight = true;
        rowLayout.childForceExpandWidth = false;
        rowLayout.childForceExpandHeight = false;

        var rowElement = row.GetComponent<LayoutElement>();
        rowElement.preferredHeight = 66f;

        var titleObject = new GameObject("Title", typeof(RectTransform), typeof(Text), typeof(LayoutElement));
        titleObject.transform.SetParent(row.transform, false);
        var titleLayout = titleObject.GetComponent<LayoutElement>();
        titleLayout.preferredWidth = 160f;

        var titleText = titleObject.GetComponent<Text>();
        titleText.text = label;
        titleText.font = GetBuiltinFont();
        titleText.fontSize = 24;
        titleText.color = TextPrimary;
        titleText.alignment = TextAnchor.MiddleLeft;
        titleText.raycastTarget = false;

        leftButton = CreateInlineActionButton(row.transform, leftButtonLabel, 46f);

        var valueObject = new GameObject("Value", typeof(RectTransform), typeof(Text), typeof(LayoutElement));
        valueObject.transform.SetParent(row.transform, false);
        var valueLayout = valueObject.GetComponent<LayoutElement>();
        valueLayout.preferredWidth = 160f;

        var valueText = valueObject.GetComponent<Text>();
        valueText.text = "--";
        valueText.font = GetBuiltinFont();
        valueText.fontSize = 24;
        valueText.color = TextPrimary;
        valueText.alignment = TextAnchor.MiddleCenter;
        valueText.raycastTarget = false;

        rightButton = CreateInlineActionButton(row.transform, rightButtonLabel, 46f);
        return valueText;
    }

    private static Text CreateText(
        RectTransform parent,
        string objectName,
        string textValue,
        int fontSize,
        TextAnchor textAnchor,
        Vector2 anchoredPosition,
        Vector2 sizeScale,
        Color color)
    {
        var textObject = new GameObject(objectName, typeof(RectTransform), typeof(Text));
        textObject.transform.SetParent(parent, false);

        var textRect = textObject.GetComponent<RectTransform>();
        textRect.anchorMin = new Vector2(0.5f, 0.5f);
        textRect.anchorMax = new Vector2(0.5f, 0.5f);
        textRect.pivot = new Vector2(0.5f, 0.5f);
        textRect.anchoredPosition = anchoredPosition;
        textRect.sizeDelta = new Vector2(1920f * sizeScale.x, 1080f * sizeScale.y);

        var text = textObject.GetComponent<Text>();
        text.text = textValue;
        text.font = GetBuiltinFont();
        text.fontSize = fontSize;
        text.alignment = textAnchor;
        text.color = color;
        text.raycastTarget = false;

        return text;
    }

    private static void CreateSceneButton(Transform parent, string label, string targetScene)
    {
        var button = CreateButton(parent, label);
        var loadButton = button.gameObject.AddComponent<SceneLoadButton>();
        loadButton.SetTargetScene(targetScene);
        UnityEventTools.AddPersistentListener(button.onClick, loadButton.LoadTargetScene);
    }

    private static Font GetBuiltinFont()
    {
        var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        if (font != null)
        {
            return font;
        }

        return Resources.GetBuiltinResource<Font>("Arial.ttf");
    }

    private static void SaveScene(Scene scene, string sceneName)
    {
        var path = SceneFolder + "/" + sceneName + ".unity";
        EditorSceneManager.SaveScene(scene, path);
    }

    private static void EnsureSceneFolder()
    {
        if (!AssetDatabase.IsValidFolder("Assets/Scenes"))
        {
            AssetDatabase.CreateFolder("Assets", "Scenes");
        }

        if (!AssetDatabase.IsValidFolder(SceneFolder))
        {
            AssetDatabase.CreateFolder("Assets/Scenes", "Prototype");
        }
    }

    private static void AssignSerializedObjectReference(Object target, string propertyName, Object value)
    {
        var serializedObject = new SerializedObject(target);
        var property = serializedObject.FindProperty(propertyName);
        if (property == null)
        {
            Debug.LogWarning("Property not found: " + propertyName);
            return;
        }

        property.objectReferenceValue = value;
        serializedObject.ApplyModifiedPropertiesWithoutUndo();
        EditorUtility.SetDirty(target);
    }

    private static void UpdateBuildSettings()
    {
        var scenes = new List<EditorBuildSettingsScene>();
        foreach (var sceneName in PrototypeSceneNames.AllScenes)
        {
            scenes.Add(new EditorBuildSettingsScene(SceneFolder + "/" + sceneName + ".unity", true));
        }

        EditorBuildSettings.scenes = scenes.ToArray();
    }

    private readonly struct NavSpec
    {
        public NavSpec(string label, string targetScene)
        {
            Label = label;
            TargetScene = targetScene;
        }

        public string Label { get; }
        public string TargetScene { get; }
    }
}
#endif
