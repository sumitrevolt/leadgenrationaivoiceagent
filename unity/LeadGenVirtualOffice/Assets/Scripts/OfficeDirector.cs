// Scene director: wires HostBridge state → RoomLayout + agent beacons + selection camera.
// Attach to the "Bridge" GameObject in Bootstrap/AdminBlueprintOffice along with HostBridge.
// Honesty rules: renders ONLY what the snapshot contains; empty snapshot → EmptyState label,
// stale flag comes from the shell; no idle "activity theater".
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace LeadGen.Office
{
    [RequireComponent(typeof(HostBridge))]
    public class OfficeDirector : MonoBehaviour
    {
        private HostBridge _bridge;
        private RoomLayout _layout;
        private readonly Dictionary<string, GameObject> _agents = new();
        private Snapshot _snap;

        private void Awake()
        {
            _bridge = GetComponent<HostBridge>();
            var layoutGo = new GameObject("Floor");
            _layout = layoutGo.AddComponent<RoomLayout>();
            _bridge.OnState += Apply;
            _bridge.OnHostSelect += FocusSelection;
            if (Camera.main != null) Camera.main.backgroundColor = StatusPalette.Bg;
        }

        private void Apply(Snapshot snap)
        {
            _snap = snap;
            _layout.Build(snap);

            // room tint = worst agent status in room (failed > waiting > processing > idle)
            foreach (var grp in snap.agents.Where(a => a != null && !string.IsNullOrEmpty(a.room))
                                           .GroupBy(a => a.room))
            {
                var worst = grp.OrderByDescending(a => Rank(a.status)).First().status;
                _layout.SetRoomStatusTint(grp.Key, worst);
            }

            // agent beacons: one small sphere per agent at a stable desk slot in its room
            foreach (var a in snap.agents)
            {
                if (a == null || string.IsNullOrEmpty(a.key)) continue;
                if (!_agents.TryGetValue(a.key, out var go))
                {
                    go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                    go.name = $"Agent::{a.key}";
                    go.transform.localScale = Vector3.one * 0.35f;
                    _agents[a.key] = go;
                }
                var room = _layout.Get(a.room);
                if (room != null)
                {
                    var slot = StableSlot(a.key, room.transform);
                    go.transform.position = slot;
                }
                go.GetComponent<MeshRenderer>().material.color = StatusPalette.ForStatus(a.status);
            }

            // remove beacons for agents no longer present (truthful roster)
            var live = new HashSet<string>(snap.agents.Where(a => a != null).Select(a => a.key));
            foreach (var dead in _agents.Keys.Where(k => !live.Contains(k)).ToList())
            {
                Destroy(_agents[dead]);
                _agents.Remove(dead);
            }
        }

        private static int Rank(string status)
        {
            var c = StatusPalette.ForStatus(status);
            if (c == StatusPalette.Failed) return 4;
            if (c == StatusPalette.Retry) return 3;
            if (c == StatusPalette.Waiting) return 2;
            if (c == StatusPalette.Processing) return 1;
            return 0;
        }

        private static Vector3 StableSlot(string key, Transform room)
        {
            // deterministic hash → grid slot inside room bounds so desks never shuffle between polls
            int h = 17;
            foreach (var ch in key) h = h * 31 + ch;
            var w = room.localScale.x; var d = room.localScale.z;
            var cols = Mathf.Max(1, Mathf.FloorToInt(w / 1.2f));
            var idx = Mathf.Abs(h) % Mathf.Max(1, cols * Mathf.Max(1, Mathf.FloorToInt(d / 1.2f)));
            var cx = idx % cols; var cz = idx / cols;
            return room.position + new Vector3(-w / 2f + 0.8f + cx * 1.2f, 0.35f, d / 2f - 0.8f - cz * 1.2f);
        }

        private void FocusSelection(string kind, string id)
        {
            Transform target = null;
            if (kind == "room") target = _layout.Get(id)?.transform;
            else if (kind == "agent" && _agents.TryGetValue(id, out var go)) target = go.transform;
            if (target == null || Camera.main == null) return;
            var cam = Camera.main.transform;
            cam.position = target.position + new Vector3(0f, 9f, -7f);
            cam.LookAt(target.position);
        }

        // click-to-select → notify host (host updates panel + minimap; loop-guarded by origin)
        private void Update()
        {
            if (!Input.GetMouseButtonDown(0) || Camera.main == null) return;
            var ray = Camera.main.ScreenPointToRay(Input.mousePosition);
            if (!Physics.Raycast(ray, out var hit, 200f)) return;
            var n = hit.collider.gameObject.name;
            if (n.StartsWith("Room::")) _bridge.SelectRoom(n.Substring(6));
            else if (n.StartsWith("Agent::")) _bridge.SelectAgent(n.Substring(7));
        }
    }
}
