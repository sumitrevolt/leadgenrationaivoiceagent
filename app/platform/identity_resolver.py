"""Identity resolver — cross-store dedupe (prospect vs inquiry vs deal).

Phone10 + email + domain fuzzy match. Merge log in data/identity_merge_log.jsonl.
Never raises. DB writes best-effort (accounts/contacts).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any
from urllib.parse import urlparse

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_MERGE_LOG = os.path.join("data", "identity_merge_log.jsonl")
_PHONE_RE = re.compile(r"\d{10}")


def _phone10(raw: Any) -> str:
    digits = "".join(c for c in str(raw or "") if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def _email(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    return s if "@" in s else ""


def _domain(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    if "@" in s:
        return s.split("@", 1)[1]
    if not s.startswith("http"):
        s = "http://" + s
    try:
        host = urlparse(s).netloc or urlparse(s).path
        return host.replace("www.", "").split("/")[0]
    except Exception:
        return ""


def resolve_key(rec: dict[str, Any]) -> str:
    """Stable identity key: p:phone10 > e:email > d:domain > id:uuid."""
    ph = _phone10(rec.get("phone") or rec.get("from_number") or rec.get("contact"))
    if ph:
        return f"p:{ph}"
    em = _email(rec.get("email") or rec.get("from"))
    if em:
        return f"e:{em}"
    dom = _domain(rec.get("website") or rec.get("domain") or rec.get("company_domain"))
    if dom:
        return f"d:{dom}"
    name = str(rec.get("business_name") or rec.get("company_name") or "").strip().lower()
    if name:
        return f"n:{re.sub(r'[^a-z0-9]+', '_', name)[:40]}"
    return f"id:{uuid.uuid4().hex[:12]}"


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append_merge(rec: dict[str, Any]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_MERGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def collect_all_records() -> list[dict[str, Any]]:
    """Aggregate records from jsonl stores with source tag."""
    out: list[dict[str, Any]] = []
    sources = [
        ("prospect", os.path.join("data", "prospects.jsonl")),
        ("inquiry", os.path.join("data", "inquiries.jsonl")),
        ("deal", os.path.join("data", "deals.jsonl")),
    ]
    for src, path in sources:
        for r in _read_jsonl(path):
            out.append({**r, "_source": src, "_key": resolve_key(r)})
    return out


def find_duplicate_groups() -> list[dict[str, Any]]:
    """Groups of records sharing phone10 or email (cross-source)."""
    by_phone: dict[str, list[dict[str, Any]]] = {}
    by_email: dict[str, list[dict[str, Any]]] = {}
    for r in collect_all_records():
        ph = _phone10(r.get("phone"))
        if ph:
            by_phone.setdefault(ph, []).append(r)
        em = _email(r.get("email"))
        if em:
            by_email.setdefault(em, []).append(r)
    groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ph, rows in by_phone.items():
        if len(rows) < 2:
            continue
        sources = {r.get("_source") for r in rows}
        if len(sources) < 2:
            continue
        gid = f"phone:{ph}"
        if gid not in seen:
            seen.add(gid)
            groups.append(
                {
                    "group_id": gid,
                    "match_type": "phone",
                    "match_value": ph,
                    "count": len(rows),
                    "sources": sorted(sources),
                    "keys": [r.get("_key") for r in rows[:10]],
                }
            )
    for em, rows in by_email.items():
        if len(rows) < 2:
            continue
        sources = {r.get("_source") for r in rows}
        if len(sources) < 2:
            continue
        gid = f"email:{em}"
        if gid not in seen:
            seen.add(gid)
            groups.append(
                {
                    "group_id": gid,
                    "match_type": "email",
                    "match_value": em,
                    "count": len(rows),
                    "sources": sorted(sources),
                    "keys": [r.get("_key") for r in rows[:10]],
                }
            )
    return sorted(groups, key=lambda g: -g["count"])[:100]


async def merge_group(group_id: str, target_key: str = "") -> dict[str, Any]:
    """Log merge decision (soft-merge — jsonl stores untouched, SSOT = merge log)."""
    groups = {g["group_id"]: g for g in find_duplicate_groups()}
    g = groups.get(group_id)
    if not g:
        return {"ok": False, "error": "group not found"}
    rec = {
        "group_id": group_id,
        "target_key": target_key or g.get("match_value"),
        "merged_at": __import__("datetime").datetime.utcnow().isoformat(),
        "sources": g.get("sources"),
    }
    _append_merge(rec)
    return {"ok": True, "merge": rec}


async def backfill_accounts_contacts(limit: int = 500) -> dict[str, Any]:
    """Best-effort upsert accounts+contacts from jsonl + leads DB."""
    created_a = 0
    created_c = 0
    try:
        from sqlalchemy import select

        from app.models.account import Account
        from app.models.base import get_async_session
        from app.models.contact import Contact
        from app.models.lead import Lead

        records = collect_all_records()[:limit]
        async with get_async_session() as session:
            for r in records:
                company = str(
                    r.get("business_name") or r.get("company_name") or r.get("name") or "Unknown"
                )[:255]
                domain = _domain(r.get("website"))
                niche = str(r.get("niche") or "")[:100]
                # Account dedupe by company+domain
                q = select(Account).where(Account.company_name == company)
                if domain:
                    q = q.where(Account.domain == domain)
                existing = (await session.execute(q.limit(1))).scalar_one_or_none()
                if not existing:
                    acc = Account(
                        id=str(uuid.uuid4()),
                        company_name=company,
                        domain=domain or None,
                        niche=niche or None,
                        city=str(r.get("city") or "")[:100] or None,
                    )
                    session.add(acc)
                    # Flush so this pending Account is visible to the dedupe
                    # SELECT on the next iteration — otherwise a second record for
                    # the same company in this batch creates a duplicate Account.
                    await session.flush()
                    created_a += 1
                    account_id = acc.id
                else:
                    account_id = existing.id
                ph = _phone10(r.get("phone"))
                em = _email(r.get("email"))
                if ph or em:
                    cq = select(Contact).where(Contact.account_id == account_id)
                    if ph:
                        cq = cq.where(Contact.phone_e164.contains(ph))
                    existing_c = (await session.execute(cq.limit(1))).scalar_one_or_none()
                    if not existing_c:
                        session.add(
                            Contact(
                                id=str(uuid.uuid4()),
                                account_id=account_id,
                                name=str(r.get("contact_name") or r.get("name") or "")[:255],
                                phone_e164=f"+91{ph}" if ph else None,
                                email=em or None,
                            )
                        )
                        created_c += 1
            # Also backfill from Lead table
            leads = (await session.execute(select(Lead).limit(limit))).scalars().all()
            for ld in leads:
                company = (ld.company_name or "Unknown")[:255]
                q2 = select(Account).where(Account.company_name == company).limit(1)
                acc = (await session.execute(q2)).scalar_one_or_none()
                if not acc:
                    acc = Account(id=str(uuid.uuid4()), company_name=company, niche=ld.niche)
                    session.add(acc)
                    await session.flush()  # visible to next iteration's dedupe SELECT
                    created_a += 1
                ph = _phone10(ld.phone)
                if ph:
                    cq2 = select(Contact).where(Contact.lead_id == ld.id).limit(1)
                    if not (await session.execute(cq2)).scalar_one_or_none():
                        session.add(
                            Contact(
                                id=str(uuid.uuid4()),
                                account_id=acc.id,
                                lead_id=ld.id,
                                phone_e164=ld.phone,
                                email=ld.email,
                                name=ld.contact_name,
                            )
                        )
                        created_c += 1
            await session.commit()
    except Exception as e:
        logger.debug("[identity] backfill skip: %s", e)
        return {"ok": False, "error": str(e)[:150], "accounts": created_a, "contacts": created_c}
    return {"ok": True, "accounts_created": created_a, "contacts_created": created_c}


__all__ = [
    "resolve_key",
    "find_duplicate_groups",
    "merge_group",
    "backfill_accounts_contacts",
    "collect_all_records",
]
