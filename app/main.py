from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.routes import router as api_router
from app.storage.database import init_db, close_db
from app.tools.files import register_file_tools
from app.tools.browser import register_browser_tools, browser_manager
from app.tools.desktop import register_desktop_tools
from app.tools.verification import register_verification_tools
from app.tools.terminal import register_terminal_tools
from app.tools.vscode import register_vscode_tools
from app.tools.memory import register_memory_tools
from app.tools.scheduler import register_scheduler_tools
from app.tools.registry import tool_registry
from app.models.base import model_registry
from app.models.gemini import create_gemini_provider
from app.models.nemotron import create_nemotron_provider
from app.config import settings
from app.security.path_policy import path_policy
import os
import logging
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("./data/workspace", exist_ok=True)
    os.makedirs("./data/reports", exist_ok=True)
    os.makedirs("./logs", exist_ok=True)
    
    logger.add(settings.log_file, level=settings.log_level, rotation="10 MB", retention="7 days")
    logger.info("Starting Personal AI Agent")
    
    await init_db()
    
    register_file_tools(tool_registry)
    register_browser_tools(tool_registry)
    register_desktop_tools(tool_registry)
    register_verification_tools(tool_registry)
    register_terminal_tools(tool_registry)
    register_vscode_tools(tool_registry)
    register_memory_tools(tool_registry)
    register_scheduler_tools(tool_registry)
    
    # Initialize model provider based on configuration
    try:
        if settings.model_provider == "gemini":
            provider = await create_gemini_provider()
            model_registry.register("gemini", provider, default=True)
            logger.info("Gemini model provider connected successfully")
        elif settings.model_provider == "nemotron":
            provider = await create_nemotron_provider()
            model_registry.register("nemotron", provider, default=True)
            logger.info("Nemotron model provider connected successfully")
        else:
            logger.warning(f"Unknown model provider: {settings.model_provider}")
    except Exception as e:
        logger.warning(f"Model provider not available: {e}. Running in limited mode.")
    
    logger.info("Application started successfully")
    yield
    
    await browser_manager.close()
    await close_db()
    logger.info("Application shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    return {"name": settings.app_name, "version": settings.app_version, "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)