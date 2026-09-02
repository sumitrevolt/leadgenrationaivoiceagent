#!/usr/bin/env python3
"""VPS ops: recreate celery workers + first Kiran optimize (admin POST equivalent)."""

from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


async def _admin_token() -> str:
    from sqlalchemy import select

    from app.api.admin import create_access_token
    from app.models.base import get_async_session
    from app.models.user import User, UserRole

    async with get_async_session() as db:
        for role in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER):
            r = await db.execute(select(User).where(User.role == role).limit(1))
            user = r.scalar_one_or_none()
            if user:
                return create_access_token(str(user.id), user.email, user.role.value)
        r = await db.execute(select(User).limit(1))
        user = r.scalar_one_or_none()
        if not user:
            raise RuntimeError("no user in DB")
        return create_access_token(str(user.id), user.email, user.role.value)


async def run_optimize_direct(force: bool = True) -> dict:
    from app.agents import campaign_optimizer

    return await campaign_optimizer.optimize(force=force)


async def run_optimize_http(force: bool = True) -> dict:
    import httpx

    token = await _admin_token()
    url = "http://127.0.0.1:8080/api/growth/campaign/optimize"
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            url,
            params={"force": "true" if force else "false"},
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()


async def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "http").lower()
    force = "--no-force" not in sys.argv
    try:
        if mode == "direct":
            out = await run_optimize_direct(force=force)
        else:
            out = await run_optimize_http(force=force)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
