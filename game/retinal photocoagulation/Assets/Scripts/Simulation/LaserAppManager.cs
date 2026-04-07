using UnityEngine;
using UnityEngine.UI;
using System.Collections.Generic;
using System.IO;
using System;

[Serializable]
public class ShotParamsData {
    public float power;
    public float spot_size_set;
    public float z_offset;
    public float exposure_time;
    public float wavelength;
}

[Serializable]
public class ShotRecordData {
    public int id;
    public float[] pos;
    public bool is_trial;
    public int spot_grade;
    public ShotParamsData parameters;
}

[Serializable]
public class SessionOutputData {
    public string session_id;
    public string task_id;
    public PlayerInfo player_info;
    public List<ShotRecordData> shots;
}

[Serializable]
public class PlayerInfo {
    public string id;
    public string name;
}

public class LaserAppManager : MonoBehaviour
{
    public static LaserAppManager Instance;

    [Header("眼底图设置")]
    public Texture2D originFundusImage;
    private RenderTexture runtimeRT;
    private RetinaPainter painter;

    // UI 控件
    private Slider sliderPower, sliderSpot, sliderDuration, sliderFocus;
    private Text lblPower, lblSpot, lblDuration, lblTaskInfo, lblFocus;
    private Dropdown dropWave;
    private Toggle chkTrial;
    private Button btnCalib;

    // 逻辑变量
    private LaserPhysicalModel physicsModel;
    private List<ShotRecordData> actionStream = new List<ShotRecordData>();
    private string taskId = "Task_Demo_001";
    private int currentBlurLevel = -1;
    private float lastOptimalZ = 0f;
    private float lastFocusDiff = 0f;
    
    public float pixelToUm = 2.0f; 
    public float zOffset = 0.0f; // 用户设定的 Z 轴位置
    public string interactionMode = "fire"; 

    void Awake() {
        Instance = this;
        EnsureMainCamera();
    }

    void Start() {
        BindUIElements();
        painter = GameObject.Find("CenterViewport")?.GetComponent<RetinaPainter>();

        if (painter != null && originFundusImage != null) {
            // 初始化高清画布
            runtimeRT = new RenderTexture(originFundusImage.width, originFundusImage.height, 0);
            Graphics.Blit(originFundusImage, runtimeRT);
            
            if(painter.ImageContent != null) {
                painter.SetSourceTexture(runtimeRT);
                painter.ImageContent.color = Color.white;
                // 初始化 1.5 倍缩放布局
                painter.SetupImageSize(originFundusImage.width, originFundusImage.height);
                CheckFocusState(true);
            }
            // 隐藏初始提示文字
            GameObject label = GameObject.Find("CenterViewport/Label");
            if (label != null) label.SetActive(false);
        }

        // 初始化物理模型
        physicsModel = new LaserPhysicalModel(new TaskParams());
        UpdateUI();
    }

    void Update() {
        // 对齐 Python 的 check_focus_state：每帧检测，等级变化才刷新显示层。
        CheckFocusState();
    }

    private void CheckFocusState(bool forceUpdate = false) {
        if (painter == null || painter.spotMaterial == null) return;

        float prevOptimalZ = lastOptimalZ;
        float prevFocusDiff = lastFocusDiff;
        int prevBlur = currentBlurLevel;

        float optimalZ = GetOptimalZ();
        float focusDiff = Mathf.Abs(zOffset - optimalZ);
        int newBlur = Mathf.FloorToInt(focusDiff / 7.5f);
        newBlur = Mathf.Min(newBlur, 20);
        lastOptimalZ = optimalZ;
        lastFocusDiff = focusDiff;

        if (forceUpdate || newBlur != currentBlurLevel) {
            currentBlurLevel = newBlur;
            painter.ApplyFocusBlur(currentBlurLevel, true);
        }

        bool metricsChanged = Mathf.Abs(prevOptimalZ - lastOptimalZ) > 0.01f || Mathf.Abs(prevFocusDiff - lastFocusDiff) > 0.01f || prevBlur != currentBlurLevel;
        if (forceUpdate || metricsChanged) {
            UpdateUI();
        }
    }

    // 让目标焦段和图像尺寸解耦，避免超大图在边缘时目标焦段超过可调范围。
    public float GetOptimalZ() {
        if (painter == null || originFundusImage == null) return 0f;
        Vector2 uv = painter.GetViewportCenterUV();
        float imgX = uv.x * originFundusImage.width;
        float imgY = uv.y * originFundusImage.height;
        Vector2 center = new Vector2(originFundusImage.width * 0.5f, originFundusImage.height * 0.5f);
        float r = Vector2.Distance(new Vector2(imgX, imgY), center);
        float maxRadius = Vector2.Distance(Vector2.zero, center);
        float normalized = maxRadius > 0.0001f ? Mathf.Clamp01(r / maxRadius) : 0f;
        return normalized * 1200f;
    }

    public void AdjustFocus(float delta) {
        zOffset = Mathf.Clamp(zOffset + delta, -2500f, 2500f);
        if(sliderFocus != null) sliderFocus.value = zOffset; // 同步滑动条
        CheckFocusState(true);
        UpdateUI();
    }

    private void BindUIElements() {
        // 绑定右侧参数面板
        sliderPower = GameObject.Find("Slider_Power").GetComponent<Slider>();
        lblPower = GameObject.Find("Slider_Power_Label").GetComponent<Text>();
        sliderSpot = GameObject.Find("Slider_Spot").GetComponent<Slider>();
        lblSpot = GameObject.Find("Slider_Spot_Label").GetComponent<Text>();
        sliderDuration = GameObject.Find("Slider_Duration").GetComponent<Slider>();
        lblDuration = GameObject.Find("Slider_Duration_Label").GetComponent<Text>();

        // 绑定调焦 Slider
        sliderFocus = GameObject.Find("Slider_Focus")?.GetComponent<Slider>();
        if(sliderFocus != null) {
            sliderFocus.minValue = -2500f;
            sliderFocus.maxValue = 2500f;
            sliderFocus.onValueChanged.AddListener(v => { zOffset = v; CheckFocusState(true); UpdateUI(); });
        }

        dropWave = GameObject.Find("Drop_Wave").GetComponent<Dropdown>();
        chkTrial = GameObject.Find("Chk_Trial").GetComponent<Toggle>();
        lblTaskInfo = GameObject.Find("Lbl_TaskInfo").GetComponent<Text>();
        lblFocus = GameObject.Find("Lbl_Focus").GetComponent<Text>();

        // 绑定左侧/底部按钮
        GameObject.Find("Btn_EndTreatment").GetComponent<Button>().onClick.AddListener(ExportJsonAndExit);
        GameObject.Find("Btn_Reset").GetComponent<Button>().onClick.AddListener(ResetImage);
        
        btnCalib = GameObject.Find("Btn_Calib").GetComponent<Button>();
        btnCalib.onClick.AddListener(EnableCalibration);
        
        // 方向键平移
        GameObject.Find("Btn_Up").GetComponent<Button>().onClick.AddListener(() => painter?.Pan(new Vector2(0, -100)));
        GameObject.Find("Btn_Down").GetComponent<Button>().onClick.AddListener(() => painter?.Pan(new Vector2(0, 100)));
        GameObject.Find("Btn_Left").GetComponent<Button>().onClick.AddListener(() => painter?.Pan(new Vector2(100, 0)));
        GameObject.Find("Btn_Right").GetComponent<Button>().onClick.AddListener(() => painter?.Pan(new Vector2(-100, 0)));
        
        // 实时更新标签
        sliderPower.onValueChanged.AddListener(v => lblPower.text = $"功率 (P): {v} mW");
        sliderSpot.onValueChanged.AddListener(v => lblSpot.text = $"设定光斑 (S): {v} μm");
        sliderDuration.onValueChanged.AddListener(v => lblDuration.text = $"曝光时间 (T): {v} ms");
    }

    private void EnsureMainCamera() {
        if (Camera.main == null) {
            GameObject camObj = new GameObject("MainCamera") { tag = "MainCamera" };
            Camera cam = camObj.AddComponent<Camera>();
            cam.backgroundColor = Color.black;
            cam.clearFlags = CameraClearFlags.SolidColor;
            camObj.transform.position = new Vector3(0, 0, -10);
        }
        // 禁用 SceneAutoBuilder 生成的旧 3D 摄像机
        GameObject oldCam = GameObject.Find("RetinaCamera");
        if (oldCam != null) oldCam.SetActive(false);
    }

    public void RecordShot(Vector2 uvPos, int grade) {
        float pxX = uvPos.x * originFundusImage.width;
        float pxY = uvPos.y * originFundusImage.height;
        var (p, s, t, wave) = GetCurrentLaserParams();

        ShotRecordData record = new ShotRecordData {
            id = actionStream.Count + 1,
            pos = new float[] { pxX, pxY },
            is_trial = chkTrial.isOn,
            spot_grade = grade,
            parameters = new ShotParamsData { 
                power = p, spot_size_set = s, exposure_time = t, wavelength = wave, z_offset = zOffset 
            }
        };
        actionStream.Add(record);
        UpdateUI();
    }

    public void ProcessCalibration(float dist) {
        pixelToUm = 1500.0f / dist;
        interactionMode = "fire";
        
        btnCalib.GetComponentInChildren<Text>().text = "视盘尺寸标定";
        btnCalib.GetComponent<Image>().color = Color.white;
        UpdateUI();
    }

    private void EnableCalibration() {
        interactionMode = "calibrate";
        btnCalib.GetComponentInChildren<Text>().text = "标定中...";
        btnCalib.GetComponent<Image>().color = new Color(1f, 0.4f, 0.4f);
        UpdateUI();
    }

    private void ResetImage() {
        if (runtimeRT) Graphics.Blit(originFundusImage, runtimeRT);
        actionStream.Clear();
        zOffset = 0f; 
        currentBlurLevel = -1;
        if(sliderFocus) sliderFocus.value = 0f;
        painter?.ResetView();
        CheckFocusState(true);
        UpdateUI();
    }

    // ====== 导出逻辑 (已修复语法错误) ======
    private void ExportJsonAndExit() {
        if (actionStream.Count == 0) {
            Debug.LogWarning("未记录任何数据，取消导出。");
            return;
        }

        string timeStamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        string sessionId = "SESS_" + timeStamp;
        string fileName = sessionId + "_result.json";
        // 存储在 Assets 的同级目录下
        string path = Path.Combine(Application.dataPath, "../" + fileName);

        SessionOutputData output = new SessionOutputData {
            session_id = sessionId,
            task_id = taskId,
            player_info = new PlayerInfo { id = "ST_001", name = "Operator" },
            shots = actionStream
        };

        try {
            string jsonString = JsonUtility.ToJson(output, true);
            File.WriteAllText(path, jsonString);
            Debug.Log($"✅ 数据导出成功: {path}");
        } catch (Exception e) {
            Debug.LogError($"导出失败: {e.Message}");
        }

#if UNITY_EDITOR
        UnityEditor.EditorApplication.isPlaying = false;
#else
        Application.Quit();
#endif
    }

    private void UpdateUI() {
        lblTaskInfo.text = $"任务 ID: {taskId}\n已击发: {actionStream.Count} 点";
        lblFocus.text = $"系统焦段 (Z): {zOffset:F1}\n目标焦段 (Optimal): {lastOptimalZ:F1}\n焦差: {lastFocusDiff:F1} | Blur: {currentBlurLevel}\n当前比例: 1px = {pixelToUm:F2} μm";
    }

    public (float p, float s, float t, float wave) GetCurrentLaserParams() {
        return (sliderPower.value, sliderSpot.value, sliderDuration.value, dropWave.value == 0 ? 532f : 672f);
    }

    public LaserPhysicalModel GetPhysicsModel() => physicsModel;
}