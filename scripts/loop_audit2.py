"""Focused audit: only REAL incomplete loops (not except/try pass)"""
import re
from pathlib import Path

BASE = Path(r"C:\Users\Ratanshila\Documents\leadgenrationaiagent")

def read(p):
    try: return Path(p).read_text(encoding='utf-8', errors='ignore')
    except: return ""

def get_context(src, pos, lines=3):
    before = src[:pos].split('\n')
    after = src[pos:].split('\n')
    ctx = before[-lines:] + after[:lines]
    return '\n'.join(ctx)

# --- 1. TODO/FIXME (real ones, high priority) ---
print("=" * 60)
print("REAL TODOs (not in except/comment-only)")
print("=" * 60)
for f in sorted(BASE.rglob("app/**/*.py")):
    src = read(f)
    for m in re.finditer(r'#\s*(TODO|FIXME)[^\n]*', src):
        ln = src[:m.start()].count('\n') + 1
        print(f"  {f.relative_to(BASE)}:L{ln}  {m.group().strip()}")

# --- 2. return {} inside non-except, non-empty function (likely stub) ---
print("\n" + "=" * 60)
print("FUNCTIONS with 'return {}' that look like real stubs")
print("=" * 60)

TARGET_FILES = [
    'app/platform/orchestrator.py',
    'app/billing/subscription.py',
    'app/platform/crm_sync.py',
    'app/voice_agent/call_qualifier.py',
    'app/api/admin_dashboard.py',
    'app/platform/call_prep.py',
    'app/marketing/niche_pack.py',
    'app/marketing/post_generator.py',
    'app/marketing/seo_pages.py',
    'app/voice_agent/function_calling.py',
    'app/voice_agent/telecaller_brain.py',
]

for rel in TARGET_FILES:
    p = BASE / rel.replace('/', '\\')
    src = read(p)
    if not src: continue
    hits = []
    for m in re.finditer(r'return \{\}', src):
        ln = src[:m.start()].count('\n') + 1
        ctx = get_context(src, m.start(), 2)
        # skip if inside except block
        block = ctx.strip()
        hits.append((ln, block))
    if hits:
        print(f"\n--- {rel} ---")
        for ln, ctx in hits:
            print(f"  L{ln}: {ctx[:120]}")

# --- 3. admin_dashboard fake data ---
print("\n" + "=" * 60)
print("FAKE/HARDCODED DATA in admin_dashboard.py")
print("=" * 60)
src = read(BASE / 'app\\api\\admin_dashboard.py')
for m in re.finditer(r'(fake|mock|dummy|hardcoded|sample_data|TODO)[^\n]*', src, re.IGNORECASE):
    ln = src[:m.start()].count('\n') + 1
    print(f"  L{ln}: {m.group().strip()[:100]}")
