"""Stage 1 shadow harness proof — zero side-effect matrix.

Usage:
  .venv\\Scripts\\python.exe scripts\\video_stage1_shadow_proof.py

Never contacts WhatsApp/Postiz/Jiya. Writes under data/video_stage1_shadow/.
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    # Ensure tools registered
    import app.marketing.video_production  # noqa: F401
    from app.marketing.video_production.shadow import rollback_stage1_env, run_shadow_matrix

    report = run_shadow_matrix(write_report=True)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "correlation_id",
                    "ok",
                    "duration_s",
                    "counters",
                    "side_effect_zero",
                    "flags",
                    "report_path",
                )
                if k in report
            },
            indent=2,
            default=str,
        )
    )
    if report.get("mismatches"):
        print("MISMATCHES:", len(report["mismatches"]))
        for m in report["mismatches"][:10]:
            print(
                " -",
                m.get("kind"),
                m.get("case") or m.get("ratio") or m.get("text"),
                m.get("category"),
            )

    # Rollback drill
    rollback_stage1_env()
    from app.marketing.video_production import flags

    rolled = flags.flag_snapshot()
    rollback_ok = (
        not rolled["VIDEO_PRODUCTION_ENABLED"]
        and not rolled["VIDEO_HARNESS_SHADOW_ENABLED"]
        and not rolled["VIDEO_WHATSAPP_REVIEW_ENABLED"]
        and not rolled["VIDEO_SOCIAL_PUBLISH_ENABLED"]
    )
    print("ROLLBACK_OK=", rollback_ok)
    return 0 if report.get("ok") and rollback_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
