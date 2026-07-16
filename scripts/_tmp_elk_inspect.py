from pathlib import Path
e = Path("frontend/design-system/vendor/elk.bundled.js").read_text(encoding="utf-8", errors="replace")
needle = "workerUrl === 'undefined' && typeof workerFactory === 'undefined'"
i = e.find(needle)
print("idx", i)
print(e[i - 400 : i + 900] if i >= 0 else "not found")
print("====")
# also search for execute in main thread path
for needle2 in ["__webworker__", "runAsWorker", "main thread", "no worker", "algorithms"]:
    print(needle2, e.find(needle2))
