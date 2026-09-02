"""Free weather-angle marketing helper (Open-Meteo — NO API key).

public-apis se: Open-Meteo (geocoding + forecast) free + no-key + India-covered
(Nager.Date ke ulat jo India support nahi karta). City → aaj ka temp + condition
→ ek Hinglish MARKETING ANGLE (garmi→AC/thanda, baarish→indoor, sardi→heater,
suhana→outdoor footfall). Content engine ise occasion ki tarah use kar sakta.

Defensive (integration-engineering pattern): 6s timeout, 1hr cache, NEVER raises,
network/parse fail → {"ok": False} (inert, koi behaviour change nahi).
"""

from __future__ import annotations

import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 3600  # 1 hr


def _condition(code: int) -> str:
    """WMO weather_code → coarse condition."""
    if code in (0, 1):
        return "clear"
    if code in (2, 3):
        return "cloudy"
    if 45 <= code <= 48:
        return "fog"
    if (51 <= code <= 67) or (80 <= code <= 82):
        return "rain"
    if 71 <= code <= 77:
        return "snow"
    if 95 <= code <= 99:
        return "storm"
    return "clear"


def _angle(temp: float, cond: str) -> dict[str, str]:
    """Temp + condition → season + Hinglish marketing angle."""
    if cond in ("rain", "storm"):
        return {
            "season": "barish",
            "angle": "Baarish ka mausam — ghar-baithe order/booking, indoor service ya monsoon-special offer push karo. ☔",
        }
    if cond == "snow" or temp <= 12:
        return {
            "season": "sardi",
            "angle": "Thand badh rahi — heater/garam-cheez/winter-care offer ya 'ghar pe service' angle chalao. 🧥",
        }
    if temp >= 34:
        return {
            "season": "garmi",
            "angle": f"Garmi tez ({int(temp)}°C) — AC/cooler/thanda/cold-drink/summer-care offer ka best time. 🌞",
        }
    return {
        "season": "suhana",
        "angle": "Mausam suhana — outdoor/visit-driven offer, footfall badhao, fresh content daalo. 🌤️",
    }


async def weather_angle(city: str = "Mumbai") -> dict[str, Any]:
    """City ka aaj ka mausam + marketing angle. Free (Open-Meteo, no key). Never raises."""
    city = (city or "Mumbai").strip() or "Mumbai"
    key = city.lower()
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < _TTL:
        return _CACHE[key][1]
    out: dict[str, Any] = {"ok": False, "city": city}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=6) as c:
            g = await c.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "country": "IN", "language": "en"},
            )
            res = (g.json().get("results") if g.status_code == 200 else None) or []
            if not res:
                _CACHE[key] = (now, out)
                return out
            lat, lon = res[0].get("latitude"), res[0].get("longitude")
            w = await c.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code",
                },
            )
            cur = (w.json().get("current") if w.status_code == 200 else None) or {}
            temp = float(cur.get("temperature_2m"))
            cond = _condition(int(cur.get("weather_code", 0)))
            out = {
                "ok": True,
                "city": city,
                "temp_c": round(temp, 1),
                "condition": cond,
                **_angle(temp, cond),
            }
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("weather_angle skip: %s", e)
        out = {"ok": False, "city": city}
    _CACHE[key] = (now, out)
    return out


__all__ = ["weather_angle"]
