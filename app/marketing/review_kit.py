"""
review_kit.py — Review COLLECTION kit (Birdeye-lite, 100% free stack).
=======================================================================

Chhote business ke liye Google-review maangne ka poora kit:
  - review_link(place_query): universal Google Maps search link + direct
    writereview-URL guidance (Place ID owner ke GBP dashboard se milta hai).
  - qr_svg(url): PURE-PYTHON QR encoder (byte mode, version auto 1-5,
    EC level L, single RS block — koi external lib nahi) → SVG string.
  - review_ask_pack(business_name): WhatsApp message + 800x1000 counter-card
    SVG ({qr} slot ke saath) + SMS line — sab template, instant.
  - full_kit(business_name, place_query): sab assemble (QR card me embedded),
    wa_message LLM-polish optional (free_ai), template fallback NEVER-empty.

Pure stdlib; generator functions kabhi raise nahi karte.
"""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

_FONT = "Segoe UI, Arial, sans-serif"


# ============================================================================ #
# Minimal QR encoder — byte mode, versions 1-5, EC level L (sab single-block).
# Reference algorithm: ISO/IEC 18004 (Nayuki-style construction). Deterministic.
# ============================================================================ #

# version -> (data codewords, EC codewords) for EC level L (1 RS block each).
_QR_L: dict[int, tuple] = {1: (19, 7), 2: (34, 10), 3: (55, 15), 4: (80, 20), 5: (108, 26)}
# version -> alignment-pattern center coordinates.
_QR_ALIGN: dict[int, list[int]] = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30]}

# GF(256) log/antilog tables (primitive poly 0x11D).
_EXP = [0] * 512
_LOG = [0] * 256
_v = 1
for _i in range(255):
    _EXP[_i] = _v
    _LOG[_v] = _i
    _v <<= 1
    if _v & 0x100:
        _v ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gmul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_ec(data: list[int], n_ec: int) -> list[int]:
    """Reed-Solomon EC codewords (single block, generator poly degree n_ec)."""
    gen = [1]
    for i in range(n_ec):
        nxt = [0] * (len(gen) + 1)
        for j, g in enumerate(gen):
            nxt[j] ^= g  # × x
            nxt[j + 1] ^= _gmul(g, _EXP[i])  # × α^i
        gen = nxt
    rem = list(data) + [0] * n_ec
    for i in range(len(data)):
        f = rem[i]
        if f:
            for j in range(1, len(gen)):
                rem[i + j] ^= _gmul(gen[j], f)
    return rem[len(data) :]


# Mask conditions (r=row, c=col) — module invert hota hai jab condition True.
_MASKS = (
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
)


def _penalty(M: list[list[bool]]) -> int:
    """Standard mask-penalty (N1/N2/N4 exact, N3 simplified string-scan)."""
    size = len(M)
    pen = 0
    for grid in (M, list(zip(*M, strict=False))):
        for line in grid:
            run, prev = 0, None
            for cell in line:
                if cell == prev:
                    run += 1
                else:
                    if run >= 5:
                        pen += 3 + run - 5
                    run, prev = 1, cell
            if run >= 5:
                pen += 3 + run - 5
            s = "".join("1" if x else "0" for x in line)
            pen += 40 * (s.count("00001011101") + s.count("10111010000"))
    for r in range(size - 1):
        for c in range(size - 1):
            if M[r][c] == M[r][c + 1] == M[r + 1][c] == M[r + 1][c + 1]:
                pen += 3
    dark = sum(row.count(True) for row in M)
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    return pen + 10 * max(0, k)


def _qr_matrix(payload: bytes) -> list[list[bool]]:
    """bytes → QR module-matrix (True = dark). Version auto 1-5, EC L."""
    version = 5
    for v in range(1, 6):
        if 8 * _QR_L[v][0] >= 12 + 8 * len(payload):
            version = v
            break
    cap = (8 * _QR_L[version][0] - 12) // 8
    payload = payload[:cap]  # defensive truncate (maps-search URL kata bhi chale)
    n_data, n_ec = _QR_L[version]
    size = 17 + 4 * version

    # --- bitstream: mode(0100) + count(8) + data + terminator + pad bytes --- #
    bits: list[int] = []

    def _put(val: int, n: int) -> None:
        for k in range(n - 1, -1, -1):
            bits.append((val >> k) & 1)

    _put(4, 4)
    _put(len(payload), 8)
    for b in payload:
        _put(b, 8)
    _put(0, min(4, n_data * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    pad_i = 0
    while len(bits) < n_data * 8:
        _put((0xEC, 0x11)[pad_i % 2], 8)
        pad_i += 1
    cw: list[int] = []
    for k in range(0, len(bits), 8):
        byte = 0
        for bit in bits[k : k + 8]:
            byte = (byte << 1) | bit
        cw.append(byte)
    cw += _rs_ec(cw, n_ec)

    # --- module grid + function-area flags --- #
    M = [[False] * size for _ in range(size)]
    F = [[False] * size for _ in range(size)]

    def _set(r: int, c: int, dark: bool) -> None:
        M[r][c] = dark
        F[r][c] = True

    # finder patterns + separators (centers: TL, TR, BL)
    for cr, cc in ((3, 3), (3, size - 4), (size - 4, 3)):
        for dr in range(-4, 5):
            for dc in range(-4, 5):
                r, c = cr + dr, cc + dc
                if 0 <= r < size and 0 <= c < size:
                    d = max(abs(dr), abs(dc))
                    _set(r, c, d != 2 and d != 4)
    # timing patterns
    for k in range(size):
        if not F[6][k]:
            _set(6, k, k % 2 == 0)
        if not F[k][6]:
            _set(k, 6, k % 2 == 0)
    # alignment patterns (finder-overlap centers skip)
    pos = _QR_ALIGN[version]
    for ar in pos:
        for ac in pos:
            if F[ar][ac]:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    _set(ar + dr, ac + dc, max(abs(dr), abs(dc)) != 1)
    # format-info areas reserve + dark module
    for k in range(9):
        if not F[8][k]:
            _set(8, k, False)
        if not F[k][8]:
            _set(k, 8, False)
    for k in range(8):
        if not F[8][size - 1 - k]:
            _set(8, size - 1 - k, False)
        if not F[size - 1 - k][8]:
            _set(size - 1 - k, 8, False)
    _set(size - 8, 8, True)

    # --- data placement (zigzag, col 6 skip) --- #
    total_bits = len(cw) * 8
    bi = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right -= 1
        upward = ((right + 1) & 2) == 0
        for vert in range(size):
            r = (size - 1 - vert) if upward else vert
            for c in (right, right - 1):
                if not F[r][c] and bi < total_bits:
                    M[r][c] = ((cw[bi >> 3] >> (7 - (bi & 7))) & 1) == 1
                    bi += 1
        right -= 2

    # --- mask trial (penalty-best) + format info --- #
    def _apply_mask(m: int) -> None:
        fn = _MASKS[m]
        for r in range(size):
            row_f, row_m = F[r], M[r]
            for c in range(size):
                if not row_f[c] and fn(r, c):
                    row_m[c] = not row_m[c]

    def _draw_format(mask: int) -> None:
        data = (1 << 3) | mask  # EC level L = 0b01
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ (((rem >> 9) & 1) * 0x537)
        fb = ((data << 10) | rem) ^ 0x5412

        def _bit(i: int) -> bool:
            return ((fb >> i) & 1) == 1

        for i in range(6):
            M[i][8] = _bit(i)
        M[7][8] = _bit(6)
        M[8][8] = _bit(7)
        M[8][7] = _bit(8)
        for i in range(9, 15):
            M[8][14 - i] = _bit(i)
        for i in range(8):
            M[8][size - 1 - i] = _bit(i)
        for i in range(8, 15):
            M[size - 15 + i][8] = _bit(i)
        M[size - 8][8] = True

    best_mask, best_pen = 0, None
    for m in range(8):
        _apply_mask(m)
        _draw_format(m)
        p = _penalty(M)
        if best_pen is None or p < best_pen:
            best_mask, best_pen = m, p
        _apply_mask(m)  # XOR dobara = wapas original
    _apply_mask(best_mask)
    _draw_format(best_mask)
    return M


def qr_svg(url: str, size: int = 320) -> str:
    """URL → scannable QR code SVG (4-module quiet zone). Deterministic, kabhi raise nahi."""
    url = (url or "").strip() or "https://www.google.com/maps"
    try:
        matrix = _qr_matrix(url.encode("utf-8"))
    except Exception as e:  # pragma: no cover - encoder deterministic hai
        logger.error(f"qr_svg encode failed: {e}")
        matrix = [[(r + c) % 2 == 0 for c in range(21)] for r in range(21)]
    try:
        size = max(64, min(int(size), 2000))
    except Exception:
        size = 320
    n = len(matrix)
    dim = n + 8
    rects = []
    for r in range(n):
        for c in range(n):
            if matrix[r][c]:
                rects.append(f'<rect x="{c + 4}" y="{r + 4}" width="1" height="1"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {dim} {dim}" shape-rendering="crispEdges">'
        f'<rect width="{dim}" height="{dim}" fill="#ffffff"/>'
        f'<g fill="#000000">{"".join(rects)}</g></svg>'
    )


# ============================================================================ #
# Review links + ask pack (templates — instant, no LLM)
# ============================================================================ #


def review_link(place_query: str) -> dict[str, Any]:
    """Google review links + guidance. Universal maps-search link hamesha milta hai."""
    q = (place_query or "").strip() or "mera business"
    return {
        "maps_search_url": f"https://www.google.com/maps/search/{quote(q)}",
        "direct_review_url_prefix": "https://search.google.com/local/writereview?placeid=",
        "direct_review_note": (
            "Sabse seedha link: https://search.google.com/local/writereview?placeid=<PLACE_ID> "
            "— isme apna Google Place ID lagana hota hai. Ye link kholte hi review box "
            "khul jaata hai (best conversion)."
        ),
        "how_to_get_place_id": [
            "business.google.com par login karein (apna GBP)",
            "'Ask for reviews' / 'Share review form' button se direct link copy karein",
            "Ya developers.google.com/maps ke 'Place ID Finder' me business naam search karein",
        ],
        "tip": (
            "Place ID na ho to maps_search_url use karein — customer business khol kar "
            "'Reviews' tab se review de sakta hai. QR isi link ka banta hai."
        ),
    }


_CARD_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000" viewBox="0 0 800 1000">'
    '<defs><linearGradient id="rkbg" x1="0%" y1="0%" x2="0%" y2="100%">'
    '<stop offset="0%" stop-color="#7c3aed"/><stop offset="100%" stop-color="#5b21b6"/>'
    "</linearGradient></defs>"
    '<rect width="800" height="1000" fill="#ffffff"/>'
    '<rect width="800" height="240" fill="url(#rkbg)"/>'
    f'<text x="400" y="105" font-family="{_FONT}" font-size="44" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">{business_name}</text>'
    f'<text x="400" y="172" font-family="{_FONT}" font-size="34" fill="#fde68a" '
    'text-anchor="middle">⭐⭐⭐⭐⭐</text>'
    f'<text x="400" y="330" font-family="{_FONT}" font-size="40" font-weight="bold" '
    'fill="#1f2937" text-anchor="middle">Hamari service achhi lagi?</text>'
    f'<text x="400" y="392" font-family="{_FONT}" font-size="34" font-weight="bold" '
    'fill="#7c3aed" text-anchor="middle">Google pe review karein 🙏</text>'
    '<rect x="220" y="460" width="360" height="360" rx="18" fill="#f5f3ff" '
    'stroke="#7c3aed" stroke-width="3"/>'
    "{qr}"
    f'<text x="400" y="880" font-family="{_FONT}" font-size="28" fill="#374151" '
    'text-anchor="middle">📱 Phone se scan karein — sirf 30 second</text>'
    f'<text x="400" y="945" font-family="{_FONT}" font-size="24" fill="#6b7280" '
    'text-anchor="middle">Aapka review hamare liye sabse bada gift hai ❤️</text>'
    "</svg>"
)


def review_ask_pack(business_name: str) -> dict[str, str]:
    """Review-request pack: wa_message + counter_card_svg ({qr} slot) + sms_line.

    Pure template — instant, kabhi empty nahi. {qr} slot full_kit() fill karta hai
    (ya khud qr_svg() ka output replace kar lo).
    """
    name = (business_name or "").strip() or "Hamari team"
    wa_message = (
        f"Namaste! 🙏 {name} ko apni seva ka mauka dene ke liye dhanyawad. "
        "Aapko hamari service kaisi lagi? Agar achhi lagi ho to bas 30 second "
        "nikaal kar Google par ek chhota review de dijiye — aapke 2 shabd "
        "hamare liye bahut keemti hain aur dusre logon ki madad bhi karte hain ⭐"
    )
    sms_line = f"{name}: Service achhi lagi? Google par 1-min me review dein — bahut madad hogi 🙏"
    card = _CARD_SVG.replace("{business_name}", escape(name, quote=True))
    return {
        "wa_message": wa_message,
        "counter_card_svg": card,
        "sms_line": sms_line,
    }


async def full_kit(business_name: str, place_query: str) -> dict[str, Any]:
    """Poora review kit assemble: links + QR + counter card (QR embedded) + messages.

    wa_message LLM-polish hota hai (free_ai), fail par template — KABHI empty nahi.
    """
    name = (business_name or "").strip() or "Hamari team"
    links = review_link((place_query or "").strip() or name)
    url = links["maps_search_url"]
    pack = review_ask_pack(name)

    qr = qr_svg(url, 320)
    embedded = qr.replace("<svg ", '<svg x="240" y="480" ', 1)
    card = pack["counter_card_svg"].replace("{qr}", embedded)

    wa_message = pack["wa_message"]
    provider = "template"
    if free_ai is not None:
        try:
            system = (
                "Tu ek Indian local business ka friendly assistant hai. Customer ko "
                "WhatsApp par Google review maangne ka 2-3 line ka warm Hinglish "
                "(Roman script) message likh. Pushy mat ban, thank you se shuru kar, "
                "30-second wala point rakh. Sirf message de, koi link/commentary nahi."
            )
            text, p = await free_ai.chat(
                system,
                [{"role": "user", "content": f"Business: {name}. Review-request message likho."}],
                max_tokens=140,
                temperature=0.7,
            )
            if text and text.strip():
                wa_message = text.strip()[:500]
                provider = p or "llm"
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"full_kit LLM polish failed, using template: {e}")

    return {
        "business_name": name,
        "links": links,
        "wa_message": wa_message + "\n\n⭐ Review yahan dein: " + url,
        "sms_line": pack["sms_line"] + " " + url,
        "qr_svg": qr,
        "counter_card_svg": card,
        "provider": provider,
    }
