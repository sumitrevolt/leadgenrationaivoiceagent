"""Marketing SEO/SEM helpers via **advertools** — optional, defensive.

advertools is the standard open-source online-marketing toolkit. We use it to
programmatically build SEM keyword lists and split copy into ad-sized slots — handy
for the ads_copy / seo_blog / gbp_text modules. Free, CPU, pandas-based (already a dep).

No env flag: if advertools isn't installed, each function returns a safe fallback
(empty list or a naive split). Never raises.

Use:
  from app.marketing import seo_tools
  kws = seo_tools.generate_keywords(["solar panels","solar installation"], ["price","subsidy","near me"])
  slots = seo_tools.split_ad("Best solar panels in Pune with 25-year warranty and free site visit", (30,30,30,90,90))
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def available() -> bool:
    try:
        import advertools  # noqa: F401

        return True
    except Exception:
        return False


def generate_keywords(
    products: list[str], modifiers: list[str], match_types: tuple = ("exact", "phrase")
) -> list[dict[str, Any]]:
    """SEM keyword combinations (advertools.kw_generate) as list[dict]. [] if unavailable."""
    if not products or not modifiers:
        return []
    try:
        import advertools as adv

        df = adv.kw_generate(products, modifiers, match_types=list(match_types))
        return df.to_dict("records")
    except Exception as exc:
        logger.info("generate_keywords unavailable (%s)", exc)
        return []


def split_ad(text: str, slots: tuple = (30, 30, 30, 90, 90)) -> list[str]:
    """Split copy into RSA-sized slots (advertools.ad_from_string). Naive fallback if missing."""
    if not (text or "").strip():
        return []
    try:
        import advertools as adv

        parts = adv.ad_from_string(text, slots=list(slots))
        return [p for p in parts if p]
    except Exception:
        out, i = [], 0
        for n in slots:
            seg = text[i : i + n].strip()
            if seg:
                out.append(seg)
            i += n
        return out


__all__ = ["available", "generate_keywords", "split_ad"]
