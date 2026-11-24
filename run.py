"""TenantShield Main Entry Point

Launches the FastAPI backend and serves the frontend.
"""

import sys
import uvicorn
from app.config import settings

def main():
    print("=" * 60)
    print(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    print(f"Environment: {settings.ENVIRONMENT} | Debug: {settings.DEBUG}")
    print(f"Web Dashboard:   http://{settings.HOST}:{settings.PORT}")
    print(f"Health Endpoint: http://{settings.HOST}:{settings.PORT}/health")
    print(f"Status Endpoint: http://{settings.HOST}:{settings.PORT}/api/status")
    print(f"API Docs:        http://{settings.HOST}:{settings.PORT}/docs")
    print("=" * 60)
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,  # Single-process clean execution for hackathon dev
        log_level="info",
    )

if __name__ == "__main__":
    main()
