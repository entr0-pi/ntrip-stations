import os
import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

if __name__ == "__main__":
    # Production: use 127.0.0.1 (behind reverse proxy)
    # Development: use 0.0.0.0 (direct access)
    is_production = os.getenv("ENVIRONMENT") == "production"

    # Host can be configured via SERVER_HOST env var
    # Default: 127.0.0.1 for production, 0.0.0.0 for development
    default_host = "127.0.0.1" if is_production else "0.0.0.0"
    host = os.getenv("SERVER_HOST", default_host)

    uvicorn.run(
        "app.main:app",
        host=host,
        port=8000,
        reload=not is_production,
        access_log=True,
    )
