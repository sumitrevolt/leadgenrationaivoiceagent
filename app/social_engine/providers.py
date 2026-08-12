"""social_engine.providers — platform adapters (SocialProvider subclasses).

LIVE now (no approval): Telegram (free), Postiz (agar configured).
Gated (creds + platform approval chahiye, tab tak INERT): Meta (FB Page + Instagram),
Google Business Profile, LinkedIn, X (Twitter), YouTube.

Token resolution: engine `account` dict deta hai = {"token","account_ref","meta"} (vault se).
Telegram bot-token env se, account_ref = chat_id. Sab publish() NEVER raises.

⚠️ Activation pe har platform ke CURRENT API version + required permission verify karo
(neeche docstrings me noted). Endpoints stable-ish hain par platforms badalte rehte.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

from .base import PublishRequest, PublishResult, SocialProvider

logger = setup_logger(__name__)

_GRAPH = "https://graph.facebook.com/v21.0"


async def _http():
    import httpx

    return httpx.AsyncClient(timeout=120)


# --------------------------------------------------------------------------- #
# Telegram — LIVE (free, BotFather token). Approval: none.
# --------------------------------------------------------------------------- #
class TelegramProvider(SocialProvider):
    name = "telegram"
    needs_public_url = False

    def _token(self) -> str:
        return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        return bool(self._token())

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        token = self._token()
        chat_id = (req.account_ref or (account or {}).get("account_ref") or "").strip()
        if not token:
            return PublishResult(ok=False, platform=self.name, error="TELEGRAM_BOT_TOKEN unset")
        if not chat_id:
            return PublishResult(ok=False, platform=self.name, error="chat_id (account_ref) unset")
        try:
            cx = await _http()
            async with cx:
                if req.media_type == "video" and req.media_path and os.path.isfile(req.media_path):
                    with open(req.media_path, "rb") as fh:
                        r = await cx.post(
                            f"https://api.telegram.org/bot{token}/sendVideo",
                            data={"chat_id": chat_id, "caption": (req.caption or "")[:1024]},
                            files={"video": (os.path.basename(req.media_path), fh, "video/mp4")},
                        )
                elif req.media_url:
                    method = "sendVideo" if req.media_type == "video" else "sendPhoto"
                    field = "video" if req.media_type == "video" else "photo"
                    r = await cx.post(
                        f"https://api.telegram.org/bot{token}/{method}",
                        json={
                            "chat_id": chat_id,
                            field: req.media_url,
                            "caption": (req.caption or "")[:1024],
                        },
                    )
                else:
                    r = await cx.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": (req.caption or "")[:4000]},
                    )
            ok = r.status_code == 200 and r.json().get("ok")
            if ok:
                mid = str(((r.json() or {}).get("result") or {}).get("message_id") or "")
                return PublishResult(ok=True, platform=self.name, post_id=mid)
            return PublishResult(ok=False, platform=self.name, error=r.text[:160])
        except Exception as e:
            return PublishResult(ok=False, platform=self.name, error=str(e)[:150])


# --------------------------------------------------------------------------- #
# Meta — Facebook Page + Instagram (one adapter, `target`). GATED.
# Approval: Meta app-review + business verification. Perms: pages_manage_posts,
# pages_read_engagement (FB); instagram_content_publish, instagram_basic (IG).
# Token: per-client Page access token (vault). IG video = PUBLIC url chahiye.
# --------------------------------------------------------------------------- #
class MetaProvider(SocialProvider):
    needs_public_url = True

    def __init__(self, target: str = "facebook"):
        self.target = target  # "facebook" | "instagram"
        self.name = target

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        return bool((account or {}).get("token"))

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        token = (account or {}).get("token") or ""
        node = (req.account_ref or (account or {}).get("account_ref") or "").strip()
        if not token or not node:
            return PublishResult(
                ok=False,
                platform=self.name,
                error="token/account_ref unset (Meta app-review pending)",
            )
        if not req.media_url:
            return PublishResult(
                ok=False, platform=self.name, error="media public URL chahiye (host first)"
            )
        try:
            cx = await _http()
            async with cx:
                if self.target == "instagram":
                    # 1) media container (REELS) 2) publish
                    c = await cx.post(
                        f"{_GRAPH}/{node}/media",
                        data={
                            "media_type": "REELS",
                            "video_url": req.media_url,
                            "caption": req.caption or "",
                            "access_token": token,
                        },
                    )
                    if c.status_code // 100 != 2:
                        return PublishResult(
                            ok=False,
                            platform=self.name,
                            error=f"container {c.status_code}: {c.text[:140]}",
                        )
                    cid = (c.json() or {}).get("id")
                    pub = await cx.post(
                        f"{_GRAPH}/{node}/media_publish",
                        data={"creation_id": cid, "access_token": token},
                    )
                    ok = pub.status_code // 100 == 2
                    pid = (pub.json() or {}).get("id", "") if ok else ""
                    return PublishResult(
                        ok=ok,
                        platform=self.name,
                        post_id=str(pid),
                        error="" if ok else pub.text[:160],
                    )
                else:  # facebook page video
                    r = await cx.post(
                        f"{_GRAPH}/{node}/videos",
                        data={
                            "file_url": req.media_url,
                            "description": req.caption or "",
                            "access_token": token,
                        },
                    )
                    ok = r.status_code // 100 == 2
                    pid = (r.json() or {}).get("id", "") if ok else ""
                    return PublishResult(
                        ok=ok,
                        platform=self.name,
                        post_id=str(pid),
                        error="" if ok else r.text[:160],
                    )
        except Exception as e:
            return PublishResult(ok=False, platform=self.name, error=str(e)[:150])


# --------------------------------------------------------------------------- #
# Google Business Profile — localPosts. GATED.
# Approval: GBP API access request + per-location OAuth. NOTE: Google ne kuch GBP
# post-features restrict kiye — activation pe current API + access status verify karo.
# --------------------------------------------------------------------------- #
class GBPProvider(SocialProvider):
    name = "gbp"
    needs_public_url = True

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        return bool((account or {}).get("token"))

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        token = (account or {}).get("token") or ""
        parent = (
            req.account_ref or (account or {}).get("account_ref") or ""
        ).strip()  # accounts/{a}/locations/{l}
        if not token or not parent:
            return PublishResult(
                ok=False, platform=self.name, error="token/location unset (GBP API access pending)"
            )
        try:
            body: dict[str, Any] = {
                "languageCode": "en-IN",
                "summary": req.caption or "",
                "topicType": "STANDARD",
            }
            if req.media_url:
                body["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": req.media_url}]
            cx = await _http()
            async with cx:
                r = await cx.post(
                    f"https://mybusiness.googleapis.com/v4/{parent}/localPosts",
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
            ok = r.status_code // 100 == 2
            pid = (r.json() or {}).get("name", "") if ok else ""
            return PublishResult(
                ok=ok, platform=self.name, post_id=str(pid), error="" if ok else r.text[:160]
            )
        except Exception as e:
            return PublishResult(ok=False, platform=self.name, error=str(e)[:150])


# --------------------------------------------------------------------------- #
# LinkedIn — Posts API. GATED (partner approval sabse mushkil).
# Approval: LinkedIn Marketing/Community Mgmt API partner access. Scope: w_organization_social
# / w_member_social. Author urn = person/organization. Video = registerUpload pehle.
# --------------------------------------------------------------------------- #
class LinkedInProvider(SocialProvider):
    name = "linkedin"
    needs_public_url = True

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        return bool((account or {}).get("token"))

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        token = (account or {}).get("token") or ""
        author = (
            req.account_ref or (account or {}).get("account_ref") or ""
        ).strip()  # urn:li:organization:123
        if not token or not author:
            return PublishResult(
                ok=False,
                platform=self.name,
                error="token/author-urn unset (LinkedIn partner access pending)",
            )
        try:
            # Text/article post (image/video = registerUpload flow, separate — activation pe wire).
            body = {
                "author": author,
                "commentary": req.caption or "",
                "visibility": "PUBLIC",
                "distribution": {"feedDistribution": "MAIN_FEED"},
                "lifecycleState": "PUBLISHED",
            }
            cx = await _http()
            async with cx:
                r = await cx.post(
                    "https://api.linkedin.com/rest/posts",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "LinkedIn-Version": "202405",
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                    json=body,
                )
            ok = r.status_code // 100 == 2
            pid = r.headers.get("x-restli-id", "") if ok else ""
            return PublishResult(
                ok=ok, platform=self.name, post_id=str(pid), error="" if ok else r.text[:160]
            )
        except Exception as e:
            return PublishResult(ok=False, platform=self.name, error=str(e)[:150])


# --------------------------------------------------------------------------- #
# X (Twitter) — v2 tweets. GATED (OAuth + paid API tier for media).
# --------------------------------------------------------------------------- #
class XProvider(SocialProvider):
    name = "x"
    needs_public_url = False

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        return bool((account or {}).get("token"))

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        token = (account or {}).get("token") or ""
        if not token:
            return PublishResult(
                ok=False, platform=self.name, error="token unset (X API access pending)"
            )
        try:
            # Text tweet. Media upload (v1.1/v2 chunked) = activation pe wire.
            cx = await _http()
            async with cx:
                r = await cx.post(
                    "https://api.twitter.com/2/tweets",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"text": (req.caption or "")[:280]},
                )
            ok = r.status_code // 100 == 2
            pid = ((r.json() or {}).get("data") or {}).get("id", "") if ok else ""
            return PublishResult(
                ok=ok, platform=self.name, post_id=str(pid), error="" if ok else r.text[:160]
            )
        except Exception as e:
            return PublishResult(ok=False, platform=self.name, error=str(e)[:150])


# --------------------------------------------------------------------------- #
# YouTube — Shorts upload. GATED (OAuth + resumable upload, heavy).
# --------------------------------------------------------------------------- #
class YouTubeProvider(SocialProvider):
    name = "youtube"
    needs_public_url = False

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        return bool((account or {}).get("token"))

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        if not (account or {}).get("token"):
            return PublishResult(
                ok=False, platform=self.name, error="token unset (YouTube OAuth pending)"
            )
        # Resumable upload (videos.insert) heavy — activation pe wire (worker me, public_url ya file).
        return PublishResult(
            ok=False, platform=self.name, error="youtube upload activation pe wire hoga"
        )


# --------------------------------------------------------------------------- #
# WhatsApp — 1-to-1 delivery of approved posts to the CLIENT's OWN number. LIVE
# (self-host WAHA ya Meta Cloud, jo bhi active). Approval: none (self-host stack).
#
# ⚠️ BAN-SAFE INVARIANT: yeh provider SIRF business-owner ke ek number pe warm 1-to-1
# message bhejta (approved content ready-to-forward). Kabhi bulk/broadcast NAHI — ek
# recipient (client ka apna phone). account_ref = recipient phone (engine client-record
# se resolve karta). Sender = get_whatsapp_sender() (self-host active to WAHA, warna Cloud).
# Image/video ka public URL caption me append hota (self-host me native media-send method
# nahi) — client apne WhatsApp pe post dekh ke aage forward kar sakti.
# --------------------------------------------------------------------------- #
class WhatsAppProvider(SocialProvider):
    name = "whatsapp"
    needs_public_url = False

    @staticmethod
    def _sender_configured() -> bool:
        """True agar koi WA backend bhej sakta (self-host WAHA base-url YA Cloud token)."""
        try:
            from app.integrations import whatsapp_selfhost

            if whatsapp_selfhost.is_active_provider():
                return True
        except Exception:
            pass
        try:
            from app.config import settings

            return bool(getattr(settings, "whatsapp_business_token", "") or "")
        except Exception:
            return False

    @staticmethod
    def _recipient(req_ref: str, account: dict[str, Any] | None) -> str:
        """Single recipient phone. account_ref (engine ne client-phone se bhara) priority,
        warna account meta. Digits-only, ek hi number — kabhi list nahi (bulk impossible)."""
        cand = (req_ref or (account or {}).get("account_ref") or "").strip()
        if not cand:
            return ""
        # Ek hi recipient enforce: agar galti se comma/space-separated aa gaya to PEHLA hi lo.
        cand = cand.replace(";", ",").split(",")[0].strip()
        return cand

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        # Inert jab tak koi WA backend na ho AUR ek recipient phone na ho.
        return bool(self._sender_configured() and self._recipient("", account))

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        to = self._recipient(req.account_ref, account)
        if not to:
            return PublishResult(ok=False, platform=self.name, error="recipient phone unset")
        if not self._sender_configured():
            return PublishResult(ok=False, platform=self.name, error="WhatsApp sender unconfigured")
        # Text body = caption (+ media public URL append; self-host me native image-send nahi).
        body = (req.caption or "").strip()
        if req.media_url:
            body = (body + ("\n\n" if body else "") + str(req.media_url)).strip()
        if not body:
            return PublishResult(
                ok=False, platform=self.name, error="empty caption (nothing to send)"
            )
        try:
            from app.integrations.whatsapp import get_whatsapp_sender

            sender = get_whatsapp_sender()
            res = await sender.send_text_message(to, body)  # NEVER raises (dict on error)
            res = res if isinstance(res, dict) else {}
            err = str(res.get("error") or "")
            if err:
                return PublishResult(ok=False, platform=self.name, error=err[:160], raw=res)
            mid = ""
            try:
                msgs = res.get("messages") or []
                if msgs:
                    mid = str((msgs[0] or {}).get("id") or "")
            except Exception:
                mid = ""
            return PublishResult(ok=True, platform=self.name, post_id=mid, raw=res)
        except Exception as e:
            return PublishResult(ok=False, platform=self.name, error=str(e)[:150])


# --------------------------------------------------------------------------- #
# Postiz — existing integration wrap (agar POSTIZ_API_KEY set). Multi-channel fallback.
# --------------------------------------------------------------------------- #
class PostizProvider(SocialProvider):
    name = "postiz"
    needs_public_url = False

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        try:
            from app.marketing import postiz_publish

            return bool(postiz_publish.enabled())
        except Exception:
            return False

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        try:
            from app.marketing import clients_store, postiz_publish

            client = dict(clients_store.get_client(req.client_id) or {})
            if not client.get("id"):
                client["id"] = str(req.client_id or "")
            # Wizard stores postiz_integrations in social_config — merge so publish
            # does not silently fall through to (now blocked) global env IDs.
            if not client.get("postiz_integrations"):
                try:
                    from app.social_engine import client_config

                    cfg = client_config.get(str(req.client_id or "")) or {}
                    if cfg.get("postiz_integrations"):
                        client["postiz_integrations"] = cfg.get("postiz_integrations")
                except Exception:
                    pass
            res = await postiz_publish.publish_video(
                client, req.caption, req.media_path or req.media_url
            )
            ok = bool(res.get("sent"))
            return PublishResult(
                ok=ok,
                platform=self.name,
                post_id=str(res.get("post_id") or ""),
                url=str(res.get("post_url") or ""),
                raw=res,
                error="" if ok else str(res.get("reason") or "")[:160],
            )
        except Exception as e:
            return PublishResult(ok=False, platform=self.name, error=str(e)[:150])


def default_providers() -> dict[str, SocialProvider]:
    """Registry: platform-key -> provider instance."""
    return {
        # telegram REMOVED 2026-06-28 (ban-risk; TelegramProvider class kept dead/unreferenced)
        "whatsapp": WhatsAppProvider(),  # 1-to-1 owner delivery of approved posts (ban-safe)
        "facebook": MetaProvider("facebook"),
        "instagram": MetaProvider("instagram"),
        "gbp": GBPProvider(),
        "linkedin": LinkedInProvider(),
        "x": XProvider(),
        "youtube": YouTubeProvider(),
        "postiz": PostizProvider(),
    }
