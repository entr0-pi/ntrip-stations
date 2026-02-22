import os
import uvicorn

if __name__ == "__main__":
    # Production: use 127.0.0.1 (behind reverse proxy)
    # Development: use 0.0.0.0 (direct access)
    is_production = os.getenv("ENVIRONMENT") == "production"

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1" if is_production else "0.0.0.0",
        port=8000,
        reload=not is_production,
        access_log=True,
    )
