"""End-to-end wizard flow smoke — disposable client pe apply → snapshot + knowledge.

Deploy se PEHLE prove karta hai ki full wizard chain kaam karta hai:
  add_client → apply_auto_setup (business type) → niche snapshot applied +
  knowledge seed persisted + services/offer/opening_line saved → brain opening
  override live → cleanup (client + snapshot files delete).

Disposable = unique phone (dev/test number range) + client id; har case ke baad
delete_client + snapshot files clean. Sab checks print + exit 0/1. Never touches
prod data (sirf data/ me files, jo bhi test client id se delete hote hain).

Usage:
    python scripts/e2e_wizard_smoke.py [--keep]    # --keep = client delete mat karo
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Dev/test number range — real client kabhi nahi chhuega
TEST_PHONE_PREFIX = "99900"
FAILS: list[str] = []
PASSES: list[str] = []
CREATED: list[str] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSES.append(name)
        print(f"  [ok] {name}{(' - ' + detail) if detail else ''}")
    else:
        FAILS.append(name)
        print(f"  [!!] {name}{(' - ' + detail) if detail else ''}")


def _make_client(biz: str, niche: str) -> dict:
    from app.marketing import clients_store

    phone = TEST_PHONE_PREFIX + str(uuid.uuid4().int % 1000000).zfill(6)
    rec = clients_store.add_client(business_name=biz, niche=niche, city="Pune", phone=phone)
    CREATED.append(str(rec.get("id") or ""))
    return rec


def _cleanup(keep: bool) -> None:
    """Disposable clients + unlinked snapshot files delete karo."""
    from app.marketing import clients_store

    for cid in CREATED:
        try:
            if not keep:
                clients_store.delete_client(cid)
                print(f"  [i] cleaned client {cid}")
        except Exception as e:
            print(f"  [i] cleanup client {cid} skip: {e}")
    # NOTE: niche_template snapshots deliberately NOT deleted — wo reusable
    # product assets hain (find_niche_snapshot index unhe refer karta hai);
    # file-only delete se index stale ho jaata hai -> "snapshot nahi mila".


def main() -> int:
    ap = argparse.ArgumentParser(description="Wizard E2E smoke — disposable client")
    ap.add_argument("--keep", action="store_true", help="client delete mat karo (debug)")
    args = ap.parse_args()

    os.environ["ONBOARD_WIZARD_APPLY"] = "1"
    os.environ["AUTO_QUALIFY_CALLS"] = "1"

    print("== Wizard E2E smoke (disposable client) ==")
    from app.marketing import onboard_wizard as wz

    # ---- Case 1: restaurant (NICHES-covered — full snapshot + knowledge) ----
    print("[1] restaurant_cafe — full auto-setup")
    c1 = _make_client("Wizard E2E Restaurant", "restaurant_cafe")
    r1 = wz.apply_auto_setup(
        c1["id"],
        "restaurant",
        business_name="Wizard E2E Restaurant",
        services="Dine-in, Takeaway, Home delivery",
        offer="Weekday lunch 20% off",
        opening_line="Namaste! Main Swara bol rahi hoon Wizard E2E Restaurant se — lunch menu ka naya offer hai, 2 minute?",
    )
    _check("restaurant: ok", bool(r1.get("ok")), f"applied={r1.get('applied')}")
    _check(
        "restaurant: niche_snapshot applied",
        "niche_snapshot" in (r1.get("applied") or []),
        str(r1.get("snapshot_warning") or ""),
    )
    _check(
        "restaurant: knowledge_seed applied",
        "knowledge_seed" in (r1.get("applied") or []),
    )
    _check(
        "restaurant: services_offer_opening applied",
        "services_offer_opening" in (r1.get("applied") or []),
    )

    # Client record verify — services/offer/opening_line persist hui?
    from app.marketing import clients_store

    rec1 = clients_store.get_client(c1["id"]) or {}
    _check(
        "restaurant: client services saved",
        (rec1.get("services") or "") == "Dine-in, Takeaway, Home delivery",
        str(rec1.get("services") or "")[:60],
    )
    _check(
        "restaurant: client wizard opening saved",
        (rec1.get("wizard_setup") or {}).get("opening_line", "").startswith("Namaste"),
    )
    # Brain override live?
    from app.voice_agent.telecaller_brain import TelecallerBrain

    brain1 = TelecallerBrain(
        niche="restaurant_cafe", client_name="Wizard E2E Restaurant", client_id=c1["id"]
    )
    line1 = brain1.opening_line()
    _check(
        "restaurant: brain uses wizard opening",
        "lunch menu ka naya offer hai"
        in line1,  # exact wizard opening — niche script ka [Company] nahi
        line1[:70],
    )

    # ---- Case 2: salon (NICHES-missing — knowledge seed hi main) ----
    print("[2] salon_spa — knowledge seed + graceful snapshot warning")
    c2 = _make_client("Wizard E2E Salon", "salon_spa")
    r2 = wz.apply_auto_setup(c2["id"], "salon", business_name="Wizard E2E Salon")
    _check("salon: ok", bool(r2.get("ok")), f"applied={r2.get('applied')}")
    _check("salon: knowledge_seed applied", "knowledge_seed" in (r2.get("applied") or []))
    _check(
        "salon: snapshot graceful",
        "snapshot_warning" in r2 or "niche_snapshot" in (r2.get("applied") or []),
    )

    # ---- Case 3: tiffin (own script + knowledge + services) ----
    print("[3] tiffin_service — own script + services")
    c3 = _make_client("Wizard E2E Tiffin", "tiffin_service")
    r3 = wz.apply_auto_setup(
        c3["id"],
        "tiffin",
        business_name="Wizard E2E Tiffin",
        services="Veg thali, Jain thali, Office bulk",
    )
    _check("tiffin: ok", bool(r3.get("ok")), f"applied={r3.get('applied')}")
    _check(
        "tiffin: niche_snapshot applied",
        "niche_snapshot" in (r3.get("applied") or []),
        str(r3.get("snapshot_warning") or ""),
    )
    _check("tiffin: knowledge_seed applied", "knowledge_seed" in (r3.get("applied") or []))
    rec3 = clients_store.get_client(c3["id"]) or {}
    _check(
        "tiffin: client services saved",
        (rec3.get("services") or "") == "Veg thali, Jain thali, Office bulk",
    )
    # Script preview tiffin ke liye apna script deta hai
    prev = wz.get_script_preview("tiffin", business_name="Wizard E2E Tiffin")
    _check("tiffin: script preview has_script", bool(prev.get("has_script")))
    _check(
        "tiffin: script opening mentions tiffin",
        "tiffin" in (prev.get("opening") or "").lower(),
    )

    # ---- Case 4: flag OFF → apply blocked (423-equivalent) ----
    print("[4] flag OFF gate")
    os.environ["ONBOARD_WIZARD_APPLY"] = "0"
    r4 = wz.apply_auto_setup(c1["id"], "restaurant")
    _check("flag-off: apply blocked", not r4.get("ok") and "disabled" in (r4.get("error") or ""))
    os.environ["ONBOARD_WIZARD_APPLY"] = "1"

    print("-" * 50)
    if FAILS:
        print(f"[!] E2E FAILED: {len(FAILS)} checks failed")
        for f in FAILS:
            print(f"    - {f}")
        _cleanup(args.keep)
        return 1
    print(f"[OK] E2E PASSED: {len(PASSES)} checks green")
    _cleanup(args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
