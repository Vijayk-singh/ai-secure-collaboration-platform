import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.redis import redis_service
from app.websocket.manager import pubsub_listener
from app.websocket.endpoints import router as ws_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the startup and shutdown events for the entire application,
    initializing databases, loggers, caches, and system clients.
    """
    # 1. Startup Logic
    setup_logging()
    logger.info("Initializing system services...")
    
    # Initialize Redis connection pool
    redis_service.init_redis()
    redis_healthy = await redis_service.ping()
    if redis_healthy:
        logger.info("Connection to Redis pool established successfully.")
        # Start background Redis Pub/Sub subscription loop
        pubsub_listener.start()
    else:
        logger.warning("Redis service is not reachable on startup.")

    logger.info(f"{settings.PROJECT_NAME} backend has started successfully under {settings.ENV} mode.")
    
    yield

    # 2. Shutdown Logic
    logger.info("Shutting down system services...")
    # Stop background Redis Pub/Sub subscription loop
    await pubsub_listener.stop()
    await redis_service.close()
    logger.info("System services shut down. Goodbye.")

# Create the FastAPI instance
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="A highly-scalable, production-ready backend platform demonstrating mature software engineering.",
    version="1.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Set up standard CORS headers
# In production, specify exact domain URLs to restrict access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Register all API endpoints
app.include_router(api_router, prefix=settings.API_V1_STR)
# Register WebSocket endpoints
app.include_router(ws_router)

# Mount static folder holding index.html, style.css, and app.js
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def root():
    """
    Serves the premium single-page application dashboard.
    """
    return FileResponse("app/static/index.html")
