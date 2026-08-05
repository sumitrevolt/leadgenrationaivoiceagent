#!/usr/bin/env python3
"""Tier 2 trigger and routing checks. Deterministic, CI-safe, no model.

Vendored from Shubhamsaboo/awesome-llm-apps at commit 779e9f9bcf87fa8c.
LeadGen adaptations: explicit catalog/eval roots, UTF-8 reads on Windows, and
an ``only`` mode so newly changed skills are checked against the full catalog
without grandfathered catalog debt making unrelated changes fail.
"""

import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SKILLS_ROOT = os.path.join(REPO_ROOT, ".claude", "skills")
EVALS_ROOT = os.path.join(HERE, "cases")

STOP = set(
    """a an the and or of to in on for with is are was were be been it its this
that those these you your i me my we our they their he she his her do does did done
can could should would will just very really some any all not no yes if then than as
at by from into out up down over under again more most other own same so too s t don
""".split()
)

MARGIN = 1.15


def tokens(text):
    out = set()
    for word in re.findall(r"[a-z0-9']+", text.lower()):
        if word in STOP or len(word) < 3:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[: -len(suffix)]
                break
        out.add(word)
    return out


def description_of(skill_dir):
    with open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(r"^description:\s*(.+?)^(?=[a-zA-Z-]+:|---)", text, re.S | re.M)
    return match.group(1) if match else ""


def score(prompt_tokens, description_tokens):
    if not prompt_tokens:
        return 0.0
    return len(prompt_tokens & description_tokens) / math.sqrt(len(prompt_tokens))


def evaluate(skills_root=SKILLS_ROOT, evals_root=EVALS_ROOT, only=None):
    skills_root = os.path.abspath(skills_root)
    evals_root = os.path.abspath(evals_root)
    selected = set(only) if only else None
    skills = {}
    for entry in sorted(os.listdir(skills_root)):
        skill_file = os.path.join(skills_root, entry, "SKILL.md")
        if os.path.exists(skill_file):
            skills[entry] = tokens(description_of(os.path.join(skills_root, entry)))
    if not skills:
        print("no skills found under %s" % skills_root)
        return 1

    unknown = sorted(selected - set(skills)) if selected else []
    if unknown:
        print("FAIL  selected skill(s) not found: %s" % ", ".join(unknown))
        return 1

    failures = 0
    names = sorted(skills)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            if selected is not None and not ({first, second} & selected):
                continue
            left, right = skills[first], skills[second]
            overlap = len(left & right) / max(1, min(len(left), len(right)))
            if overlap > 0.5:
                print(
                    "FAIL  descriptions near-collide: %s vs %s (%.0f%% shared vocabulary)"
                    % (first, second, overlap * 100)
                )
                failures += 1

    target_names = names if selected is None else [name for name in names if name in selected]
    for name in target_names:
        case_file = os.path.join(evals_root, name, "trigger-cases.json")
        if not os.path.exists(case_file):
            print("WARN  %s has no trigger-cases.json - add one" % name)
            continue
        with open(case_file, encoding="utf-8") as handle:
            cases = json.load(handle)["cases"]
        positives, negatives = [], []
        for case in cases:
            if case.get("lexical") is False:
                continue
            case_score = score(tokens(case["prompt"]), skills[name])
            (positives if case["should_trigger"] else negatives).append((case_score, case["id"]))
            if case["should_trigger"] and len(skills) > 1:
                best = max(skills, key=lambda key: score(tokens(case["prompt"]), skills[key]))
                if best != name:
                    print("FAIL  %s: %r routes to %s instead" % (name, case["id"], best))
                    failures += 1
        if positives and negatives:
            worst_positive, positive_id = min(positives)
            best_negative, negative_id = max(negatives)
            if worst_positive <= best_negative * MARGIN:
                print(
                    "FAIL  %s: weakest positive %r (%.2f) does not clear strongest "
                    "near-miss %r (%.2f)"
                    % (name, positive_id, worst_positive, negative_id, best_negative)
                )
                failures += 1
            else:
                print(
                    "PASS  %s: %d positives clear %d near-misses (weakest %.2f vs strongest %.2f)"
                    % (name, len(positives), len(negatives), worst_positive, best_negative)
                )

    if failures:
        print("\n%d failure(s)" % failures)
        return 1
    print(
        "\ntrigger & routing: all clear (%d checked; %d catalog skill%s)"
        % (len(target_names), len(skills), "" if len(skills) == 1 else "s")
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deterministic skill trigger and routing checks.")
    parser.add_argument("--skills-root", default=SKILLS_ROOT)
    parser.add_argument("--evals-root", default=EVALS_ROOT)
    parser.add_argument("--only", action="append", default=[], metavar="SKILL")
    args = parser.parse_args(argv)
    return evaluate(args.skills_root, args.evals_root, only=args.only or None)


if __name__ == "__main__":
    sys.exit(main())
