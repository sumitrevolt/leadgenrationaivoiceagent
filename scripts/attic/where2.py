# Mimic uvicorn's import resolution: run as `cd /opt/leadgen && .venv/bin/python scripts/where2.py`
# (NO PYTHONPATH=., NO sys.path hacks) to see exactly which modules uvicorn loads.
import app

print("app pkg   :", getattr(app, "__file__", "?"), "| path:", list(getattr(app, "__path__", [])))
import app.main as m

print("app.main  :", m.__file__)
print("has /app/login:", "/app/login" in [str(getattr(r, "path", "")) for r in m.app.routes])
try:
    import app.cache as c

    print("app.cache :", getattr(c, "__file__", "?"))
except Exception as e:
    print("app.cache ERR:", repr(e)[:90])
