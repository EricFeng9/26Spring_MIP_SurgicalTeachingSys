using System.Collections.Generic;
using TMPro;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    public sealed class TreatmentParameterPanelController : MonoBehaviour
    {
        [SerializeField] private GameObject panelRoot;
        [SerializeField] private TMP_Text titleText;
        [SerializeField] private RecordImageSlot imageSlot;
        [SerializeField] private RecordTextSlot descriptionText;

        private readonly List<TreatmentParameterSnapshot> _snapshots = new List<TreatmentParameterSnapshot>();
        private int _currentIndex;

        private void Awake()
        {
            if (panelRoot != null)
            {
                panelRoot.SetActive(false);
            }
        }

        public void SetSnapshots(IList<TreatmentParameterSnapshot> snapshots)
        {
            _snapshots.Clear();
            if (snapshots != null)
            {
                _snapshots.AddRange(snapshots);
            }

            _currentIndex = 0;
            Refresh();
        }

        public void Open()
        {
            if (panelRoot != null)
            {
                panelRoot.SetActive(true);
            }

            Refresh();
        }

        public void Close()
        {
            if (panelRoot != null)
            {
                panelRoot.SetActive(false);
            }
        }

        public void ShowNext()
        {
            if (_snapshots.Count == 0)
            {
                return;
            }

            _currentIndex = (_currentIndex + 1) % _snapshots.Count;
            Refresh();
        }

        public void ShowPrevious()
        {
            if (_snapshots.Count == 0)
            {
                return;
            }

            _currentIndex = (_currentIndex - 1 + _snapshots.Count) % _snapshots.Count;
            Refresh();
        }

        private void Refresh()
        {
            if (_snapshots.Count == 0)
            {
                if (titleText != null)
                {
                    titleText.text = "暂无参数记录";
                }

                if (imageSlot != null)
                {
                    imageSlot.SetSprite(null);
                }

                if (descriptionText != null)
                {
                    descriptionText.SetText("本次手术暂无可展示的参数截图。");
                }

                return;
            }

            TreatmentParameterSnapshot snapshot = _snapshots[_currentIndex];
            if (titleText != null)
            {
                titleText.text = string.IsNullOrWhiteSpace(snapshot.title)
                    ? $"参数截图 {_currentIndex + 1}/{_snapshots.Count}"
                    : $"{snapshot.title}  {_currentIndex + 1}/{_snapshots.Count}";
            }

            if (imageSlot != null)
            {
                imageSlot.SetSprite(snapshot.image);
            }

            if (descriptionText != null)
            {
                descriptionText.SetText(snapshot.description);
            }
        }
    }
}
