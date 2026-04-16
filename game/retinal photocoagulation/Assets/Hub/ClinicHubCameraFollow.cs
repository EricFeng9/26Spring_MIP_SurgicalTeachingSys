using UnityEngine;

namespace RetinalPrototype.Hub
{
    public sealed class ClinicHubCameraFollow : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private float smoothTime = 0.15f;
        [SerializeField] private bool followX = true;
        [SerializeField] private bool followY;
        [SerializeField] private Vector2 minXY = new Vector2(-100f, -100f);
        [SerializeField] private Vector2 maxXY = new Vector2(100f, 100f);

        private Vector3 _velocity;

        private void LateUpdate()
        {
            if (target == null)
            {
                return;
            }

            Vector3 current = transform.position;
            Vector3 desired = current;

            if (followX)
            {
                desired.x = target.position.x;
            }

            if (followY)
            {
                desired.y = target.position.y;
            }

            desired.x = Mathf.Clamp(desired.x, minXY.x, maxXY.x);
            desired.y = Mathf.Clamp(desired.y, minXY.y, maxXY.y);

            transform.position = Vector3.SmoothDamp(current, desired, ref _velocity, Mathf.Max(0.01f, smoothTime));
        }
    }
}
