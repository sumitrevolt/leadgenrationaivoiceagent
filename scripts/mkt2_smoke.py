"""Marketing v2 VPS smoke — fallbacks + scoring + poster escaping (no LLM/network)."""

from app.marketing import festivals, gbp_audit, posters


def main() -> None:
    qs = gbp_audit.AUDIT_QUESTIONS
    best = gbp_audit.score_audit({q["id"]: 0 for q in qs})
    worst = gbp_audit.score_audit({q["id"]: len(q["options"]) - 1 for q in qs})
    print(
        "AUDIT:",
        len(qs),
        "Qs | best:",
        best.get("score"),
        best.get("grade"),
        "| worst:",
        worst.get("score"),
        worst.get("grade"),
        "| fixes:",
        len(worst.get("top_fixes") or worst.get("fixes") or []),
    )

    p = posters.generate_poster("offer-burst", "R&D <Solar>", offer="20% OFF", phone="98xxx")
    svg = p.get("svg") or ""
    print("POSTER ok:", ("R&amp;D" in svg) and ("<Solar>" not in svg) and len(svg) > 500)

    up = festivals.upcoming(60)
    print("FESTIVALS next-60d:", len(up), "| first:", (up[0]["name"] if up else "none"))


if __name__ == "__main__":
    main()
