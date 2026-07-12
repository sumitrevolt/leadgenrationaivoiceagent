// Bootstrap scene router: decides Admin vs Customer scene from the HOSTING PAGE URL path.
// Deterministic + secret-free: /app/customer/office → CustomerBlueprintOffice, else Admin.
// The shell cannot be spoofed into cross-mode data exposure by this: mode only picks the
// RENDERER; all data arrives via the shell push and is already tenant/role-scoped server-side.
using UnityEngine;
using UnityEngine.SceneManagement;

namespace LeadGen.Office
{
    public class SceneRouter : MonoBehaviour
    {
        private void Start()
        {
            var url = Application.absoluteURL ?? "";
            var target = url.Contains("/app/customer/office")
                ? "CustomerBlueprintOffice"
                : "AdminBlueprintOffice";
            SceneManager.LoadScene(target, LoadSceneMode.Single);
        }
    }
}
