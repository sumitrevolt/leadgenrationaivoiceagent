# Squad Lead — Data & RAG (Squad 7)
# Responsibility: Qdrant vector store, RAG pipeline, kb_main namespace
# Autopilot: Auto-scaling, daily vector backup, retrieval quality checks

import subprocess

from app.utils.logger import setup_logger

logger = setup_logger(__name__)
squad_name = "Data & RAG"
status = "GREEN"
capacity = 66

def vector_backup():
    """Daily Qdrant vector store backup + integrity check."""
    result = subprocess.run(
        ["bash", "-c", "python3 -c \"from app.platform.qdrant_utils import backup_kb_main; print(backup_kb_main())\""],
        cwd="/opt/leadgen", capture_output=True, text=True
    )
    output = result.stdout.strip()
    return {"status": "backup_ran", "output": output}

def retrieval_quality(query: str, top_k: int = 5):
    """Test RAG retrieval quality for given query."""
    result = subprocess.run(
        ["bash", "-c", f"python3 -c \"from app.platform.qdrant import search_kb_main; results = search_kb_main('{query}', top_k={top_k}); print(f'Found {len(results)} results')\""],
        cwd="/opt/leadgen", capture_output=True, text=True
    )
    return {"status": "quality_check", "query": query, "results": result.stdout}

def namespace_health():
    """Check all namespace health in Qdrant: niche:/client:<id>/skills."""
    result = subprocess.run(
        ["bash", "-c", "python3 -c \"from app.platform.qdrant import list_namespaces; print(list_namespaces())\""],
        cwd="/opt/leadgen", capture_output=True, text=True
    )
    return {"status": "namespace_health", "output": result.stdout}

# Export for autopilot registration
__all__ = ["squad_name", "status", "capacity", "vector_backup", "retrieval_quality", "namespace_health"]
