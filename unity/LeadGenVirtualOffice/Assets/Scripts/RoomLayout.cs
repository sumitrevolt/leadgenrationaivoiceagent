// Builds the 8-room floor at runtime from snapshot.rooms + the canonical geometry mapping.
// Geometry: docs/OFFICE_MAP_UNITY_MAPPING.md §1 — 2D px (office_map OFFICE.ROOMS) × 0.025 = meters.
// Rooms come from the API; this table holds ONLY placement for known canonical ids.
// If the API ever sends a room id not in this table, it is laid out in an overflow row —
// never dropped, never invented.
using System.Collections.Generic;
using UnityEngine;

namespace LeadGen.Office
{
    public class RoomLayout : MonoBehaviour
    {
        public const float Scale = 0.025f; // 1 px → 0.025 m (30 m × 20.5 m floor)

        // id → (x, y, w, h) in 2D px, mirror of office_map.html:873-881.
        private static readonly Dictionary<string, Vector4> Geom = new()
        {
            { "coordinator",          new Vector4(0,   0,   1200, 120) },
            { "lead_lab",             new Vector4(0,   120, 300,  350) },
            { "sales_crm",            new Vector4(300, 120, 300,  350) },
            { "voice_team",           new Vector4(600, 120, 300,  350) },
            { "marketing_team",       new Vector4(900, 120, 300,  350) },
            { "qa_audit",             new Vector4(0,   470, 250,  350) },
            { "platform_engineering", new Vector4(250, 470, 700,  350) },
            { "admin_finance",        new Vector4(950, 470, 250,  350) },
        };

        private readonly Dictionary<string, GameObject> _rooms = new();
        private int _overflow;

        public void Build(Snapshot snap)
        {
            foreach (var room in snap.rooms)
            {
                if (room == null || string.IsNullOrEmpty(room.id) || _rooms.ContainsKey(room.id)) continue;
                var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
                go.name = $"Room::{room.id}";
                go.transform.SetParent(transform, false);

                Vector4 g;
                if (!Geom.TryGetValue(room.id, out g))
                {   // unknown room from API → overflow strip below the floor, visible + labeled
                    g = new Vector4(_overflow * 320, 880, 300, 200);
                    _overflow++;
                }
                var w = g.z * Scale; var d = g.w * Scale;
                go.transform.localScale = new Vector3(w, 0.05f, d);
                go.transform.localPosition = new Vector3((g.x + g.z / 2f) * Scale, 0f, -(g.y + g.w / 2f) * Scale);

                var mr = go.GetComponent<MeshRenderer>();
                mr.material.color = StatusPalette.Panel;
                _rooms[room.id] = go;
            }
        }

        public void SetRoomStatusTint(string roomId, string worstStatus)
        {
            if (!_rooms.TryGetValue(roomId, out var go)) return;
            var baseCol = StatusPalette.Panel;
            var tint = StatusPalette.ForStatus(worstStatus);
            go.GetComponent<MeshRenderer>().material.color = Color.Lerp(baseCol, tint, 0.25f);
        }

        public GameObject Get(string roomId) => _rooms.TryGetValue(roomId, out var go) ? go : null;
    }
}
