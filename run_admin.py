"""
LeadGen AI - Admin Command Center (Standalone Microservice)
Runs independently from main app - no main.py modification needed.
"""

from fastapi import FastAPI
from app.admin.main import admin_router

app = FastAPI(
    title="LeadGen AI - Admin Command Center",
    description="Real-time system monitoring, worker coordination, task ledger",
    version="1.0.0"
)

app.include_router(admin_router)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "admin-command-center"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
