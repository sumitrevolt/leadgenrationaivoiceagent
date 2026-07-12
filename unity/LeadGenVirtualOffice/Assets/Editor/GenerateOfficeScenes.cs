// Idempotent, programmatic scene generation for the Blueprint Virtual Office.
// Menu: LeadGen → Generate Office Scenes  |  CLI: -executeMethod LeadGen.Office.Editor.GenerateOfficeScenes.Generate
// Running twice must not duplicate objects: every root object is looked up by NAME and reused.
// Scenes stay lightweight — rooms/agents are built at RUNTIME from API state (RoomLayout/OfficeDirector);
// the scene only carries camera, light, bridge wiring, UI canvas + overlays + legend, event system.
#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace LeadGen.Office.Editor
{
    public static class GenerateOfficeScenes
    {
        private const string ScenesDir = "Assets/Scenes";

        [MenuItem("LeadGen/Generate Office Scenes")]
        public static void Generate()
        {
            Directory.CreateDirectory(ScenesDir);
            BuildBootstrap($"{ScenesDir}/Bootstrap.unity");
            BuildScene($"{ScenesDir}/AdminBlueprintOffice.unity", OfficeMode.Admin);
            BuildScene($"{ScenesDir}/CustomerBlueprintOffice.unity", OfficeMode.Customer);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log("GenerateOfficeScenes: DONE (idempotent) — Bootstrap + Admin + Customer scenes written.");
        }

        // Bootstrap: minimal router scene (index 0). SceneRouter picks Admin vs Customer
        // from the hosting page URL (/app/customer/office → customer scene).
        private static void BuildBootstrap(string path)
        {
            Scene scene = File.Exists(path)
                ? EditorSceneManager.OpenScene(path, OpenSceneMode.Single)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var camGo = FindOrCreate(scene, "Main Camera");
            var cam = GetOrAdd<Camera>(camGo);
            camGo.tag = "MainCamera";
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = StatusPalette.Bg;

            var routerGo = FindOrCreate(scene, "Router");
            GetOrAdd<SceneRouter>(routerGo);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, path);
            Debug.Log($"GenerateOfficeScenes: saved {path} (Bootstrap)");
        }

        private static void BuildScene(string path, OfficeMode mode)
        {
            Scene scene = File.Exists(path)
                ? EditorSceneManager.OpenScene(path, OpenSceneMode.Single)
                : EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // --- Camera (blueprint clear color, orthographic-ish tilt view) ---
            var camGo = FindOrCreate(scene, "Main Camera");
            var cam = GetOrAdd<Camera>(camGo);
            camGo.tag = "MainCamera";
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = StatusPalette.Bg;
            cam.fieldOfView = 50f;
            camGo.transform.position = new Vector3(15f, 22f, -6f);
            camGo.transform.rotation = Quaternion.Euler(60f, 0f, 0f);
            GetOrAdd<CameraController>(camGo);
            GetOrAdd<AudioListener>(camGo);

            // --- Light (single directional, no realtime shadows — perf budget) ---
            var lightGo = FindOrCreate(scene, "Directional Light");
            var light = GetOrAdd<Light>(lightGo);
            light.type = LightType.Directional;
            light.intensity = 1.0f;
            light.shadows = LightShadows.None;
            lightGo.transform.rotation = Quaternion.Euler(55f, -30f, 0f);

            // --- Bridge (shell entry point: SendMessage("Bridge", "OnHostEvent", json)) ---
            var bridgeGo = FindOrCreate(scene, "Bridge");
            GetOrAdd<HostBridge>(bridgeGo);
            if (mode == OfficeMode.Admin)
            {
                GetOrAdd<OfficeDirector>(bridgeGo);
                var staleCust = bridgeGo.GetComponent<CustomerDirector>();
                if (staleCust != null) Object.DestroyImmediate(staleCust); // never both directors
            }
            else
            {
                GetOrAdd<CustomerDirector>(bridgeGo);
                var staleAdmin = bridgeGo.GetComponent<OfficeDirector>();
                if (staleAdmin != null) Object.DestroyImmediate(staleAdmin);
            }
            GetOrAdd<OverlayUI>(bridgeGo);

            // --- UI canvas + overlays + status legend ---
            var canvasGo = FindOrCreate(scene, "OfficeCanvas");
            var canvas = GetOrAdd<Canvas>(canvasGo);
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = GetOrAdd<CanvasScaler>(canvasGo);
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280, 720);
            GetOrAdd<GraphicRaycaster>(canvasGo);

            BuildOverlay(canvasGo, "LoadingOverlay", "Loading office state…", true);
            BuildOverlay(canvasGo, "ErrorOverlay", "Office state unavailable — Lightweight Mode link is in the top bar.", false);
            BuildBadge(canvasGo, "StaleBadge", "STALE DATA", new Vector2(0f, 1f), new Vector2(8f, -8f));
            BuildLegend(canvasGo, mode);

            // --- Event system ---
            var esGo = FindOrCreate(scene, "EventSystem");
            GetOrAdd<EventSystem>(esGo);
            GetOrAdd<StandaloneInputModule>(esGo);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, path);
            Debug.Log($"GenerateOfficeScenes: saved {path} ({mode})");
        }

        // ---------- UI builders (idempotent via name lookup) ----------

        private static void BuildOverlay(GameObject canvas, string name, string message, bool visibleByDefault)
        {
            var go = FindOrCreateChild(canvas, name);
            var rect = GetOrAdd<RectTransform>(go);
            rect.anchorMin = Vector2.zero; rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero; rect.offsetMax = Vector2.zero;
            var img = GetOrAdd<Image>(go);
            img.color = new Color(StatusPalette.Bg.r, StatusPalette.Bg.g, StatusPalette.Bg.b, 0.85f);

            var txtGo = FindOrCreateChild(go, "Text");
            var txtRect = GetOrAdd<RectTransform>(txtGo);
            txtRect.anchorMin = new Vector2(0.1f, 0.4f); txtRect.anchorMax = new Vector2(0.9f, 0.6f);
            txtRect.offsetMin = Vector2.zero; txtRect.offsetMax = Vector2.zero;
            var txt = GetOrAdd<Text>(txtGo);
            txt.text = message;
            txt.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            txt.fontSize = 22;
            txt.alignment = TextAnchor.MiddleCenter;
            txt.color = StatusPalette.Text;
            go.SetActive(visibleByDefault);
        }

        private static void BuildBadge(GameObject canvas, string name, string label, Vector2 anchor, Vector2 offset)
        {
            var go = FindOrCreateChild(canvas, name);
            var rect = GetOrAdd<RectTransform>(go);
            rect.anchorMin = anchor; rect.anchorMax = anchor;
            rect.pivot = new Vector2(0f, 1f);
            rect.anchoredPosition = offset;
            rect.sizeDelta = new Vector2(150f, 30f);
            var img = GetOrAdd<Image>(go);
            img.color = new Color(StatusPalette.Waiting.r, StatusPalette.Waiting.g, StatusPalette.Waiting.b, 0.9f);
            var txtGo = FindOrCreateChild(go, "Text");
            var txtRect = GetOrAdd<RectTransform>(txtGo);
            txtRect.anchorMin = Vector2.zero; txtRect.anchorMax = Vector2.one;
            txtRect.offsetMin = Vector2.zero; txtRect.offsetMax = Vector2.zero;
            var txt = GetOrAdd<Text>(txtGo);
            txt.text = label;
            txt.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            txt.fontSize = 14;
            txt.alignment = TextAnchor.MiddleCenter;
            txt.color = Color.black;
            go.SetActive(false);
        }

        private static void BuildLegend(GameObject canvas, OfficeMode mode)
        {
            var go = FindOrCreateChild(canvas, "StatusLegend");
            var rect = GetOrAdd<RectTransform>(go);
            rect.anchorMin = new Vector2(1f, 0f); rect.anchorMax = new Vector2(1f, 0f);
            rect.pivot = new Vector2(1f, 0f);
            rect.anchoredPosition = new Vector2(-8f, 8f);
            rect.sizeDelta = new Vector2(190f, 132f);
            var img = GetOrAdd<Image>(go);
            img.color = new Color(StatusPalette.Panel.r, StatusPalette.Panel.g, StatusPalette.Panel.b, 0.92f);

            // legend rows: canonical status set (style guide) — status is text + color, never color-only
            (string, Color)[] rows = mode == OfficeMode.Admin
                ? new[]
                {
                    ("healthy / working", StatusPalette.Healthy),
                    ("processing", StatusPalette.Processing),
                    ("waiting / blocked", StatusPalette.Waiting),
                    ("retry", StatusPalette.Retry),
                    ("failed", StatusPalette.Failed),
                    ("offline / unknown", StatusPalette.Idle),
                }
                : new[]
                {
                    ("complete", StatusPalette.Healthy),
                    ("in progress", StatusPalette.Processing),
                    ("waiting for you", StatusPalette.Waiting),
                    ("blocked", StatusPalette.Failed),
                    ("not started", StatusPalette.Idle),
                };
            // clear + rebuild rows (bounded, deterministic — safe for idempotency)
            for (int i = go.transform.childCount - 1; i >= 0; i--)
                Object.DestroyImmediate(go.transform.GetChild(i).gameObject);
            for (int i = 0; i < rows.Length; i++)
            {
                var row = new GameObject($"Row{i}", typeof(RectTransform));
                row.transform.SetParent(go.transform, false);
                var rr = row.GetComponent<RectTransform>();
                rr.anchorMin = new Vector2(0f, 1f); rr.anchorMax = new Vector2(1f, 1f);
                rr.pivot = new Vector2(0.5f, 1f);
                rr.anchoredPosition = new Vector2(0f, -4f - i * 20f);
                rr.sizeDelta = new Vector2(-12f, 18f);

                var dot = new GameObject("Dot", typeof(RectTransform), typeof(Image));
                dot.transform.SetParent(row.transform, false);
                var dr = dot.GetComponent<RectTransform>();
                dr.anchorMin = new Vector2(0f, 0.5f); dr.anchorMax = new Vector2(0f, 0.5f);
                dr.anchoredPosition = new Vector2(10f, 0f); dr.sizeDelta = new Vector2(10f, 10f);
                dot.GetComponent<Image>().color = rows[i].Item2;

                var lbl = new GameObject("Label", typeof(RectTransform), typeof(Text));
                lbl.transform.SetParent(row.transform, false);
                var lr = lbl.GetComponent<RectTransform>();
                lr.anchorMin = new Vector2(0f, 0f); lr.anchorMax = new Vector2(1f, 1f);
                lr.offsetMin = new Vector2(24f, 0f); lr.offsetMax = new Vector2(0f, 0f);
                var t = lbl.GetComponent<Text>();
                t.text = rows[i].Item1;
                t.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
                t.fontSize = 12;
                t.alignment = TextAnchor.MiddleLeft;
                t.color = StatusPalette.Text;
            }
        }

        // ---------- idempotency helpers ----------

        private static GameObject FindOrCreate(Scene scene, string name)
        {
            foreach (var root in scene.GetRootGameObjects())
                if (root.name == name) return root;
            var go = new GameObject(name);
            SceneManager.MoveGameObjectToScene(go, scene);
            return go;
        }

        private static GameObject FindOrCreateChild(GameObject parent, string name)
        {
            var t = parent.transform.Find(name);
            if (t != null) return t.gameObject;
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent.transform, false);
            return go;
        }

        private static T GetOrAdd<T>(GameObject go) where T : Component
        {
            var c = go.GetComponent<T>();
            return c != null ? c : go.AddComponent<T>();
        }
    }

    public enum OfficeMode { Admin, Customer }
}
#endif
