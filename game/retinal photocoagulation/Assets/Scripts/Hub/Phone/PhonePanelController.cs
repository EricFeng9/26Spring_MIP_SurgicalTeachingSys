using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace RetinalPrototype.Hub.Phone
{
    public sealed class PhonePanelController : MonoBehaviour
    {
        [Header("Panel")]
        [SerializeField] private CanvasGroup panelCanvasGroup;
        [SerializeField] private GameObject panelRoot;
        [SerializeField] private Button closeButton;
        [SerializeField] private TMP_Text chatHeaderText;

        [Header("Data")]
        [SerializeField] private List<PhoneTaskData> tasks = new List<PhoneTaskData>();
        [SerializeField] private int defaultSelectedIndex;

        [Header("Contact List")]
        [SerializeField] private Transform contactContentRoot;
        [SerializeField] private PhoneContactItemUI contactItemPrefab;
        [SerializeField] private Sprite contactNormalBackground;
        [SerializeField] private Sprite contactSelectedBackground;

        [Header("Messages")]
        [SerializeField] private Transform messageContentRoot;
        [SerializeField] private ScrollRect messageScrollRect;
        [SerializeField] private PhoneMessageItemUI patientMessagePrefab;
        [SerializeField] private PhoneMessageItemUI doctorMessagePrefab;

        [Header("Decision Buttons")]
        [SerializeField] private GameObject decisionRoot;
        [SerializeField] private Button yesButton;
        [SerializeField] private Button noButton;
        [SerializeField] private string fallbackYesSceneName;
        [SerializeField] private string fallbackNoSceneName;

        [Header("Dependencies")]
        [SerializeField] private ClinicHubPlayerController playerController;
        [SerializeField] private RetinalPrototype.SceneTransitionController sceneTransition;
        [SerializeField] private bool lockPlayerWhileOpen = true;
        [SerializeField] private bool autoCloseOnDecision = true;

        [Header("Events")]
        [SerializeField] private UnityEvent onPhoneOpened;
        [SerializeField] private UnityEvent onPhoneClosed;
        [SerializeField] private UnityEvent onDecisionYes;
        [SerializeField] private UnityEvent onDecisionNo;

        private readonly List<PhoneContactItemUI> _contactItems = new List<PhoneContactItemUI>();
        private int _currentTaskIndex = -1;

        private void Awake()
        {
            if (closeButton != null)
            {
                closeButton.onClick.AddListener(ClosePhone);
            }

            if (yesButton != null)
            {
                yesButton.onClick.AddListener(HandleYesClicked);
            }

            if (noButton != null)
            {
                noButton.onClick.AddListener(HandleNoClicked);
            }

            SetPanelVisible(false);
        }

        public void OpenPhone()
        {
            if (tasks == null || tasks.Count == 0)
            {
                SetPanelVisible(true);
                return;
            }

            SetPanelVisible(true);
            BuildContactList();
            SelectTask(Mathf.Clamp(defaultSelectedIndex, 0, tasks.Count - 1));

            if (lockPlayerWhileOpen && playerController != null)
            {
                playerController.SetInputLocked(true);
            }

            onPhoneOpened?.Invoke();
        }

        public void ClosePhone()
        {
            SetPanelVisible(false);

            if (lockPlayerWhileOpen && playerController != null)
            {
                playerController.SetInputLocked(false);
                playerController.SetAction(ClinicHubAction.Idle);
            }

            onPhoneClosed?.Invoke();
        }

        public void OpenPhoneFromInteraction()
        {
            OpenPhone();
        }

        public void RefreshAfterTaskUpdate()
        {
            if (!IsOpen())
            {
                return;
            }

            BuildContactList();
            if (tasks.Count > 0)
            {
                SelectTask(Mathf.Clamp(_currentTaskIndex, 0, tasks.Count - 1));
            }
        }

        private bool IsOpen()
        {
            if (panelCanvasGroup != null)
            {
                return panelCanvasGroup.alpha > 0.001f;
            }

            return panelRoot != null && panelRoot.activeSelf;
        }

        private void BuildContactList()
        {
            if (contactContentRoot == null || contactItemPrefab == null)
            {
                return;
            }

            for (int i = contactContentRoot.childCount - 1; i >= 0; i--)
            {
                Destroy(contactContentRoot.GetChild(i).gameObject);
            }

            _contactItems.Clear();

            for (int i = 0; i < tasks.Count; i++)
            {
                PhoneTaskData task = tasks[i];
                if (task == null)
                {
                    continue;
                }

                var item = Instantiate(contactItemPrefab, contactContentRoot);
                item.Setup(i, task, SelectTask);
                _contactItems.Add(item);
            }
        }

        private void SelectTask(int index)
        {
            if (tasks == null || tasks.Count == 0)
            {
                return;
            }

            if (index < 0 || index >= tasks.Count)
            {
                return;
            }

            _currentTaskIndex = index;
            PhoneTaskData task = tasks[index];
            if (task == null)
            {
                return;
            }

            if (chatHeaderText != null)
            {
                chatHeaderText.text = task.displayName;
            }

            for (int i = 0; i < _contactItems.Count; i++)
            {
                _contactItems[i].SetSelected(i == _currentTaskIndex, contactNormalBackground, contactSelectedBackground);
            }

            BuildMessages(task);
            UpdateDecisionButtons(task);
        }

        private void BuildMessages(PhoneTaskData task)
        {
            if (messageContentRoot == null)
            {
                return;
            }

            for (int i = messageContentRoot.childCount - 1; i >= 0; i--)
            {
                Destroy(messageContentRoot.GetChild(i).gameObject);
            }

            if (task == null || task.messages == null)
            {
                StartCoroutine(ScrollToBottomOnNextFrame());
                return;
            }

            for (int i = 0; i < task.messages.Count; i++)
            {
                PhoneMessageData data = task.messages[i];
                PhoneMessageItemUI prefab = data != null && data.sender == PhoneSender.Doctor
                    ? doctorMessagePrefab
                    : patientMessagePrefab;

                if (prefab == null)
                {
                    continue;
                }

                var item = Instantiate(prefab, messageContentRoot);
                item.Setup(data);
            }

            StartCoroutine(ScrollToBottomOnNextFrame());
        }

        private void UpdateDecisionButtons(PhoneTaskData task)
        {
            bool show = task != null && task.requiresDecision;
            if (decisionRoot != null)
            {
                decisionRoot.SetActive(show);
            }
        }

        private IEnumerator ScrollToBottomOnNextFrame()
        {
            yield return null;
            Canvas.ForceUpdateCanvases();

            if (messageScrollRect != null)
            {
                messageScrollRect.verticalNormalizedPosition = 0f;
            }
        }

        private void HandleYesClicked()
        {
            onDecisionYes?.Invoke();
            HandleDecision(isYes: true);
        }

        private void HandleNoClicked()
        {
            onDecisionNo?.Invoke();
            HandleDecision(isYes: false);
        }

        private void HandleDecision(bool isYes)
        {
            PhoneTaskData task = GetCurrentTask();
            string targetScene = isYes
                ? (!string.IsNullOrEmpty(task != null ? task.yesSceneName : null) ? task.yesSceneName : fallbackYesSceneName)
                : (!string.IsNullOrEmpty(task != null ? task.noSceneName : null) ? task.noSceneName : fallbackNoSceneName);

            if (autoCloseOnDecision)
            {
                ClosePhone();
            }

            if (string.IsNullOrEmpty(targetScene))
            {
                return;
            }

            if (sceneTransition != null)
            {
                sceneTransition.LoadScene(targetScene);
            }
            else
            {
                SceneManager.LoadScene(targetScene);
            }
        }

        private PhoneTaskData GetCurrentTask()
        {
            if (tasks == null || tasks.Count == 0)
            {
                return null;
            }

            if (_currentTaskIndex < 0 || _currentTaskIndex >= tasks.Count)
            {
                return null;
            }

            return tasks[_currentTaskIndex];
        }

        private void SetPanelVisible(bool visible)
        {
            if (panelRoot != null)
            {
                panelRoot.SetActive(visible);
            }

            if (panelCanvasGroup == null)
            {
                return;
            }

            panelCanvasGroup.alpha = visible ? 1f : 0f;
            panelCanvasGroup.blocksRaycasts = visible;
            panelCanvasGroup.interactable = visible;
        }
    }
}
