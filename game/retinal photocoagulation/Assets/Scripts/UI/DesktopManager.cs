using UnityEngine;

public class DesktopManager : MonoBehaviour
{
    // 在这里声明 7 个窗口物体，以后要在 Unity 里把它们拖进来
    [Header("Windows")]
    public GameObject shopWindow;
    public GameObject orderWindow;
    public GameObject historyWindow;
    public GameObject gameWindow1;
    public GameObject gameWindow2;
    public GameObject gameWindow3;
    public GameObject gameWindow4;

    // --- 窗口开关函数 ---

    public void OpenShop() { shopWindow.SetActive(true); }
    public void CloseShop() { shopWindow.SetActive(false); }

    public void OpenOrder() { orderWindow.SetActive(true); }
    public void CloseOrder() { orderWindow.SetActive(false); }

    public void OpenHistory() { historyWindow.SetActive(true); }
    public void CloseHistory() { historyWindow.SetActive(false); }

    // 这里以第一个游戏为例，其他的你可以自己照着写
    public void OpenGame1() { gameWindow1.SetActive(true); }
    public void CloseGame1() { gameWindow1.SetActive(false); }

    public void OpenGame2() { gameWindow2.SetActive(true); }
    public void CloseGame2() { gameWindow2.SetActive(false); }

    public void OpenGame3() { gameWindow3.SetActive(true); }
    public void CloseGame3() { gameWindow3.SetActive(false); }

    public void OpenGame4() { gameWindow4.SetActive(true); }
    public void CloseGame4() { gameWindow4.SetActive(false); }
}