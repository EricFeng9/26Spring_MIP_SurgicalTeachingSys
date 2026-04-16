using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.UI;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

public static class RetinalLaserUiGenerator
{
    private const string RootName = "UI_RetinalLaserSimulator";
    private static DefaultControls.Resources _resources;

    [MenuItem("Tools/Generate/Retinal Laser Simulator UI")]
    public static void Generate()
    {
        _resources = new DefaultControls.Resources();

        var canvas = EnsureCanvas();
        EnsureEventSystem();

        var old = GameObject.Find(RootName);
        if (old != null)
        {
            Undo.DestroyObjectImmediate(old);
        }

        var root = CreateUIObject(RootName, canvas.transform);
        Stretch(root.GetComponent<RectTransform>(), 0, 0, 0, 0);

        var rootBg = root.AddComponent<Image>();
        rootBg.color = Hex("F2F4F7");

        BuildLeftArea(root.transform);
        BuildRightArea(root.transform);
        BuildMinimapPopup(root.transform);

        EditorUtility.SetDirty(root);
        Selection.activeGameObject = root;
    }

    private static Canvas EnsureCanvas()
    {
        var canvas = Object.FindObjectOfType<Canvas>();
        if (canvas != null) return canvas;

        var go = new GameObject(
            "Canvas",
            typeof(RectTransform),
            typeof(Canvas),
            typeof(CanvasScaler),
            typeof(GraphicRaycaster)
        );

        Undo.RegisterCreatedObjectUndo(go, "Create Canvas");

        canvas = go.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;

        var scaler = go.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
        scaler.matchWidthOrHeight = 0.5f;

        return canvas;
    }

    private static void EnsureEventSystem()
    {
        if (Object.FindObjectOfType<EventSystem>() != null) return;

        var go = new GameObject(
            "EventSystem",
            typeof(EventSystem),
            typeof(StandaloneInputModule)
        );

        Undo.RegisterCreatedObjectUndo(go, "Create EventSystem");
    }

    private static void BuildLeftArea(Transform parent)
    {
        var left = CreateUIObject("Panel_LeftArea", parent);
        Stretch(left.GetComponent<RectTransform>(), 12, 12, 444, 12);

        var vlg = left.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(0, 0, 0, 0);
        vlg.spacing = 8;
        vlg.childAlignment = TextAnchor.UpperLeft;
        vlg.childControlWidth = true;
        vlg.childControlHeight = true;
        vlg.childForceExpandWidth = true;
        vlg.childForceExpandHeight = false;

        var title = CreateText(
            "Text_Title_SurgicalSimulation",
            left.transform,
            "Surgical Simulation",
            18,
            FontStyle.Bold,
            TextAnchor.MiddleLeft,
            Hex("101010")
        );
        SetLayout(title, -1, 42, 0, 0);

        var toolbar = CreateHorizontalRow("Row_Toolbar", left.transform, 10, 42);
        CreateButton(toolbar.transform, "Button_UndoLast", "Undo Last", 106, 38, Hex("ECE9E2"));
        CreateButton(toolbar.transform, "Button_ClearAll", "Clear All", 106, 38, Hex("ECE9E2"));
        CreateButton(toolbar.transform, "Button_StartDiscCalibration", "Start Disc Calibration", 172, 38, Hex("ECE9E2"));
        CreateButton(toolbar.transform, "Button_ResetCalibration", "Reset Calibration", 148, 38, Hex("ECE9E2"));
        CreateButton(toolbar.transform, "Button_MiniMap", "Mini-map", 110, 38, Hex("ECE9E2"));
        CreateButton(toolbar.transform, "Button_EndSurgery", "End Surgery", 118, 38, Hex("E9E0D7"));

        var infoRow = CreateHorizontalRow("Row_InfoBar", left.transform, 10, 34);

        var timerLabel = CreateText("Text_Label_Timer", infoRow.transform, "Timer", 12, FontStyle.Normal, TextAnchor.MiddleLeft, Hex("202020"));
        SetLayout(timerLabel, 42, 28, 0, 0);

        var timerValue = CreateText("Text_Value_Timer", infoRow.transform, "00:00", 18, FontStyle.Bold, TextAnchor.MiddleLeft, Hex("111111"));
        SetLayout(timerValue, 70, 28, 0, 0);

        var sep = CreateUIObject("Separator_TimerSpots", infoRow.transform);
        var sepImg = sep.AddComponent<Image>();
        sepImg.color = Hex("C8C8C8");
        SetLayout(sep, 2, 24, 0, 0);

        var spotsLabel = CreateText("Text_Label_Spots", infoRow.transform, "Spots", 12, FontStyle.Normal, TextAnchor.MiddleLeft, Hex("202020"));
        SetLayout(spotsLabel, 42, 28, 0, 0);

        var spotsValue = CreateText("Text_Value_Spots", infoRow.transform, "0", 18, FontStyle.Bold, TextAnchor.MiddleLeft, Hex("111111"));
        SetLayout(spotsValue, 40, 28, 0, 0);

        var hint = CreateText(
            "Text_HintInteraction",
            left.transform,
            "Left click: fire current mode pattern | Right click: remove nearest | Calibration mode: click two optic-disc edge points",
            12,
            FontStyle.Normal,
            TextAnchor.MiddleLeft,
            Hex("2A2A2A")
        );
        SetLayout(hint, -1, 24, 0, 0);

        var viewportContainer = CreateUIObject("Panel_ViewportContainer", left.transform);
        var viewportLE = viewportContainer.AddComponent<LayoutElement>();
        viewportLE.flexibleHeight = 1;
        viewportLE.minHeight = 400;

        var viewportImage = viewportContainer.AddComponent<Image>();
        viewportImage.color = Hex("101418");

        var viewportOutline = viewportContainer.AddComponent<Outline>();
        viewportOutline.effectColor = Hex("2A3340");
        viewportOutline.effectDistance = new Vector2(1f, -1f);

        var fovFrame = CreateUIObject("Image_FOVCircleApprox", viewportContainer.transform);
        var fovFrameRt = fovFrame.GetComponent<RectTransform>();
        fovFrameRt.anchorMin = new Vector2(0.5f, 0.5f);
        fovFrameRt.anchorMax = new Vector2(0.5f, 0.5f);
        fovFrameRt.pivot = new Vector2(0.5f, 0.5f);
        fovFrameRt.sizeDelta = new Vector2(720, 720);

        var fovImage = fovFrame.AddComponent<Image>();
        fovImage.sprite = EnsureFovCircleSpriteAsset();
        fovImage.type = Image.Type.Simple;
        fovImage.preserveAspect = true;
        fovImage.color = Color.white;

        var fovText = CreateText(
            "Text_ViewportPlaceholder",
            fovFrame.transform,
            "Microscope FOV",
            22,
            FontStyle.Bold,
            TextAnchor.MiddleCenter,
            Hex("FFFFFF")
        );
        Stretch(fovText.GetComponent<RectTransform>(), 0, 0, 0, 0);
    }

    private static void BuildRightArea(Transform parent)
    {
        var right = CreateUIObject("Panel_RightArea", parent);
        var rt = right.GetComponent<RectTransform>();
        rt.anchorMin = new Vector2(1f, 0f);
        rt.anchorMax = new Vector2(1f, 1f);
        rt.pivot = new Vector2(1f, 0.5f);
        rt.sizeDelta = new Vector2(420, 0);
        rt.anchoredPosition = new Vector2(-12, 0);

        var vlg = right.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(0, 0, 0, 0);
        vlg.spacing = 8;
        vlg.childAlignment = TextAnchor.UpperLeft;
        vlg.childControlWidth = true;
        vlg.childControlHeight = true;
        vlg.childForceExpandWidth = true;
        vlg.childForceExpandHeight = false;

        var title = CreateText(
            "Text_Title_ControlPanel",
            right.transform,
            "Control Panel",
            18,
            FontStyle.Bold,
            TextAnchor.MiddleLeft,
            Hex("101010")
        );
        SetLayout(title, -1, 42, 0, 0);

        var singleShot = CreateSection(right.transform, "Section_SingleShotMode", "Single-Shot Mode");
        CreateDropdownField(singleShot.transform, "Field_Mode", "mode", new[] { "single", "matrix" }, 0);
        CreateDropdownField(singleShot.transform, "Field_WavelengthNm", "wavelength_nm", new[] { "532", "577", "659" }, 0);
        CreateSliderField(singleShot.transform, "Field_PowerMw", "power_mw", 50, 800, 180, "180");
        CreateSliderField(singleShot.transform, "Field_DurationMs", "duration_ms", 10, 500, 20, "20");
        CreateDropdownField(singleShot.transform, "Field_PulseMode", "pulse_mode", new[] { "single_pulse", "repeat" }, 0);
        CreateSliderField(singleShot.transform, "Field_IntervalS", "interval_s", 0.05f, 1.0f, 0.20f, "0.2");
        CreateSliderField(singleShot.transform, "Field_SpotSizeUm", "spot_size_um", 50, 800, 200, "200");
        CreateDropdownField(singleShot.transform, "Field_FundusLens", "fundus_lens", new[] { "Goldmann", "Krieger", "Panfundoscope", "Mainster" }, 0);
        CreateSliderField(singleShot.transform, "Field_AimingBeamLevel", "aiming_beam_level", 0, 100, 50, "50");
        CreateToggleField(singleShot.transform, "Field_TitrateMode", "titrate_mode", false);

        var matrix = CreateSection(right.transform, "Section_MatrixMode", "Matrix Mode");
        CreateDropdownField(matrix.transform, "Field_Shape", "shape", new[] { "square", "line", "triangle", "circle", "quarter_circle", "half_circle" }, 0);
        CreateInputFieldRow(matrix.transform, "Field_ShapeParam", "shape_param", "3");
        CreateSliderField(matrix.transform, "Field_SpacingXSpot", "spacing_x_spot", 0.25f, 3.0f, 1.0f, "1.0");
        CreateSliderField(matrix.transform, "Field_RotationDeg", "rotation_deg", -180f, 180f, 0f, "0.0");
        CreateInputFieldRow(matrix.transform, "Field_XYOffsetDx", "xy_offset_dx", "0.0");
        CreateInputFieldRow(matrix.transform, "Field_XYOffsetDy", "xy_offset_dy", "0.0");

        var calibration = CreateSection(right.transform, "Section_Calibration", "Calibration");
        CreateInputFieldRow(calibration.transform, "Field_OpticDiscUm", "optic_disc_um", "1500");

        var status = CreateSection(right.transform, "Section_Status", "Status");
        var statusInput = CreateMultilineStatus(status.transform, "InputField_StatusLog");
        SetLayout(statusInput, -1, 260, 0, 1);

        var defaultStatus = string.Join("\n", new[]
        {
            "=== Current parameter set ===",
            "mode             : single",
            "pulse_mode       : single_pulse",
            "interval_s       : 0.20",
            "Lens coeff       : 1.080",
            "Wavelength (nm)  : 532.0",
            "Spot size (µm)   : 200.0",
            "Beam on retina   : 216.0 µm",
            "Duration (ms)    : 20.0",
            "Power (mW)       : 180.0",
            "Aiming level     : 50",
            "Titrate mode     : False",
            "",
            "=== Calibration ===",
            "Scale            : not calibrated",
            "",
            "=== Matrix mode ===",
            "shape            : square",
            "shape_param      : 3",
            "spacing_x_spot   : 1.00",
            "rotation_deg     : 0.0",
            "xy_offset        : (0.0, 0.0)",
            "",
            "=== Image / lesions ===",
            "Lesion count     : 0",
        });

        var statusField = statusInput.GetComponent<InputField>();
        statusField.text = defaultStatus;
    }

    private static void BuildMinimapPopup(Transform parent)
    {
        var overlay = CreateUIObject("Popup_MinimapOverlay", parent);
        Stretch(overlay.GetComponent<RectTransform>(), 0, 0, 0, 0);

        var overlayImage = overlay.AddComponent<Image>();
        overlayImage.color = new Color(0f, 0f, 0f, 0.35f);

        var window = CreateUIObject("Window_Minimap", overlay.transform);
        var windowRt = window.GetComponent<RectTransform>();
        windowRt.anchorMin = new Vector2(0.5f, 0.5f);
        windowRt.anchorMax = new Vector2(0.5f, 0.5f);
        windowRt.pivot = new Vector2(0.5f, 0.5f);
        windowRt.sizeDelta = new Vector2(360, 390);

        var windowBg = window.AddComponent<Image>();
        windowBg.color = Hex("1C2432");

        var header = CreateUIObject("Bar_MinimapHeader", window.transform);
        var headerRt = header.GetComponent<RectTransform>();
        headerRt.anchorMin = new Vector2(0f, 1f);
        headerRt.anchorMax = new Vector2(1f, 1f);
        headerRt.pivot = new Vector2(0.5f, 1f);
        headerRt.sizeDelta = new Vector2(0, 40);
        headerRt.anchoredPosition = Vector2.zero;

        var headerBg = header.AddComponent<Image>();
        headerBg.color = Hex("233049");

        var headerTitle = CreateText(
            "Text_MinimapTitle",
            header.transform,
            "Mini-map",
            14,
            FontStyle.Bold,
            TextAnchor.MiddleLeft,
            Hex("E6EDF9")
        );
        var htRt = headerTitle.GetComponent<RectTransform>();
        htRt.anchorMin = new Vector2(0f, 0f);
        htRt.anchorMax = new Vector2(1f, 1f);
        htRt.offsetMin = new Vector2(12, 0);
        htRt.offsetMax = new Vector2(-56, 0);

        var closeButton = CreateButton(header.transform, "Button_MinimapClose", "×", 34, 28, Hex("233049"));
        var cbRt = closeButton.GetComponent<RectTransform>();
        cbRt.anchorMin = new Vector2(1f, 0.5f);
        cbRt.anchorMax = new Vector2(1f, 0.5f);
        cbRt.pivot = new Vector2(1f, 0.5f);
        cbRt.anchoredPosition = new Vector2(-6, 0);

        var body = CreateUIObject("Panel_MinimapBody", window.transform);
        var bodyRt = body.GetComponent<RectTransform>();
        bodyRt.anchorMin = new Vector2(0f, 0f);
        bodyRt.anchorMax = new Vector2(1f, 1f);
        bodyRt.offsetMin = new Vector2(14, 14);
        bodyRt.offsetMax = new Vector2(-14, -54);

        var bodyBg = body.AddComponent<Image>();
        bodyBg.color = new Color(0, 0, 0, 0);

        var mapFrame = CreateUIObject("Panel_MinimapFrame", body.transform);
        var mapFrameRt = mapFrame.GetComponent<RectTransform>();
        mapFrameRt.anchorMin = new Vector2(0.5f, 0.5f);
        mapFrameRt.anchorMax = new Vector2(0.5f, 0.5f);
        mapFrameRt.pivot = new Vector2(0.5f, 0.5f);
        mapFrameRt.sizeDelta = new Vector2(300, 300);
        mapFrameRt.anchoredPosition = new Vector2(0, 10);

        var mapFrameBg = mapFrame.AddComponent<Image>();
        mapFrameBg.color = Hex("1F2530");

        var mapOutline = mapFrame.AddComponent<Outline>();
        mapOutline.effectColor = Hex("5D6B82");
        mapOutline.effectDistance = new Vector2(1f, -1f);

        var mapText = CreateText(
            "Text_MinimapPlaceholder",
            mapFrame.transform,
            "MINI MAP",
            18,
            FontStyle.Bold,
            TextAnchor.MiddleCenter,
            Hex("B6C3D9")
        );
        Stretch(mapText.GetComponent<RectTransform>(), 0, 20, 0, 90);

        var reservedText = CreateText(
            "Text_MinimapReserved",
            mapFrame.transform,
            "Reserved",
            12,
            FontStyle.Normal,
            TextAnchor.MiddleCenter,
            Hex("8B98AD")
        );
        Stretch(reservedText.GetComponent<RectTransform>(), 0, 0, 0, 60);

        overlay.SetActive(false);
    }

    private static GameObject CreateSection(Transform parent, string name, string titleText)
    {
        var section = CreateUIObject(name, parent);
        var img = section.AddComponent<Image>();
        img.color = Hex("ECE9E2");

        var vlg = section.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(8, 8, 8, 8);
        vlg.spacing = 6;
        vlg.childAlignment = TextAnchor.UpperLeft;
        vlg.childControlWidth = true;
        vlg.childControlHeight = true;
        vlg.childForceExpandWidth = true;
        vlg.childForceExpandHeight = false;

        var title = CreateText(
            "Text_Title_" + name.Replace("Section_", ""),
            section.transform,
            titleText,
            14,
            FontStyle.Bold,
            TextAnchor.MiddleLeft,
            Hex("222222")
        );
        SetLayout(title, -1, 22, 0, 0);

        return section;
    }

    private static void CreateDropdownField(Transform parent, string rowName, string labelText, string[] options, int defaultIndex)
    {
        var row = CreateUIObject(rowName, parent);
        SetLayout(row, -1, 58, 0, 0);

        var vlg = row.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(0, 0, 0, 0);
        vlg.spacing = 4;
        vlg.childAlignment = TextAnchor.UpperLeft;
        vlg.childControlWidth = true;
        vlg.childControlHeight = true;
        vlg.childForceExpandWidth = true;
        vlg.childForceExpandHeight = false;

        var label = CreateText("Label_" + rowName.Replace("Field_", ""), row.transform, labelText, 12, FontStyle.Normal, TextAnchor.MiddleLeft, Hex("202020"));
        SetLayout(label, -1, 18, 0, 0);

        var dropdown = DefaultControls.CreateDropdown(_resources);
        dropdown.name = "Dropdown_" + rowName.Replace("Field_", "");
        dropdown.transform.SetParent(row.transform, false);
        SetLayout(dropdown, -1, 30, 1, 0);

        var dd = dropdown.GetComponent<Dropdown>();
        dd.ClearOptions();
        dd.AddOptions(options.ToList());
        dd.value = Mathf.Clamp(defaultIndex, 0, options.Length - 1);

        var bg = dropdown.GetComponent<Image>();
        bg.color = Color.white;

        var caption = dropdown.transform.Find("Label");
        if (caption != null)
        {
            caption.name = "Text_Caption_" + rowName.Replace("Field_", "");
            var t = caption.GetComponent<Text>();
            t.font = Arial();
            t.fontSize = 13;
            t.color = Hex("222222");
            t.alignment = TextAnchor.MiddleLeft;
        }

        var arrow = dropdown.transform.Find("Arrow");
        if (arrow != null) arrow.name = "Icon_Arrow_" + rowName.Replace("Field_", "");

        var template = dropdown.transform.Find("Template");
        if (template != null) template.name = "Template_" + rowName.Replace("Field_", "");
    }

    private static void CreateSliderField(Transform parent, string rowName, string labelText, float min, float max, float value, string inputText)
    {
        var row = CreateUIObject(rowName, parent);
        SetLayout(row, -1, 62, 0, 0);

        var vlg = row.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(0, 0, 0, 0);
        vlg.spacing = 4;
        vlg.childAlignment = TextAnchor.UpperLeft;
        vlg.childControlWidth = true;
        vlg.childControlHeight = true;
        vlg.childForceExpandWidth = true;
        vlg.childForceExpandHeight = false;

        var label = CreateText("Label_" + rowName.Replace("Field_", ""), row.transform, labelText, 12, FontStyle.Normal, TextAnchor.MiddleLeft, Hex("202020"));
        SetLayout(label, -1, 18, 0, 0);

        var line = CreateHorizontalRow("Row_" + rowName.Replace("Field_", ""), row.transform, 8, 30);

        var slider = DefaultControls.CreateSlider(_resources);
        slider.name = "Slider_" + rowName.Replace("Field_", "");
        slider.transform.SetParent(line.transform, false);
        SetLayout(slider, -1, 20, 1, 0);

        var sl = slider.GetComponent<Slider>();
        sl.minValue = min;
        sl.maxValue = max;
        sl.value = value;

        var sliderBg = slider.transform.Find("Background");
        if (sliderBg != null)
        {
            sliderBg.name = "Background_" + rowName.Replace("Field_", "");
            var img = sliderBg.GetComponent<Image>();
            if (img != null) img.color = Hex("D8D3CB");
        }

        var fillArea = slider.transform.Find("Fill Area");
        if (fillArea != null) fillArea.name = "FillArea_" + rowName.Replace("Field_", "");

        var fill = slider.transform.Find("Fill Area/Fill");
        if (fill != null)
        {
            fill.name = "Fill_" + rowName.Replace("Field_", "");
            var img = fill.GetComponent<Image>();
            if (img != null) img.color = Hex("BFB8AD");
        }

        var handleArea = slider.transform.Find("Handle Slide Area");
        if (handleArea != null) handleArea.name = "HandleArea_" + rowName.Replace("Field_", "");

        var handle = slider.transform.Find("Handle Slide Area/Handle");
        if (handle != null)
        {
            handle.name = "Handle_" + rowName.Replace("Field_", "");
            var img = handle.GetComponent<Image>();
            if (img != null) img.color = Hex("EFEDE8");
        }

        var input = DefaultControls.CreateInputField(_resources);
        input.name = "InputField_" + rowName.Replace("Field_", "");
        input.transform.SetParent(line.transform, false);
        SetLayout(input, 64, 24, 0, 0);

        var inputField = input.GetComponent<InputField>();
        inputField.text = inputText;
        inputField.contentType = InputField.ContentType.DecimalNumber;

        var inputBg = input.GetComponent<Image>();
        inputBg.color = Color.white;

        var placeholder = input.transform.Find("Placeholder");
        if (placeholder != null)
        {
            placeholder.name = "Placeholder_" + rowName.Replace("Field_", "");
            var t = placeholder.GetComponent<Text>();
            t.text = "";
        }

        var text = input.transform.Find("Text");
        if (text != null)
        {
            text.name = "Text_" + rowName.Replace("Field_", "");
            var t = text.GetComponent<Text>();
            t.font = Arial();
            t.fontSize = 13;
            t.color = Hex("222222");
            t.alignment = TextAnchor.MiddleLeft;
        }
    }

    private static void CreateInputFieldRow(Transform parent, string rowName, string labelText, string value)
    {
        var row = CreateUIObject(rowName, parent);
        SetLayout(row, -1, 58, 0, 0);

        var vlg = row.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(0, 0, 0, 0);
        vlg.spacing = 4;
        vlg.childAlignment = TextAnchor.UpperLeft;
        vlg.childControlWidth = true;
        vlg.childControlHeight = true;
        vlg.childForceExpandWidth = true;
        vlg.childForceExpandHeight = false;

        var label = CreateText("Label_" + rowName.Replace("Field_", ""), row.transform, labelText, 12, FontStyle.Normal, TextAnchor.MiddleLeft, Hex("202020"));
        SetLayout(label, -1, 18, 0, 0);

        var input = DefaultControls.CreateInputField(_resources);
        input.name = "InputField_" + rowName.Replace("Field_", "");
        input.transform.SetParent(row.transform, false);
        SetLayout(input, -1, 30, 1, 0);

        var inputField = input.GetComponent<InputField>();
        inputField.text = value;
        inputField.contentType = InputField.ContentType.DecimalNumber;

        var bg = input.GetComponent<Image>();
        bg.color = Color.white;

        var placeholder = input.transform.Find("Placeholder");
        if (placeholder != null)
        {
            placeholder.name = "Placeholder_" + rowName.Replace("Field_", "");
            var t = placeholder.GetComponent<Text>();
            t.text = "";
        }

        var text = input.transform.Find("Text");
        if (text != null)
        {
            text.name = "Text_" + rowName.Replace("Field_", "");
            var t = text.GetComponent<Text>();
            t.font = Arial();
            t.fontSize = 13;
            t.color = Hex("222222");
            t.alignment = TextAnchor.MiddleLeft;
        }
    }

    private static void CreateToggleField(Transform parent, string rowName, string labelText, bool isOn)
    {
        var row = CreateUIObject(rowName, parent);
        SetLayout(row, -1, 28, 0, 0);

        var toggle = DefaultControls.CreateToggle(_resources);
        toggle.name = "Toggle_" + rowName.Replace("Field_", "");
        toggle.transform.SetParent(row.transform, false);
        Stretch(toggle.GetComponent<RectTransform>(), 0, 0, 0, 0);

        var tg = toggle.GetComponent<Toggle>();
        tg.isOn = isOn;

        var background = toggle.transform.Find("Background");
        if (background != null)
        {
            background.name = "Background_" + rowName.Replace("Field_", "");
            var img = background.GetComponent<Image>();
            if (img != null) img.color = Color.white;
        }

        var checkmark = toggle.transform.Find("Background/Checkmark");
        if (checkmark != null) checkmark.name = "Checkmark_" + rowName.Replace("Field_", "");

        var label = toggle.transform.Find("Label");
        if (label != null)
        {
            label.name = "Text_" + rowName.Replace("Field_", "");
            var t = label.GetComponent<Text>();
            t.text = labelText;
            t.font = Arial();
            t.fontSize = 12;
            t.color = Hex("202020");
            t.alignment = TextAnchor.MiddleLeft;
        }
    }

    private static GameObject CreateMultilineStatus(Transform parent, string name)
    {
        var input = DefaultControls.CreateInputField(_resources);
        input.name = name;
        input.transform.SetParent(parent, false);

        var field = input.GetComponent<InputField>();
        field.lineType = InputField.LineType.MultiLineNewline;
        field.readOnly = true;
        field.contentType = InputField.ContentType.Standard;

        var bg = input.GetComponent<Image>();
        bg.color = Color.white;

        var placeholder = input.transform.Find("Placeholder");
        if (placeholder != null)
        {
            placeholder.name = "Placeholder_StatusLog";
            var t = placeholder.GetComponent<Text>();
            t.text = "";
        }

        var text = input.transform.Find("Text");
        if (text != null)
        {
            text.name = "Text_StatusLog";
            var t = text.GetComponent<Text>();
            t.font = Arial();
            t.fontSize = 12;
            t.color = Hex("111111");
            t.alignment = TextAnchor.UpperLeft;
            var rt = text.GetComponent<RectTransform>();
            rt.offsetMin = new Vector2(10, 10);
            rt.offsetMax = new Vector2(-10, -10);
        }

        return input;
    }

    private static GameObject CreateButton(Transform parent, string name, string caption, float width, float height, Color bgColor)
    {
        var button = DefaultControls.CreateButton(_resources);
        button.name = name;
        button.transform.SetParent(parent, false);
        SetLayout(button, width, height, 0, 0);

        var img = button.GetComponent<Image>();
        img.color = bgColor;

        var txt = button.GetComponentInChildren<Text>();
        txt.text = caption;
        txt.font = Arial();
        txt.fontSize = 14;
        txt.fontStyle = FontStyle.Bold;
        txt.color = Hex("222222");
        txt.alignment = TextAnchor.MiddleCenter;
        txt.gameObject.name = "Text_" + name.Replace("Button_", "");

        return button;
    }

    private static GameObject CreateHorizontalRow(string name, Transform parent, float spacing, float height)
    {
        var row = CreateUIObject(name, parent);
        SetLayout(row, -1, height, 0, 0);

        var hlg = row.AddComponent<HorizontalLayoutGroup>();
        hlg.padding = new RectOffset(0, 0, 0, 0);
        hlg.spacing = spacing;
        hlg.childAlignment = TextAnchor.MiddleLeft;
        hlg.childControlWidth = false;
        hlg.childControlHeight = true;
        hlg.childForceExpandWidth = false;
        hlg.childForceExpandHeight = false;

        return row;
    }

    private static GameObject CreateText(
        string name,
        Transform parent,
        string value,
        int fontSize,
        FontStyle style,
        TextAnchor anchor,
        Color color
    )
    {
        var go = CreateUIObject(name, parent);
        var text = go.AddComponent<Text>();
        text.font = Arial();
        text.text = value;
        text.fontSize = fontSize;
        text.fontStyle = style;
        text.alignment = anchor;
        text.color = color;
        text.horizontalOverflow = HorizontalWrapMode.Wrap;
        text.verticalOverflow = VerticalWrapMode.Truncate;
        return go;
    }

    private static GameObject CreateUIObject(string name, Transform parent)
    {
        var go = new GameObject(name, typeof(RectTransform));
        Undo.RegisterCreatedObjectUndo(go, "Create " + name);
        go.transform.SetParent(parent, false);
        return go;
    }

    private static void Stretch(RectTransform rt, float left, float bottom, float right, float top)
    {
        rt.anchorMin = Vector2.zero;
        rt.anchorMax = Vector2.one;
        rt.offsetMin = new Vector2(left, bottom);
        rt.offsetMax = new Vector2(-right, -top);
    }

    private static void SetLayout(GameObject go, float preferredWidth, float preferredHeight, float flexibleWidth, float flexibleHeight)
    {
        var le = go.GetComponent<LayoutElement>();
        if (le == null) le = go.AddComponent<LayoutElement>();

        if (preferredWidth >= 0)
        {
            le.preferredWidth = preferredWidth;
            le.minWidth = preferredWidth;
        }

        if (preferredHeight >= 0)
        {
            le.preferredHeight = preferredHeight;
            le.minHeight = preferredHeight;
        }

        le.flexibleWidth = flexibleWidth;
        le.flexibleHeight = flexibleHeight;
    }

    private static Font Arial()
    {
        return Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
    }

    private static Color Hex(string hex)
    {
        ColorUtility.TryParseHtmlString("#" + hex, out var c);
        return c;
    }

    private static Sprite EnsureFovCircleSpriteAsset()
    {
        const string folderPath = "Assets/GeneratedUI";
        const string assetPath = "Assets/GeneratedUI/RetinalLaserFOVCircle.png";

        if (!Directory.Exists(folderPath))
        {
            Directory.CreateDirectory(folderPath);
        }

        var existing = AssetDatabase.LoadAssetAtPath<Sprite>(assetPath);
        if (existing != null) return existing;

        const int size = 512;
        const float outlineWidth = 2.5f;

        var tex = new Texture2D(size, size, TextureFormat.ARGB32, false);
        tex.filterMode = FilterMode.Bilinear;

        var center = new Vector2((size - 1) * 0.5f, (size - 1) * 0.5f);
        float radius = size * 0.48f;

        var fill = Hex("03080F");
        var outline = Hex("8DA2BF");

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float dist = Vector2.Distance(new Vector2(x, y), center);

                if (dist <= radius)
                {
                    if (dist >= radius - outlineWidth)
                        tex.SetPixel(x, y, outline);
                    else
                        tex.SetPixel(x, y, fill);
                }
                else
                {
                    tex.SetPixel(x, y, new Color(0, 0, 0, 0));
                }
            }
        }

        tex.Apply();

        File.WriteAllBytes(assetPath, tex.EncodeToPNG());
        Object.DestroyImmediate(tex);

        AssetDatabase.Refresh();

        var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer != null)
        {
            importer.textureType = TextureImporterType.Sprite;
            importer.alphaIsTransparency = true;
            importer.mipmapEnabled = false;
            importer.spritePixelsPerUnit = 100;
            importer.SaveAndReimport();
        }

        return AssetDatabase.LoadAssetAtPath<Sprite>(assetPath);
    }
}