# SUPERSEDED — see docs/_route_usage_method.md

The earlier static "safe to delete" idea was retracted: static cross-referencing
cannot prove a route is dead (dynamic frontend URLs + external/webhook callers).
Use **real traffic** instead:

    python scripts/route_usage_audit.py --access-log /opt/leadgen/logs/access.log

Full explanation and the 593->~400 plan: docs/_route_usage_method.md
Static starting points (review only): docs/_route_candidates_all.md
