"""Generate social page kits (markdown) — LeadsGenAI brand + sample client.

Run (VPS): docker exec leadgen_app python scripts/gen_page_kits.py
Output: data/page_kits/<slug>.md (paste-ready, Hinglish)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.marketing.social_page_kit import build_page_kit  # noqa: E402

OUT = Path("data/page_kits")


def _md(kit: dict) -> str:
    p = kit["pages"]
    fb, ig, li, x, gbp, wa = (
        p["facebook"],
        p["instagram"],
        p["linkedin"],
        p["x_twitter"],
        p["gbp"],
        p["whatsapp_business"],
    )
    lines = [
        f"# {kit['business_name']} — Social Page Setup Kit",
        f"_Niche: {kit['niche_name']} · City: {kit.get('city') or '—'}_",
        "",
        "## 📘 Facebook Page",
        f"- **Page name:** {fb.get('page_name')}",
        f"- **Username:** @{fb.get('username')}",
        f"- **Bio:** {fb.get('bio')}",
        f"- **About:** {fb.get('about')}",
        f"- **CTA button:** {fb.get('cta_button')}",
        "",
        "## 📸 Instagram",
        f"- **Handle:** @{ig.get('handle')}",
        "- **Bio:**",
        "```",
        str(ig.get("bio") or ""),
        "```",
        f"- **Highlights:** {', '.join(ig.get('highlights') or [])}",
        "",
        "## 💼 LinkedIn Page",
        f"- **Tagline:** {li.get('tagline')}",
        f"- **About:** {li.get('about')}",
        "",
        "## 🐦 X (Twitter)",
        f"- **Handle:** @{x.get('handle')}",
        f"- **Bio:** {x.get('bio')}",
        "",
        "## 📍 Google Business Profile",
        f"- **Description:** {gbp.get('description')}",
        "",
        "## 💬 WhatsApp Business",
        f"- **About:** {wa.get('about')}",
        f"- **Greeting:** {wa.get('greeting')}",
        "",
        "## 🎨 Branding",
        f"- **Logo (AI):** {kit.get('logo_url') or '(POLLINATIONS_API_KEY set karke /app/marketing → Logo tab)'}",
        f"- **Cover image prompt:** {kit.get('cover_image_prompt')}",
        "",
        f"## 📝 Pehle {len(kit['first_posts'])} posts",
    ]
    for i, post in enumerate(kit["first_posts"], 1):
        tags = " ".join(post.get("hashtags") or [])
        lines += [
            f"### Post {i} — {post['occasion']}",
            str(post.get("caption") or ""),
            f"_{tags}_" if tags else "",
            (f"🖼️ image idea: {post.get('image_idea')}" if post.get("image_idea") else ""),
            "",
        ]
    extra = kit.get("hashtags") or []
    if extra:
        lines += ["## #️⃣ Hashtag bank", " ".join(str(t) for t in extra[:20]), ""]
    if kit.get("best_time"):
        lines += [f"**Best posting time:** {kit['best_time']}", ""]
    lines += ["---", f"_{kit.get('setup_note', '')}_"]
    return "\n".join(lines)


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [
        # APNA brand (Product 1+2 dono ka parent brand)
        {
            "business_name": "LeadsGenAI",
            "niche": "ai_marketing",
            "city": "Mumbai",
            "phone": "+91 84590 12607",
        },
        # Sample client kit (demo/deliverable example)
        {
            "business_name": "Sharma Solar",
            "niche": "solar_residential",
            "city": "Pune",
            "phone": "",
        },
    ]
    for t in targets:
        kit = await build_page_kit(**t)
        slug = t["business_name"].lower().replace(" ", "_")
        (OUT / f"{slug}.md").write_text(_md(kit), encoding="utf-8")
        print(f"WROTE data/page_kits/{slug}.md (provider posts: {len(kit['first_posts'])})")
    print("KITS_DONE")


if __name__ == "__main__":
    asyncio.run(main())
