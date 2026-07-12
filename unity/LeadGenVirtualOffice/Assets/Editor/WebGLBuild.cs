// CLI build entry (deterministic, fail-non-zero):
//   Unity.exe -batchmode -quit -projectPath unity\LeadGenVirtualOffice ^
//     -executeMethod LeadGen.Office.Editor.WebGLBuild.Build -logFile build.log
// Steps: (1) regenerate scenes (idempotent) (2) build WebGL Brotli → Build/
// Tests run separately via -runTests (see README) because -runTests and -executeMethod
// cannot share one invocation.
#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace LeadGen.Office.Editor
{
    public static class WebGLBuild
    {
        [MenuItem("LeadGen/Build WebGL (Brotli)")]
        public static void Build()
        {
            GenerateOfficeScenes.Generate();

            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Brotli;
            PlayerSettings.WebGL.decompressionFallback = false;
            PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.None;
            PlayerSettings.WebGL.memorySize = 256; // MB heap (bounded; tune with real measurements)
            PlayerSettings.stripEngineCode = true;
            PlayerSettings.SetManagedStrippingLevel(BuildTargetGroup.WebGL, ManagedStrippingLevel.High);
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.companyName = "LeadGen AI";
            PlayerSettings.productName = "LeadGenVirtualOffice";

            var scenes = new[]
            {
                "Assets/Scenes/Bootstrap.unity",
                "Assets/Scenes/AdminBlueprintOffice.unity",
                "Assets/Scenes/CustomerBlueprintOffice.unity",
            };
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = "Build",
                target = BuildTarget.WebGL,
                options = BuildOptions.None,
            });

            Debug.Log($"WebGL build: {report.summary.result}, total {report.summary.totalSize} bytes, " +
                      $"{report.summary.totalTime.TotalSeconds:F0}s, warnings={report.summary.totalWarnings}, errors={report.summary.totalErrors}");
            if (report.summary.result != BuildResult.Succeeded)
                EditorApplication.Exit(1);

            // size manifest for deployment evidence
            var sb = new System.Text.StringBuilder("WebGL build sizes:\n");
            foreach (var f in Directory.GetFiles("Build", "*", SearchOption.AllDirectories))
                sb.AppendLine($"{new FileInfo(f).Length,12} bytes  {f}");
            File.WriteAllText("Build/build_sizes.txt", sb.ToString());
        }
    }
}
#endif
