// Customer Blueprint Office — journey-zone scene director (Milestone E).
// Renders the tenant-scoped CustomerState DTO pushed by the CUSTOMER shell:
//   Setup → Brand → Content → Approval → Social → Reports  (six zones in a row)
// plus a Delivery Shelf (one item per entitled deliverable, status-colored, ledger truth).
// Honesty rules: renders ONLY DTO contents; no admin data, no invented counts, no fake activity.
using System.Collections.Generic;
using UnityEngine;

namespace LeadGen.Office
{
    [RequireComponent(typeof(HostBridge))]
    public class CustomerDirector : MonoBehaviour
    {
        // Journey zones: id → column index. Light "AI Office" palette (style guide §4).
        private static readonly (string id, string label)[] Zones =
        {
            ("setup", "Setup"), ("brand", "Brand"), ("content", "Content"),
            ("approval", "Approvals"), ("social", "Social"), ("reports", "Reports"),
        };
        private const float ZoneW = 4.5f, ZoneD = 6f, ZoneGap = 0.5f;

        private HostBridge _bridge;
        private readonly Dictionary<string, GameObject> _zones = new();
        private readonly Dictionary<string, GameObject> _shelfItems = new();
        private CustomerState _state;

        private void Awake()
        {
            _bridge = GetComponent<HostBridge>();
            _bridge.OnCustomerState += Apply;
            if (Camera.main != null) Camera.main.backgroundColor = new Color(0.965f, 0.965f, 0.984f); // --bg-soft #f6f6fb
            BuildZones();
        }

        private void BuildZones()
        {
            for (int i = 0; i < Zones.Length; i++)
            {
                var (id, label) = Zones[i];
                if (_zones.ContainsKey(id)) continue;
                var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
                go.name = $"Zone::{id}";
                go.transform.SetParent(transform, false);
                go.transform.localScale = new Vector3(ZoneW, 0.05f, ZoneD);
                go.transform.localPosition = new Vector3(i * (ZoneW + ZoneGap), 0f, 0f);
                go.GetComponent<MeshRenderer>().material.color = Color.white;
                _zones[id] = go;
            }
        }

        private void Apply(CustomerState state)
        {
            _state = state;

            // zone tint: journey progress — setup zone reflects setup_pct, approval zone reflects queue
            Tint("setup", state.setup_pct >= 100 ? StatusPalette.Healthy
                : state.setup_pct > 0 ? StatusPalette.Processing : StatusPalette.Idle);
            Tint("approval", state.approvals_pending > 0 ? StatusPalette.Waiting : StatusPalette.Healthy);
            var socialOk = state.social.Exists(s => s != null && s.status == "connected");
            var socialPending = state.social.Exists(s => s != null && s.status == "provider_review_pending");
            Tint("social", socialOk ? StatusPalette.Healthy : socialPending ? StatusPalette.Waiting : StatusPalette.Idle);
            Tint("reports", state.report_health == "green" ? StatusPalette.Healthy
                : state.report_health == "red" ? StatusPalette.Failed
                : state.report_health == "yellow" ? StatusPalette.Waiting : StatusPalette.Idle);

            // Delivery Shelf: one small cube per REAL deliverable from the DTO (ledger truth)
            var live = new HashSet<string>();
            for (int i = 0; i < state.deliverables.Count && i < 32; i++) // bounded object count
            {
                var d = state.deliverables[i];
                if (d == null || string.IsNullOrEmpty(d.id)) continue;
                live.Add(d.id);
                if (!_shelfItems.TryGetValue(d.id, out var go))
                {
                    go = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    go.name = $"Deliverable::{d.id}";
                    go.transform.SetParent(transform, false);
                    go.transform.localScale = Vector3.one * 0.5f;
                    _shelfItems[d.id] = go;
                }
                go.transform.localPosition = new Vector3((i % 8) * 0.7f + 8f, 0.4f, -ZoneD / 2f - 1.5f - (i / 8) * 0.7f);
                go.GetComponent<MeshRenderer>().material.color = DeliverableColor(d.status);
            }
            foreach (var dead in new List<string>(_shelfItems.Keys))
                if (!live.Contains(dead)) { Destroy(_shelfItems[dead]); _shelfItems.Remove(dead); }
        }

        private static Color DeliverableColor(string status)
        {
            switch ((status ?? "").ToLowerInvariant())
            {
                case "done": case "completed": return StatusPalette.Healthy;
                case "in_progress": return StatusPalette.Processing;
                case "waiting_customer": case "waiting for customer": return StatusPalette.Waiting;
                case "blocked": return StatusPalette.Failed;
                default: return StatusPalette.Idle; // not_started/unknown — never fake green
            }
        }

        private void Tint(string zoneId, Color c)
        {
            if (_zones.TryGetValue(zoneId, out var go))
                go.GetComponent<MeshRenderer>().material.color = Color.Lerp(Color.white, c, 0.35f);
        }

        // click → allowlisted action for the zone (routes fixed in the shell)
        private void Update()
        {
            if (!Input.GetMouseButtonDown(0) || Camera.main == null) return;
            var ray = Camera.main.ScreenPointToRay(Input.mousePosition);
            if (!Physics.Raycast(ray, out var hit, 200f)) return;
            var n = hit.collider.gameObject.name;
            if (!n.StartsWith("Zone::")) return;
            switch (n.Substring(6))
            {
                case "setup": _bridge.Invoke("open_setup"); break;
                case "brand": _bridge.Invoke("open_setup"); break;
                case "content": _bridge.Invoke("open_approval"); break;
                case "approval": _bridge.Invoke("open_approval"); break;
                case "social": _bridge.Invoke("open_social_connect"); break;
                case "reports": _bridge.Invoke("open_reports"); break;
            }
        }
    }
}
