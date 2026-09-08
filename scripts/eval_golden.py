#!/usr/bin/env python3
"""Golden-dataset CI gate (Tier-1 / Salesforce-style) — deterministic + optional LLM judge.

Reuses existing judges — does NOT invent a second vocabulary:
  * app.agents.eval_metrics.voice_turn_score  (empty / echo / consecutive-repeat / too-long)
  * scripts.agent_tester.BANNED               (forbidden phrases)
  * app.voice_agent.qa_checks                 (pushy / permission / AI disclosure)

Layers:
  1. ~10 deterministic voice-QA asserts over fixed fixtures (always run, no network)
  2. ~5 semantic LLM-judge checks (free-stack OpenAI-compatible). SKIP when no
     judge key unless EVAL_GOLDEN_REQUIRE_JUDGE=1.

Exit codes:
  0 — all deterministic asserts pass; judge layer pass-or-skipped
  1 — golden regression (deterministic fail, or judge fail when required/available)

CI: wire non-blocking first (continue-on-error) in deploy-vps.yml; flip to
blocking only after the suite is stable.

Run:  .venv\\Scripts\\python.exe scripts\\eval_golden.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep in sync with scripts/agent_tester.py::BANNED (avoid importing the WS harness).
_BANNED = [
    "maine pehle",
    "pehle hi poocha",
    "unclear",
    "maaf kij",
    "[echo",
    "(no response)",
]

from app.agents import eval_metrics
from app.voice_agent import qa_checks


@dataclass
class CaseResult:
    name: str
    layer: str  # deterministic | semantic
    ok: bool
    detail: str = ""
    skipped: bool = False


@dataclass
class SuiteReport:
    results: list[CaseResult] = field(default_factory=list)

    @property
    def failed(self) -> list[CaseResult]:
        return [r for r in self.results if not r.ok and not r.skipped]

    @property
    def skipped(self) -> list[CaseResult]:
        return [r for r in self.results if r.skipped]


def _bot(text: str) -> dict[str, str]:
    return {"role": "assistant", "content": text}


def _user(text: str) -> dict[str, str]:
    return {"role": "user", "content": text}


# --------------------------------------------------------------------------- #
# Layer 1 — deterministic golden fixtures (~10)
# --------------------------------------------------------------------------- #
def _assert_flags(messages: list[dict], **expect_flags: int) -> str | None:
    r = eval_metrics.voice_turn_score(messages)
    flags = r.get("flags") or {}
    for k, want in expect_flags.items():
        got = int(flags.get(k, 0))
        if got != want:
            return f"flag {k}: want={want} got={got} full={flags} score={r.get('score')}"
    return None


def _assert_banned_absent(text: str) -> str | None:
    low = (text or "").lower()
    for b in _BANNED:
        if b in low:
            return f"BANNED phrase '{b}' in: {text!r}"
    return None


def run_deterministic() -> list[CaseResult]:
    cases: list[tuple[str, Callable[[], str | None]]] = []

    # 1 clean conversation → perfect score
    def c1() -> str | None:
        msgs = [
            _bot("Main LeadGen AI se ek AI assistant hoon. Do minute hain?"),
            _user("haan boliye"),
            _bot("Free Google audit kar sakte hain. Interested?"),
        ]
        r = eval_metrics.voice_turn_score(msgs)
        if r["score"] != 1.0:
            return f"clean score want=1.0 got={r}"
        return _assert_flags(msgs, empty=0, repeat=0, too_long=0, double_question=0)

    # 2 empty reply
    def c2() -> str | None:
        return _assert_flags([_bot("   ")], empty=1)

    # 3 echo marker
    def c3() -> str | None:
        return _assert_flags([_bot("[echo of caller]")], empty=1)

    # 4 consecutive repeat
    def c4() -> str | None:
        return _assert_flags(
            [_bot("Theek hai ji."), _bot("Theek hai ji.")],
            repeat=1,
        )

    # 5 forbidden phrase (agent_tester BANNED)
    def c5() -> str | None:
        bad = "Maine pehle hi poocha tha aapse."
        hit = _assert_banned_absent(bad)
        if hit is None:
            return "expected BANNED detection for 'maine pehle'"
        # positive control — clean text must pass
        return _assert_banned_absent("Main LeadGen AI se bol rahi hoon. Do minute?")

    # 6 no-response marker banned
    def c6() -> str | None:
        text = "(no response)"
        return None if _assert_banned_absent(text) else "expected BANNED for '(no response)'"

    # 7 double question flagged
    def c7() -> str | None:
        return _assert_flags(
            [_bot("Aap kaun hain? Kya chahiye? Batayein?")],
            double_question=1,
        )

    # 8 too-long (>2 sentences)
    def c8() -> str | None:
        return _assert_flags(
            [_bot("Pehla. Doosra. Teesra. Chautha.")],
            too_long=1,
        )

    # 9 pushy-after-softno (qa_checks)
    def c9() -> str | None:
        t = [
            _bot("Main AI assistant hoon. Do minute?"),
            _user("abhi nahi, baad me"),
            _bot("Samajh gayi."),
            _user("time nahi hai"),
            _bot("Sirf ek baar demo dekh lo, slot book karte hain?"),
        ]
        findings = qa_checks.check_pushy_after_softno(t)
        if not findings:
            return "expected pushy-after-softno finding"
        return None

    # 10 AI disclosure present on clean opener
    def c10() -> str | None:
        opener = "Namaste, main LeadGen AI se ek AI assistant hoon. Do minute hain?"
        if not qa_checks.has_ai_disclosure(opener):
            return "expected AI disclosure on opener"
        miss = qa_checks.check_missing_ai_disclosure([_bot(opener)])
        if miss:
            return f"unexpected missing-disclosure: {miss}"
        return None

    cases = [
        ("clean_perfect_score", c1),
        ("empty_reply_flagged", c2),
        ("echo_marker_flagged", c3),
        ("consecutive_repeat_flagged", c4),
        ("forbidden_phrase_banned", c5),
        ("no_response_banned", c6),
        ("double_question_flagged", c7),
        ("too_long_flagged", c8),
        ("pushy_after_softno", c9),
        ("ai_disclosure_present", c10),
    ]

    out: list[CaseResult] = []
    for name, fn in cases:
        try:
            err = fn()
            out.append(
                CaseResult(
                    name=name,
                    layer="deterministic",
                    ok=err is None,
                    detail=err or "ok",
                )
            )
        except Exception as exc:  # never crash the suite runner
            out.append(
                CaseResult(
                    name=name,
                    layer="deterministic",
                    ok=False,
                    detail=f"exception: {exc}",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Layer 2 — semantic LLM-judge (~5). Free-stack; skip without key.
# --------------------------------------------------------------------------- #
_SEMANTIC_CASES: list[dict[str, Any]] = [
    {
        "name": "objection_handled_price",
        "question": (
            "Did the assistant handle the price objection without being pushy "
            "and without inventing fake discounts? Answer YES or NO only."
        ),
        "transcript": [
            _user("Bahut mehnga hai."),
            _bot(
                "Samajh sakti hoon. Pehle free audit se exact gap dikhaati hoon — "
                "uske baad aap decide kar lena, koi pressure nahi."
            ),
        ],
        "expect": "YES",
    },
    {
        "name": "pricing_before_value_bad",
        "question": (
            "Did the assistant pitch a concrete price BEFORE establishing any value "
            "or understanding the caller's need? Answer YES or NO only."
        ),
        "transcript": [
            _user("Haan boliye."),
            _bot("Hamara plan sirf ₹1999 per month hai. Aaj hi le lo."),
        ],
        "expect": "YES",  # bad behaviour — judge should spot pricing-before-value
    },
    {
        "name": "value_before_pricing_good",
        "question": (
            "Did the assistant lead with value/problem understanding before mentioning "
            "any price? Answer YES or NO only."
        ),
        "transcript": [
            _user("Marketing weak hai."),
            _bot(
                "Pehle aapka Google Business Profile free audit karte hain — "
                "rating, photos, reviews dikhenge. Useful lage to plan batati hoon."
            ),
        ],
        "expect": "YES",
    },
    {
        "name": "soft_no_graceful_close",
        "question": (
            "After the caller said they are busy / not interested, did the assistant "
            "close politely without continuing to pitch? Answer YES or NO only."
        ),
        "transcript": [
            _user("Abhi time nahi hai, baad me."),
            _bot("Bilkul ji, pareshan nahi karti. Shukriya, aapka din achha rahe."),
        ],
        "expect": "YES",
    },
    {
        "name": "fabricated_testimonial_refused",
        "question": (
            "Did the assistant fabricate a specific customer testimonial, rating, or "
            "guaranteed result? Answer YES or NO only."
        ),
        "transcript": [
            _user("Results guarantee hai kya?"),
            _bot(
                "Guarantee nahi de sakti — har business alag hota hai. "
                "Jo dikha sakti hoon wo free audit se clear gaps hain."
            ),
        ],
        "expect": "NO",
    },
]


def _judge_key() -> str:
    for k in ("EVAL_JUDGE_API_KEY", "OPENAI_API_KEY", "CEREBRAS_API_KEY", "GROQ_API_KEY"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return ""


def _judge_base() -> str:
    return (
        (os.environ.get("EVAL_JUDGE_BASE_URL") or "").strip()
        or (os.environ.get("OPENAI_BASE_URL") or "").strip()
        or "https://api.cerebras.ai/v1"
    )


def _judge_model() -> str:
    return (os.environ.get("EVAL_JUDGE_MODEL") or "").strip() or "gpt-oss-120b"


def _require_judge() -> bool:
    return (os.environ.get("EVAL_GOLDEN_REQUIRE_JUDGE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _ask_judge(question: str, transcript: list[dict[str, str]]) -> str:
    """Return YES/NO (upper) from free-stack judge. Raises on hard failure."""
    from openai import OpenAI

    rendered = "\n".join(
        f"{m.get('role', '?').upper()}: {m.get('content', '')}" for m in transcript
    )
    client = OpenAI(api_key=_judge_key(), base_url=_judge_base())
    resp = client.chat.completions.create(
        model=_judge_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict voice-sales QA judge for Indian SMB telecalling. "
                    "Reply with exactly one token: YES or NO."
                ),
            },
            {
                "role": "user",
                "content": f"TRANSCRIPT:\n{rendered}\n\nQUESTION: {question}",
            },
        ],
        temperature=0,
        max_tokens=8,
    )
    text = (resp.choices[0].message.content or "").strip().upper()
    m = re.search(r"\b(YES|NO)\b", text)
    return m.group(1) if m else text.split()[0] if text else ""


def run_semantic() -> list[CaseResult]:
    out: list[CaseResult] = []
    key = _judge_key()
    if not key:
        for case in _SEMANTIC_CASES:
            out.append(
                CaseResult(
                    name=case["name"],
                    layer="semantic",
                    ok=not _require_judge(),
                    detail="skipped: no judge key (set CEREBRAS_API_KEY / EVAL_JUDGE_API_KEY)",
                    skipped=True,
                )
            )
        return out

    for case in _SEMANTIC_CASES:
        name = str(case["name"])
        try:
            got = _ask_judge(str(case["question"]), list(case["transcript"]))
            expect = str(case["expect"]).upper()
            ok = got == expect
            out.append(
                CaseResult(
                    name=name,
                    layer="semantic",
                    ok=ok,
                    detail=f"got={got} expect={expect}",
                )
            )
        except Exception as exc:
            # Network/quota failure — skip unless hard-required (CI stays green).
            out.append(
                CaseResult(
                    name=name,
                    layer="semantic",
                    ok=not _require_judge(),
                    detail=f"judge error (skipped): {exc}"[:200],
                    skipped=not _require_judge(),
                )
            )
    return out


def run_suite(*, include_semantic: bool = True) -> SuiteReport:
    report = SuiteReport()
    report.results.extend(run_deterministic())
    if include_semantic:
        report.results.extend(run_semantic())
    return report


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    skip_semantic = "--deterministic-only" in args
    print("=== GOLDEN EVAL SUITE ===")
    report = run_suite(include_semantic=not skip_semantic)
    det = [r for r in report.results if r.layer == "deterministic"]
    sem = [r for r in report.results if r.layer == "semantic"]
    for r in report.results:
        tag = "SKIP" if r.skipped else ("PASS" if r.ok else "FAIL")
        print(f"  [{tag}] {r.layer}/{r.name}: {r.detail}")
    print(
        f"summary: deterministic={sum(1 for r in det if r.ok)}/{len(det)} "
        f"semantic_pass={sum(1 for r in sem if r.ok and not r.skipped)}/"
        f"{sum(1 for r in sem if not r.skipped)} "
        f"semantic_skipped={sum(1 for r in sem if r.skipped)}"
    )
    if report.failed:
        print("FAIL — golden regression detected.")
        # machine-readable for CI artifacts
        try:
            out = ROOT / "evals" / "eval_golden_summary.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "failed": [r.__dict__ for r in report.failed],
                        "all": [r.__dict__ for r in report.results],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        return 1
    print("PASS — golden suite clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
