"""Minimal Agent 入口"""
import os
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    import uvicorn
    from api.server import app

    uvicorn.run(app, host="0.0.0.0", port=8000)
