using UnityEngine;

namespace RetinalPrototype
{
    public static class PrototypeSaveSystem
    {
        private const string CurrentSlotKey = "Prototype.CurrentSlot";
        private const string SlotKeyPrefix = "Prototype.SaveSlot.";
        private const int MinSlot = 1;
        private const int MaxSlot = 3;

        public static int CurrentSlot
        {
            get => PlayerPrefs.GetInt(CurrentSlotKey, -1);
            private set
            {
                PlayerPrefs.SetInt(CurrentSlotKey, value);
                PlayerPrefs.Save();
            }
        }

        public static int SlotCount => MaxSlot;

        public static bool HasAnySave()
        {
            for (var i = MinSlot; i <= MaxSlot; i++)
            {
                if (HasSave(i))
                {
                    return true;
                }
            }

            return false;
        }

        public static bool HasSave(int slotIndex)
        {
            if (!IsValidSlot(slotIndex))
            {
                return false;
            }

            return PlayerPrefs.GetInt(GetSlotKey(slotIndex), 0) == 1;
        }

        public static void ActivateSlot(int slotIndex)
        {
            if (!IsValidSlot(slotIndex))
            {
                Debug.LogWarning($"Invalid slot index: {slotIndex}");
                return;
            }

            PlayerPrefs.SetInt(GetSlotKey(slotIndex), 1);
            CurrentSlot = slotIndex;
            PlayerPrefs.Save();
        }

        public static void ClearSlot(int slotIndex)
        {
            if (!IsValidSlot(slotIndex))
            {
                Debug.LogWarning($"Invalid slot index: {slotIndex}");
                return;
            }

            PlayerPrefs.DeleteKey(GetSlotKey(slotIndex));
            if (CurrentSlot == slotIndex)
            {
                CurrentSlot = -1;
            }

            PlayerPrefs.Save();
        }

        private static bool IsValidSlot(int slotIndex)
        {
            return slotIndex >= MinSlot && slotIndex <= MaxSlot;
        }

        private static string GetSlotKey(int slotIndex)
        {
            return SlotKeyPrefix + slotIndex;
        }
    }
}
