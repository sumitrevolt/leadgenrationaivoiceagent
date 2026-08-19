import sys

with open("scripts/buzz_start_harness.py", encoding="utf-8") as f:
    text = f.read()

text = text.replace(
    'choices=["Boss", "Bumble", "Fizz", "Honey"]',
    'choices=["Boss", "Bumble", "Fizz", "Honey", "Comb"]',
)

with open("scripts/buzz_start_harness.py", "w", encoding="utf-8") as f:
    f.write(text)
