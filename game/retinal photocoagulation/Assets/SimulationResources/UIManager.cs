using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class UIManager : MonoBehaviour
{
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

    [Header("Time Scale Settings")]
    [Tooltip("轮盘呼出时的时间流速，1为正常，0.1为极慢的子弹时间")]
    public float bulletTimeScale = 0.1f;

    // 记录设置面板的开关状态
    private bool isSettingsOpen = false;
    private int currentSelectedIndex = -1;
    private Camera uiCamera;

    private void Awake()
    {
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
        }
    }

    private void LayoutRadialItems()
    {
        if (radialItems == null || radialItems.Length == 0)
        {
            return;
        }

        var step = 360f / radialItems.Length;
        var sign = clockwise ? -1f : 1f;

        for (int i = 0; i < radialItems.Length; i++)
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
        float relative = Mathf.Repeat(startAngle - angle, 360f);
        float sectorSize = 360f / 8f;
        int index = Mathf.FloorToInt((relative + sectorSize * 0.5f) / sectorSize) % 8;

        if (!clockwise)
        {
            index = (8 - index) % 8;
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

    // 处理设置面板 (Esc键 切换开关)
    private void HandleSettingsInput()
    {
        if (Input.GetKeyDown(KeyCode.Escape))
        {
            isSettingsOpen = !isSettingsOpen;
            settingsPanel.SetActive(isSettingsOpen);

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
            ConfirmCurrentSelection();
            radialMenuPanel.SetActive(false);
            Time.timeScale = 1f;
            
            // TODO: 在这里可以触发“应用轮盘参数”的逻辑
            Debug.Log("轮盘参数已确认！");
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