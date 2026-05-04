using UnityEngine;

namespace RetinalPrototype.Hub
{
    public sealed class ClinicHubReturnState : MonoBehaviour
    {
        private static ClinicHubReturnState _instance;

        private bool _hasReturnPose;
        private Vector3 _returnPosition;
        private bool _returnFacingRight;

        public static bool HasReturnPose => _instance != null && _instance._hasReturnPose;
        public static Vector3 ReturnPosition => _instance != null ? _instance._returnPosition : Vector3.zero;
        public static bool ReturnFacingRight => _instance == null || _instance._returnFacingRight;

        private void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }

            _instance = this;
            DontDestroyOnLoad(gameObject);
        }

        public static void SavePose(Vector3 position, bool facingRight)
        {
            EnsureInstance();
            _instance._returnPosition = position;
            _instance._returnFacingRight = facingRight;
            _instance._hasReturnPose = true;
        }

        public static void ConsumePose(ClinicHubPlayerController player)
        {
            if (player == null || !HasReturnPose)
            {
                return;
            }

            player.SnapTo(_instance._returnPosition);
            player.SetFacingRight(_instance._returnFacingRight);
            player.SetAction(ClinicHubAction.Idle);
            player.SetInputLocked(false);
            _instance._hasReturnPose = false;
        }

        private static void EnsureInstance()
        {
            if (_instance != null)
            {
                return;
            }

            var stateObject = new GameObject(nameof(ClinicHubReturnState));
            _instance = stateObject.AddComponent<ClinicHubReturnState>();
        }
    }
}
