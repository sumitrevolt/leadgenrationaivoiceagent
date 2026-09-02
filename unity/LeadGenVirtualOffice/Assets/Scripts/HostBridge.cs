// The ONLY Unity↔browser boundary. Inbound: shell calls SendMessage("Bridge","OnHostEvent",json).
// Outbound: allowlisted actions via LG_BRIDGE (Plugins/WebGL/HostBridge.jslib).
// SECURITY: no tokens, no URLs, no free-form JS — see docs/UNITY_VIRTUAL_OFFICE_SECURITY.md §3.
using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace LeadGen.Office
{
    public class HostBridge : MonoBehaviour
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] private static extern void LG_BridgeInvoke(string payloadJson);
#else
        private static void LG_BridgeInvoke(string payloadJson) =>
            Debug.Log($"[HostBridge] (editor stub) invoke: {payloadJson}");
#endif

        public event Action<Snapshot> OnState;
        public event Action<CustomerState> OnCustomerState;
        public event Action<string, string> OnHostSelect; // kind, id

        // Called by the web shell via unityInstance.SendMessage("Bridge","OnHostEvent", json)
        public void OnHostEvent(string json)
        {
            HostEvent evt = null;
            try { evt = JsonUtility.FromJson<HostEvent>(json); } catch { /* malformed → ignore */ }
            if (evt == null || string.IsNullOrEmpty(evt.type)) return;

            switch (evt.type)
            {
                case "state" when evt.snapshot != null:
                    OnState?.Invoke(evt.snapshot);
                    break;
                case "customer_state" when evt.customer != null:
                    OnCustomerState?.Invoke(evt.customer);
                    break;
                case "select" when evt.origin == "host": // loop guard: only host-origin applied
                    OnHostSelect?.Invoke(evt.kind ?? "", evt.id ?? "");
                    break;
            }
        }

        // ---- outbound (allowlist mirrors docs/UNITY_OFFICE_API_CONTRACT.md §4) ----
        private static readonly string[] Allowed =
        {
            "open_command_center", "open_customer_360", "open_delivery_proof", "open_approval",
            "open_setup", "open_reports", "open_social_connect", "open_billing", "open_support",
            "open_agent_details", "refresh_office_state",
        };

        public void Invoke(string action, string id = null)
        {
            if (Array.IndexOf(Allowed, action) < 0)
            {
                Debug.LogWarning($"[HostBridge] blocked non-allowlisted action '{action}'");
                return;
            }
            var idPart = string.IsNullOrEmpty(id) ? "" : $",\"id\":\"{Sanitize(id)}\"";
            LG_BridgeInvoke($"{{\"action\":\"{action}\"{idPart},\"origin\":\"unity\"}}");
        }

        public void SelectRoom(string id)  => EmitSelect("room", id);
        public void SelectAgent(string id) => EmitSelect("agent", id);

        private static void EmitSelect(string kind, string id)
        {
            var s = Sanitize(id);
            if (string.IsNullOrEmpty(s)) return;
#if UNITY_WEBGL && !UNITY_EDITOR
            LG_SelectInHost(kind, s);
#else
            Debug.Log($"[HostBridge] (editor stub) select {kind}:{s}");
#endif
        }

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] private static extern void LG_SelectInHost(string kind, string id);
#endif

        private static string Sanitize(string id)
        {
            if (string.IsNullOrEmpty(id) || id.Length > 64) return null;
            foreach (var c in id)
                if (!char.IsLetterOrDigit(c) && c != '_' && c != '-' && c != '.') return null;
            return id;
        }
    }
}
