using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace RetinalPrototype
{
    [RequireComponent(typeof(RectTransform))]
    public sealed class SurgeryFundusInteractionOverlay : MonoBehaviour, IPointerDownHandler, IDragHandler, IPointerUpHandler, IPointerMoveHandler
    {
        public event Action<Vector2> FireClicked;
        public event Action<Vector2, Vector2> CalibrationLineFinished;
        public event Action<Vector2> PointerMoved;

        private RectTransform _rect;
        private bool _calibrationMode;
        private bool _isDragging;
        private Vector2 _dragStart;
        private Vector2 _dragCurrent;

        private RectTransform _line;
        private RectTransform _startDot;
        private RectTransform _endDot;

        private void Awake()
        {
            _rect = GetComponent<RectTransform>();
            CreateVisuals();
            HideCalibrationVisuals();
        }

        public void SetCalibrationMode(bool enabled)
        {
            _calibrationMode = enabled;
            if (!enabled)
            {
                _isDragging = false;
                HideCalibrationVisuals();
            }
        }

        public void OnPointerDown(PointerEventData eventData)
        {
            if (!TryGetLocalPoint(eventData, out var local))
            {
                return;
            }

            if (_calibrationMode)
            {
                _isDragging = true;
                _dragStart = local;
                _dragCurrent = local;
                UpdateCalibrationVisuals();
                return;
            }

            FireClicked?.Invoke(local);
        }

        public void OnDrag(PointerEventData eventData)
        {
            if (!_calibrationMode || !_isDragging)
            {
                return;
            }

            if (!TryGetLocalPoint(eventData, out var local))
            {
                return;
            }

            _dragCurrent = local;
            UpdateCalibrationVisuals();
        }

        public void OnPointerUp(PointerEventData eventData)
        {
            if (!_calibrationMode || !_isDragging)
            {
                return;
            }

            _isDragging = false;
            if (!TryGetLocalPoint(eventData, out var local))
            {
                HideCalibrationVisuals();
                return;
            }

            _dragCurrent = local;
            UpdateCalibrationVisuals();

            var distance = Vector2.Distance(_dragStart, _dragCurrent);
            if (distance > 10f)
            {
                CalibrationLineFinished?.Invoke(_dragStart, _dragCurrent);
            }

            SetCalibrationMode(false);
        }

        public void OnPointerMove(PointerEventData eventData)
        {
            if (!TryGetLocalPoint(eventData, out var local))
            {
                return;
            }

            PointerMoved?.Invoke(local);
        }

        private bool TryGetLocalPoint(PointerEventData eventData, out Vector2 localPoint)
        {
            return RectTransformUtility.ScreenPointToLocalPointInRectangle(
                _rect,
                eventData.position,
                eventData.pressEventCamera,
                out localPoint);
        }

        private void CreateVisuals()
        {
            _line = CreateVisual("CalibrationLine", new Vector2(1f, 2f));
            _startDot = CreateVisual("CalibrationStart", new Vector2(8f, 8f));
            _endDot = CreateVisual("CalibrationEnd", new Vector2(8f, 8f));

            _line.GetComponent<Image>().color = new Color(0.2f, 0.95f, 0.4f, 0.95f);
            _startDot.GetComponent<Image>().color = new Color(0.12f, 0.90f, 0.32f, 0.98f);
            _endDot.GetComponent<Image>().color = new Color(0.12f, 0.90f, 0.32f, 0.98f);
        }

        private RectTransform CreateVisual(string name, Vector2 size)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(transform, false);
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.5f, 0.5f);
            rt.anchorMax = new Vector2(0.5f, 0.5f);
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.sizeDelta = size;
            return rt;
        }

        private void UpdateCalibrationVisuals()
        {
            _line.gameObject.SetActive(true);
            _startDot.gameObject.SetActive(true);
            _endDot.gameObject.SetActive(true);

            var delta = _dragCurrent - _dragStart;
            var length = Mathf.Max(1f, delta.magnitude);
            var center = (_dragStart + _dragCurrent) * 0.5f;
            var angle = Mathf.Atan2(delta.y, delta.x) * Mathf.Rad2Deg;

            _line.anchoredPosition = center;
            _line.sizeDelta = new Vector2(length, 2f);
            _line.localRotation = Quaternion.Euler(0f, 0f, angle);

            _startDot.anchoredPosition = _dragStart;
            _endDot.anchoredPosition = _dragCurrent;
        }

        private void HideCalibrationVisuals()
        {
            _line.gameObject.SetActive(false);
            _startDot.gameObject.SetActive(false);
            _endDot.gameObject.SetActive(false);
        }
    }
}
