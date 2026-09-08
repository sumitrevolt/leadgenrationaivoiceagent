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

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.platform import posthog_config

# 2MB se badi HTML inject karne ka risk nahi (file-serve etc.) — skip.
_MAX_INJECT_BYTES = 2 * 1024 * 1024


def _key() -> str:
    return posthog_config.get_api_key()


def _host() -> str:
    return posthog_config.get_host()


def _posthog_head() -> str:
    key = _key()
    host = _host()
    # Official PostHog array-stub loader, VERBATIM (posthog.com JS web snippet).
    # BUGFIX 2026-07-02: the previous hand-transcribed variant renamed init's
    # params to (t,e,a), shadowing the outer stub-array `e` — so
    # `u._i.push([t,e,a])` ran against the CONFIG OBJECT (which has no `_i`)
    # and threw `TypeError: Cannot read properties of undefined (reading
    # 'push') at r.init` on EVERY injected page load (seen live on /app/office
    # at minified lines 225-227). It also never created the <script> tag that
    # loads /static/array.js, so analytics silently captured nothing. The
    # official snippet below keeps init params as (i,s,a) (no shadowing),
    # pushes to the outer `e._i`, and actually loads array.js.
    return (
        "\n<script>\n"
        "!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){"
        'function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),'
        "t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}"
        '(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,'
        'p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",'
        '(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;'
        'for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],'
        'u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},'
        'u.people.toString=function(){return u.toString(1)+".people (stub)"},'
        'o="init capture register register_once register_for_session unregister unregister_for_session '
        "getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment "
        "getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys "
        "identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags "
        "setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id "
        "get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted "
        "captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing "
        'opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),'
        "n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}"
        "(document,window.posthog=window.posthog||[]);\n"
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
