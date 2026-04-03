using UnityEngine;
using UnityEngine.SceneManagement;

namespace RetinalPrototype
{
    public static class SurgeryPanelRuntimeInjector
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void InjectPanelAfterSceneLoad()
        {
            var scene = SceneManager.GetActiveScene();
            if (scene.name != PrototypeSceneNames.SurgerySimulation)
            {
                return;
            }

            // Scene builder already creates full UI. Runtime path only restores missing links.
            var panel = Object.FindFirstObjectByType<SurgeryLaserControlPanelController>();
            if (panel == null)
            {
                return;
            }

            var renderer = Object.FindFirstObjectByType<SurgeryLaserSpotRenderer>();
            if (renderer == null)
            {
                var host = new GameObject("SurgeryLaserSpotRenderer");
                host.AddComponent<SurgeryLaserSpotRenderer>();
            }
        }
    }
}
