// Bounded blueprint camera: wheel zoom + edge-safe WASD/arrow pan + smooth focus eases.
// No FPS controls, no free rotation (Phase 20: avoid complex game controls).
using UnityEngine;

namespace LeadGen.Office
{
    public class CameraController : MonoBehaviour
    {
        public Vector2 PanMin = new(-5f, -30f);
        public Vector2 PanMax = new(35f, 10f);
        public float MinHeight = 8f;
        public float MaxHeight = 34f;
        public float PanSpeed = 12f;
        public float ZoomSpeed = 8f;

        private Vector3? _focusTarget;

        public void FocusOn(Vector3 worldPos)
        {
            _focusTarget = new Vector3(worldPos.x, transform.position.y, worldPos.z - 7f);
        }

        private void Update()
        {
            var p = transform.position;

            var h = Input.GetAxisRaw("Horizontal");
            var v = Input.GetAxisRaw("Vertical");
            if (Mathf.Abs(h) > 0.01f || Mathf.Abs(v) > 0.01f)
            {
                _focusTarget = null; // manual input overrides ease
                p += new Vector3(h, 0f, v) * (PanSpeed * Time.deltaTime);
            }

            var scroll = Input.GetAxis("Mouse ScrollWheel");
            if (Mathf.Abs(scroll) > 0.001f)
                p.y = Mathf.Clamp(p.y - scroll * ZoomSpeed, MinHeight, MaxHeight);

            if (_focusTarget.HasValue)
            {
                p = Vector3.Lerp(p, _focusTarget.Value, 4f * Time.deltaTime);
                if ((p - _focusTarget.Value).sqrMagnitude < 0.01f) _focusTarget = null;
            }

            p.x = Mathf.Clamp(p.x, PanMin.x, PanMax.x);
            p.z = Mathf.Clamp(p.z, PanMin.y, PanMax.y);
            transform.position = p;
        }
    }
}
