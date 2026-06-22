"""analytics_inject.py — PostHog snippet auto-inject into HTML (G3). GATED.

KYU: frontend/ me 30+ standalone .html (StaticFiles + HTMLResponse) serve hote.
Har file edit karne ki jagah ye middleware `</head>` se pehle PostHog snippet
inject karta — session-replay + autocapture + web-funnels for /audit /demo /pricing
/start. **OFF by default**: `POSTHOG_API_KEY` set nahi -> har response untouched
(turant passthrough, zero overhead). Never-raise: koi bhi issue -> original response.

Register (main.py app-factory me, middleware stack ke END me — sabse bahar):
    from app.middleware.analytics_inject import PostHogInjectMiddleware
    app.add_middleware(PostHogInjectMiddleware)
"""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# 2MB se badi HTML inject karne ka risk nahi (file-serve etc.) — skip.
_MAX_INJECT_BYTES = 2 * 1024 * 1024


def _key() -> str:
    return os.environ.get("POSTHOG_API_KEY", "").strip()


def _host() -> str:
    return os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com").strip()


def _posthog_head() -> str:
    key = _key()
    host = _host()
    # Full official loader (array-stub) — autocapture + session replay ON by default.
    return (
        "\n<script>\n"
        "!function(t,e){var o,n,p,r=e.__SV;if(window.posthog||(window.posthog=[]),!r){"
        'r=window.posthog,r.toString=function(t){var e="posthog";return"posthog"!==t&&(e+="."+t),e},'
        'r.people=r.people||[],r.people.toString=function(){return r.toString(1)+".people (stub)"},'
        'o="capture identify alias people.set people.set_once set_config register register_once '
        "unregister opt_out_capturing has_opted_out_capturing opt_in_capturing reset isFeatureEnabled "
        "onFeatureFlags getFeatureFlag getFeatureFlagPayload reloadFeatureFlags group updateEarlyAccessFeatureEnrollment "
        "getEarlyAccessFeatures getActiveMatchingSurveys getSurveys captureException loadToolbar get_distinct_id "
        'getGroups get_session_id get_session_replay_url alias set_config".split(" "),'
        "n=function(t){var e=r;for(var a=0;a<o.length;a++)e[o[a]]=function(t){return function(){"
        "e.push([t].concat(Array.prototype.slice.call(arguments,0)))}}(o[a])}}(0),r._i=[],"
        'r.init=function(t,e,a){function s(t,e){var a=e.split(".");2==a.length&&(t=t[a[0]],e=a[1]),'
        't[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}var u=e;void 0!==a?u=r[a]=[]:a="posthog",'
        'u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),'
        't||(e+=" (stub)"),e},u._i.push([t,e,a]),r.__SV=1}}(document,window.posthog||[]);\n'
        f"posthog.init('{key}',{{api_host:'{host}',person_profiles:'identified_only',"
        "capture_pageview:true,session_recording:{maskAllInputs:true}});\n"
        "</script>\n"
    )


class PostHogInjectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Gate: key unset -> turant original (zero work).
        if not _key():
            return response
        try:
            ct = response.headers.get("content-type", "")
            if "text/html" not in ct.lower():
                return response

            body = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                body += chunk
                if len(body) > _MAX_INJECT_BYTES:
                    # Too big -> return as-is (iterator already consumed).
                    return Response(
                        content=body,
                        status_code=response.status_code,
                        headers=_passthru_headers(response),
                        media_type=response.media_type,
                    )

            text = body.decode("utf-8", "ignore")
            if "posthog" not in text.lower() and "</head>" in text:
                text = text.replace("</head>", _posthog_head() + "</head>", 1)
            data = text.encode("utf-8")
            return Response(
                content=data,
                status_code=response.status_code,
                headers=_passthru_headers(response, new_len=len(data)),
                media_type=response.media_type,
            )
        except Exception:
            # Iterator consume ho chuka ho to bhi best-effort original bytes return.
            try:
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=_passthru_headers(response),
                    media_type=response.media_type,
                )
            except Exception:
                return response


def _passthru_headers(response, new_len: int | None = None) -> dict:
    headers = dict(response.headers)
    headers.pop("content-length", None)
    if new_len is not None:
        headers["content-length"] = str(new_len)
    return headers


__all__ = ["PostHogInjectMiddleware"]
