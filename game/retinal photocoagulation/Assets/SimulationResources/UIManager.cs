using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class UIManager : MonoBehaviour
{
    private const string DefaultSettingsPanelName = "Settings_Overlay";
    private const string DefaultRadialPanelName = "RadialMenu_Overlay";

    [Header("UI Panels")]
    public GameObject settingsPanel;
    public GameObject radialMenuPanel;

    [Header("8向环形菜单")]
    [Tooltip("按顺时针顺序配置8个菜单项（建议从正上方开始）")]
    public RectTransform[] radialItems = new RectTransform[8];
    [Tooltip("菜单项中心到轮盘中心的半径")]
    public float radialRadius = 170f;
    [Tooltip("首个菜单项的角度（0为向右，90为向上）")]
    public float startAngle = 90f;
    [Tooltip("是否按顺时针方向布局")]
    public bool clockwise = true;
    [Tooltip("中心死区半径，鼠标在死区内不选中任何方向")]
    public float deadZoneRadius = 40f;
    [Tooltip("默认颜色")]
    public Color normalItemColor = new Color(1f, 1f, 1f, 0.85f);
    [Tooltip("选中高亮颜色")]
    public Color highlightedItemColor = new Color(1f, 0.88f, 0.35f, 1f);

    [Header("参数滚轮模式")]
    [Tooltip("启用后，Element 0~3 分别对应 功率/时长/光斑/波长，滚轮上调加、下调减")]
    public bool useFourItemBidirectionalScroll = true;
    [Tooltip("参数控制目标（通常拖入挂有 SurgerySimulator 的对象）")]
    public SurgerySimulator surgerySimulator;

    [Header("Time Scale Settings")]
    [Tooltip("轮盘呼出时的时间流速，1为正常，0.1为极慢的子弹时间")]
    public float bulletTimeScale = 0.1f;

    [Header("滚轮调参")]
    [Tooltip("启用后，悬停选中某个方块时，滚轮会触发该方块绑定的按钮事件")]
    public bool enableScrollAdjust = true;
    [Tooltip("每次滚轮事件最多触发的步数，避免滚动过快导致参数跳变过大")]
    public int maxScrollStepsPerFrame = 3;

    // 记录设置面板的开关状态
    private bool isSettingsOpen = false;
    private int currentSelectedIndex = -1;
    private Camera uiCamera;

    private void Awake()
    {
        AutoBindReferences();

        if (radialMenuPanel != null)
        {
            var canvas = radialMenuPanel.GetComponentInParent<Canvas>();
            if (canvas != null)
            {
                uiCamera = canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : canvas.worldCamera;
            }
        }
    }

    private void Start()
    {
        AutoBindReferences();
        LayoutRadialItems();
        ResetItemHighlight();

        if (radialMenuPanel != null)
        {
            radialMenuPanel.SetActive(false);
        }
    }

    void Update()
    {
        HandleSettingsInput();
        HandleRadialMenuInput();

        if (radialMenuPanel != null && radialMenuPanel.activeSelf && !isSettingsOpen)
        {
            UpdateRadialSelectionByMouse();
            HandleRadialScrollAdjust();
        }
    }

    private void LayoutRadialItems()
    {
        int itemCount = GetLayoutItemCount();
        if (radialItems == null || radialItems.Length == 0 || itemCount <= 0)
        {
            return;
        }

        var step = 360f / itemCount;
        var sign = clockwise ? -1f : 1f;

        for (int i = 0; i < itemCount; i++)
        {
            var item = radialItems[i];
            if (item == null)
            {
                continue;
            }

            float angleDeg = startAngle + sign * i * step;
            float angleRad = angleDeg * Mathf.Deg2Rad;
            item.anchoredPosition = new Vector2(Mathf.Cos(angleRad), Mathf.Sin(angleRad)) * radialRadius;
        }
    }

    private void UpdateRadialSelectionByMouse()
    {
        if (radialMenuPanel == null)
        {
            return;
        }

        var panelRect = radialMenuPanel.GetComponent<RectTransform>();
        if (panelRect == null)
        {
            return;
        }

        if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(panelRect, Input.mousePosition, uiCamera, out var localPos))
        {
            return;
        }

        if (localPos.magnitude < deadZoneRadius)
        {
            SetSelectedIndex(-1);
            return;
        }

        float angle = Mathf.Atan2(localPos.y, localPos.x) * Mathf.Rad2Deg;
        int itemCount = GetLayoutItemCount();
        if (itemCount <= 0)
        {
            SetSelectedIndex(-1);
            return;
        }

        float relative = Mathf.Repeat(startAngle - angle, 360f);
        float sectorSize = 360f / itemCount;
        int index = Mathf.FloorToInt((relative + sectorSize * 0.5f) / sectorSize) % itemCount;

        if (!clockwise)
        {
            index = (itemCount - index) % itemCount;
        }

        SetSelectedIndex(index);
    }

    private void SetSelectedIndex(int index)
    {
        if (currentSelectedIndex == index)
        {
            return;
        }

        currentSelectedIndex = index;
        RefreshItemHighlight();
    }

    private void ResetItemHighlight()
    {
        currentSelectedIndex = -1;
        RefreshItemHighlight();
    }

    private void RefreshItemHighlight()
    {
        if (radialItems == null)
        {
            return;
        }

        for (int i = 0; i < radialItems.Length; i++)
        {
            if (radialItems[i] == null)
            {
                continue;
            }

            var image = radialItems[i].GetComponent<Image>();
            if (image == null)
            {
                continue;
            }

            image.color = (i == currentSelectedIndex) ? highlightedItemColor : normalItemColor;
        }
    }

    private void ConfirmCurrentSelection()
    {
        if (currentSelectedIndex < 0 || radialItems == null || currentSelectedIndex >= radialItems.Length)
        {
            return;
        }

        var selectedItem = radialItems[currentSelectedIndex];
        if (selectedItem == null)
        {
            return;
        }

        var button = selectedItem.GetComponent<Button>();
        if (button != null)
        {
            button.onClick.Invoke();
        }

        Debug.Log($"8向菜单选择: {currentSelectedIndex} -> {selectedItem.name}");
    }

    private void HandleRadialScrollAdjust()
    {
        if (!enableScrollAdjust)
        {
            return;
        }

        int itemCount = GetActiveItemCount();
        if (currentSelectedIndex < 0 || radialItems == null || currentSelectedIndex >= itemCount)
        {
            return;
        }

        float scroll = Input.mouseScrollDelta.y;
        if (Mathf.Abs(scroll) < 0.01f)
        {
            return;
        }

        if (useFourItemBidirectionalScroll && surgerySimulator != null)
        {
            // Element 0..3 -> 功率/时长/光斑/波长
            if (currentSelectedIndex >= 0 && currentSelectedIndex <= 3)
            {
                int direction = scroll > 0f ? 1 : -1;
                int fourModeSteps = Mathf.Clamp(Mathf.Max(1, Mathf.RoundToInt(Mathf.Abs(scroll))), 1, Mathf.Max(1, maxScrollStepsPerFrame));
                for (int i = 0; i < fourModeSteps; i++)
                {
                    surgerySimulator.AdjustRadialParameter(currentSelectedIndex, direction);
                }
            }
            return;
        }

        var selectedItem = radialItems[currentSelectedIndex];
        if (selectedItem == null)
        {
            return;
        }

        var button = selectedItem.GetComponent<Button>();
        if (button == null)
        {
            return;
        }

        int steps = Mathf.Clamp(Mathf.Max(1, Mathf.RoundToInt(Mathf.Abs(scroll))), 1, Mathf.Max(1, maxScrollStepsPerFrame));
        for (int i = 0; i < steps; i++)
        {
            button.onClick.Invoke();
        }
    }

    // 处理设置面板 (Esc键 切换开关)
    private void HandleSettingsInput()
    {
        if (Input.GetKeyDown(KeyCode.Escape))
        {
            isSettingsOpen = !isSettingsOpen;
            if (settingsPanel != null)
            {
                settingsPanel.SetActive(isSettingsOpen);
            }

            // 如果打开了设置菜单，通常游戏应该完全暂停
            if (isSettingsOpen)
            {
                Time.timeScale = 0f; 
            }
            else
            {
                // 设置开启期间可能松开了Tab，避免轮盘卡住显示。
                if (radialMenuPanel != null && radialMenuPanel.activeSelf && !Input.GetKey(KeyCode.Tab))
                {
                    radialMenuPanel.SetActive(false);
                    ResetItemHighlight();
                }

                // 若轮盘仍处于打开状态，恢复子弹时间；否则恢复正常时间。
                if (radialMenuPanel != null && radialMenuPanel.activeSelf)
                {
                    Time.timeScale = bulletTimeScale;
                }
                else
                {
                    Time.timeScale = 1f;
                }
            }
        }
    }

    // 处理战术轮盘 (Tab键 长按呼出，松开隐藏)
    private void HandleRadialMenuInput()
    {
        // 如果设置面板开着，就屏蔽轮盘操作
        if (isSettingsOpen) return;

        if (radialMenuPanel == null) return;

        // 按下 Tab 键瞬间：呼出轮盘，进入子弹时间
        if (Input.GetKeyDown(KeyCode.Tab))
        {
            radialMenuPanel.SetActive(true);
            Time.timeScale = bulletTimeScale;
            ResetItemHighlight();
        }

        // 松开 Tab 键瞬间：隐藏轮盘，时间恢复正常
        if (Input.GetKeyUp(KeyCode.Tab))
        {
            radialMenuPanel.SetActive(false);
            Time.timeScale = 1f;
            
            // TODO: 在这里可以触发“应用轮盘参数”的逻辑
            Debug.Log("轮盘参数已确认！");
        }
    }

    private int GetActiveItemCount()
    {
        if (radialItems == null || radialItems.Length == 0)
        {
            return 0;
        }

        int expected = useFourItemBidirectionalScroll ? 4 : radialItems.Length;
        return Mathf.Clamp(expected, 0, radialItems.Length);
    }

    // 布局始终按完整轮盘数量计算，避免四方向模式影响8向环状排布。
    private int GetLayoutItemCount()
    {
        if (radialItems == null || radialItems.Length == 0)
        {
            return 0;
        }

        int nonNullCount = 0;
        for (int i = 0; i < radialItems.Length; i++)
        {
            if (radialItems[i] != null)
            {
                nonNullCount++;
            }
        }

        return nonNullCount > 0 ? nonNullCount : radialItems.Length;
    }

    private void AutoBindReferences()
    {
        if (settingsPanel == null)
        {
            var obj = GameObject.Find(DefaultSettingsPanelName);
            if (obj != null) settingsPanel = obj;
        }

        if (radialMenuPanel == null)
        {
            var obj = GameObject.Find(DefaultRadialPanelName);
            if (obj != null) radialMenuPanel = obj;
        }

        if (surgerySimulator == null)
        {
            surgerySimulator = FindObjectOfType<SurgerySimulator>();
        }

        AutoBindRadialItems();
    }

    private void AutoBindRadialItems()
    {
        if (radialMenuPanel == null || radialItems == null || radialItems.Length == 0)
        {
            return;
        }

        int targetCount = radialItems.Length;
        if (targetCount <= 0) return;

        bool needBind = false;
        for (int i = 0; i < targetCount; i++)
        {
            if (radialItems[i] == null)
            {
                needBind = true;
                break;
            }
        }

        if (!needBind) return;

        int writeIndex = 0;
        foreach (Transform child in radialMenuPanel.transform)
        {
            if (writeIndex >= targetCount) break;
            var rt = child as RectTransform;
            if (rt == null) continue;
            if (rt.GetComponent<Button>() == null) continue;
            radialItems[writeIndex++] = rt;
        }

        if (writeIndex < targetCount)
        {
            Button[] buttons = radialMenuPanel.GetComponentsInChildren<Button>(true);
            for (int i = 0; i < buttons.Length && writeIndex < targetCount; i++)
            {
                var rt = buttons[i].GetComponent<RectTransform>();
                if (rt == null || rt == radialMenuPanel.GetComponent<RectTransform>()) continue;

                bool exists = false;
                for (int j = 0; j < writeIndex; j++)
                {
                    if (radialItems[j] == rt)
                    {
                        exists = true;
                        break;
                    }
                }

                if (!exists)
                {
                    radialItems[writeIndex++] = rt;
                }
            }
        }
    }

    // ==========================================
    // 设置面板专属功能代码
    // ==========================================

    // 1. 继续手术
    public void ResumeGame()
    {
        isSettingsOpen = false;
        if (settingsPanel != null)
        {
            settingsPanel.SetActive(false);
        }

        // 继续游戏时，确保轮盘关闭并恢复高亮状态。
        if (radialMenuPanel != null && radialMenuPanel.activeSelf)
        {
            radialMenuPanel.SetActive(false);
            ResetItemHighlight();
        }

        Time.timeScale = 1f;
    }

    // 2. 重新开始
    public void RestartGame()
    {
        Time.timeScale = 1f;
        SceneManager.LoadScene(SceneManager.GetActiveScene().name);
    }

    // 3. 退出手术
    public void QuitGame()
    {
        Debug.Log("执行退出游戏指令...");
        Application.Quit();
    }

    // 4. 键位设置（目前作为占位符）
    public void OpenKeybindSettings()
    {
        Debug.Log("打开键位设置子菜单...");
    }

    // 5. 主音量滑动条响应
    public void OnVolumeChanged(float value)
    {
        AudioListener.volume = value;
    }

    // 6. 鼠标灵敏度滑动条响应
    public void OnSensitivityChanged(float value)
    {
        PlayerPrefs.SetFloat("MouseSensitivity", value);
        PlayerPrefs.Save();
    }
}