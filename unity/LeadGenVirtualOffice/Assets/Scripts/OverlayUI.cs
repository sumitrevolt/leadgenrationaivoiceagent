// Runtime controller for the generated overlays (LoadingOverlay / ErrorOverlay / StaleBadge).
// State transitions are driven by HostBridge messages; no fake states, no spinner-forever:
// if no state arrives within TimeoutSeconds, the error overlay (with fallback wording) shows.
using UnityEngine;

namespace LeadGen.Office
{
    public class OverlayUI : MonoBehaviour
    {
        public float TimeoutSeconds = 20f;
        public float StaleSeconds = 45f;

        private GameObject _loading, _error, _stale;
        private float _lastStateAt = -1f;
        private bool _everReceived;

        private void Awake()
        {
            var canvas = GameObject.Find("OfficeCanvas");
            if (canvas == null) return;
            _loading = FindChild(canvas, "LoadingOverlay");
            _error = FindChild(canvas, "ErrorOverlay");
            _stale = FindChild(canvas, "StaleBadge");
            var bridge = GetComponent<HostBridge>();
            if (bridge != null)
            {
                bridge.OnState += _ => MarkFresh();
                bridge.OnCustomerState += _ => MarkFresh();
            }
        }

        private void MarkFresh()
        {
            _everReceived = true;
            _lastStateAt = Time.unscaledTime;
            if (_loading != null) _loading.SetActive(false);
            if (_error != null) _error.SetActive(false);
            if (_stale != null) _stale.SetActive(false);
        }

        private void Update()
        {
            if (!_everReceived)
            {
                if (Time.unscaledTime > TimeoutSeconds && _error != null && _loading != null)
                {
                    _loading.SetActive(false);
                    _error.SetActive(true);
                }
                return;
            }
            if (_stale != null && _lastStateAt > 0f)
                _stale.SetActive(Time.unscaledTime - _lastStateAt > StaleSeconds);
        }

        private static GameObject FindChild(GameObject parent, string name)
        {
            var t = parent.transform.Find(name);
            return t != null ? t.gameObject : null;
        }
    }
}
