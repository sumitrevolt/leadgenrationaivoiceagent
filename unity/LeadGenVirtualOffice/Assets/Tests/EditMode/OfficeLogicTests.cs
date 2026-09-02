// EditMode tests — DTO parsing, status palette, room layout, bridge hardening.
// Run: Unity Test Runner (EditMode) or CLI -runTests -testPlatform EditMode.
using System.Collections.Generic;
using LeadGen.Office;
using NUnit.Framework;
using UnityEngine;

namespace LeadGen.Office.Tests
{
    public class StatusPaletteTests
    {
        [TestCase("failed", "failed")]
        [TestCase("ERROR", "failed")]
        [TestCase("critical", "failed")]
        [TestCase("retry", "retry")]
        [TestCase("waiting", "waiting")]
        [TestCase("blocked", "waiting")]
        [TestCase("reviewing", "waiting")]
        [TestCase("working", "processing")]
        [TestCase("running", "processing")]
        [TestCase("healthy", "healthy")]
        [TestCase("done", "healthy")]
        [TestCase("offline", "idle")]
        [TestCase("", "idle")]
        [TestCase(null, "idle")]
        [TestCase("totally-unknown", "idle")]
        public void ForStatus_maps_to_canonical_colors(string status, string expected)
        {
            var c = StatusPalette.ForStatus(status);
            var map = new Dictionary<string, Color>
            {
                { "failed", StatusPalette.Failed }, { "retry", StatusPalette.Retry },
                { "waiting", StatusPalette.Waiting }, { "processing", StatusPalette.Processing },
                { "healthy", StatusPalette.Healthy }, { "idle", StatusPalette.Idle },
            };
            Assert.AreEqual(map[expected], c, $"status '{status}' should map to {expected}");
        }

        [Test]
        public void Unknown_status_is_never_fake_green()
        {
            Assert.AreNotEqual(StatusPalette.Healthy, StatusPalette.ForStatus("mystery"));
            Assert.AreNotEqual(StatusPalette.Healthy, StatusPalette.ForStatus(null));
        }
    }

    public class HostEventParsingTests
    {
        [Test]
        public void State_event_parses_snapshot()
        {
            var json = "{\"type\":\"state\",\"origin\":\"host\",\"snapshot\":{\"rooms\":[{\"id\":\"voice_team\",\"label\":\"Voice\"}]," +
                       "\"agents\":[{\"key\":\"a1\",\"name\":\"Isha\",\"room\":\"voice_team\",\"status\":\"working\",\"task\":\"t\"}]}}";
            var evt = JsonUtility.FromJson<HostEvent>(json);
            Assert.AreEqual("state", evt.type);
            Assert.AreEqual(1, evt.snapshot.rooms.Count);
            Assert.AreEqual("voice_team", evt.snapshot.rooms[0].id);
            Assert.AreEqual("working", evt.snapshot.agents[0].status);
        }

        [Test]
        public void Customer_state_event_parses_dto()
        {
            var json = "{\"type\":\"customer_state\",\"origin\":\"host\",\"customer\":{\"business_name\":\"B\",\"setup_pct\":40," +
                       "\"approvals_pending\":2,\"deliverables\":[{\"id\":\"d1\",\"label\":\"Post\",\"status\":\"done\"}]," +
                       "\"social\":[{\"platform\":\"instagram\",\"status\":\"connected\"}]}}";
            var evt = JsonUtility.FromJson<HostEvent>(json);
            Assert.AreEqual("customer_state", evt.type);
            Assert.AreEqual(40, evt.customer.setup_pct);
            Assert.AreEqual("done", evt.customer.deliverables[0].status);
            Assert.AreEqual("connected", evt.customer.social[0].status);
        }

        [Test]
        public void Malformed_and_unknown_fields_do_not_throw()
        {
            Assert.DoesNotThrow(() => JsonUtility.FromJson<HostEvent>("{\"type\":\"state\",\"unknown_field\":123}"));
            Assert.DoesNotThrow(() => JsonUtility.FromJson<HostEvent>("{}"));
        }
    }

    public class RoomLayoutTests
    {
        private static Snapshot Snap(params string[] roomIds)
        {
            var s = new Snapshot();
            foreach (var id in roomIds) s.rooms.Add(new Room { id = id, label = id });
            return s;
        }

        [Test]
        public void Builds_known_rooms_at_mapped_positions()
        {
            var go = new GameObject("layout-test");
            try
            {
                var layout = go.AddComponent<RoomLayout>();
                layout.Build(Snap("coordinator", "lead_lab"));
                var coord = layout.Get("coordinator");
                Assert.IsNotNull(coord);
                // coordinator: x,y,w,h = 0,0,1200,120 → center (15.0, -1.5), scale (30, ., 3)
                Assert.AreEqual(30f, coord.transform.localScale.x, 0.001f);
                Assert.AreEqual(3f, coord.transform.localScale.z, 0.001f);
                Assert.AreEqual(15f, coord.transform.localPosition.x, 0.001f);
            }
            finally { Object.DestroyImmediate(go); }
        }

        [Test]
        public void Build_is_idempotent_no_duplicates()
        {
            var go = new GameObject("layout-test2");
            try
            {
                var layout = go.AddComponent<RoomLayout>();
                layout.Build(Snap("coordinator"));
                layout.Build(Snap("coordinator"));
                int count = 0;
                foreach (Transform child in go.transform)
                    if (child.name == "Room::coordinator") count++;
                Assert.AreEqual(1, count, "re-Build must not duplicate rooms");
            }
            finally { Object.DestroyImmediate(go); }
        }

        [Test]
        public void Unknown_room_goes_to_overflow_not_dropped()
        {
            var go = new GameObject("layout-test3");
            try
            {
                var layout = go.AddComponent<RoomLayout>();
                layout.Build(Snap("brand_new_dept"));
                var room = layout.Get("brand_new_dept");
                Assert.IsNotNull(room, "unknown rooms must render in overflow, never dropped");
                Assert.Greater(-room.transform.localPosition.z, 20f, "overflow strip sits below the floor");
            }
            finally { Object.DestroyImmediate(go); }
        }
    }
}
