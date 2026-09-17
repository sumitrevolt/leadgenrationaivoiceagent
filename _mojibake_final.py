import re, subprocess

FILES = [
    'docs/SAAS_INFRA_TRUTH_AND_GAPS_2026_06_15.md',
    'app/api/growth.py',
    'docs/skills/CANONICAL_SKILL_INDEX.md',
]

# char->byte: ASCII + cp1252 with latin1-fallback for the 5 holes.
# This is the exact inverse of "UTF-8 bytes misread as cp1252".
table = {}
for b in range(256):
    if b < 0x80:
        table[chr(b)] = b
    else:
        try:
            table[bytes([b]).decode('cp1252')] = b
        except Exception:
            table[chr(b)] = b  # U+00XX hole fallback

def reverse_runs(raw: bytes) -> bytes:
    t = raw.decode('utf-8')
    n = len(t)
    mb = [table.get(c) for c in t]  # None for unmappable (>0xFF / emoji)
    out = bytearray()
    i = 0
    while i < n:
        if mb[i] is None:
            out += t[i].encode('utf-8'); i += 1; continue
        j = i
        while j < n and mb[j] is not None:
            j += 1
        run = t[i:j]
        if len(run) >= 2 and any(ord(x) > 0x7f for x in run):
            cand = bytes(mb[i:j])
            try:
                cand.decode('utf-8')
                out += cand; i = j; continue
            except Exception:
                pass
        out += run.encode('utf-8'); i = j
    return bytes(out)

def fam(d):
    c3a2 = sum(1 for m in re.finditer(b'\xc3\xa2', d)
               if d[m.start()+2:m.start()+3][:1] in (b'\xc3', b'\xe2', b'\xcb'))
    c382 = sum(1 for m in re.finditer(b'\xc3\x82', d)
               if d[m.start()+2:m.start()+3][:1] in (b'\xc2', b'\xc3', b'\xe2'))
    return c3a2 + c382

total = 0
for f in FILES:
    # start from the CURRENT worktree file (already == origin/main after revert)
    cur = open(f, 'rb').read()
    for _ in range(6):
        nxt = reverse_runs(cur)
        ok = True
        try: nxt.decode('utf-8')
        except Exception: ok = False
        if not ok:
            break
        if fam(nxt) == fam(cur) or nxt == cur:
            cur = nxt
            break
        cur = nxt
    total += fam(cur)
    print(f'== {f}')
    print(f'   residual mojibake-family now: {fam(cur)}  (was {fam(open(f,"rb").read())} before this run on disk: {subprocess.run(["git","show","origin/main:"+f],capture_output=True).stdout and fam(subprocess.run(["git","show","origin/main:"+f],capture_output=True).stdout)})')
    print(f'   utf8 valid: {bool(cur.decode("utf-8", errors="strict"))}')
    open(f, 'wb').write(cur)
print(f'\nTOTAL residual across 3 files: {total}')
