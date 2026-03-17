import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.patients.endpoints import router as patients_router
from .config import settings
from .database import init_db
from .logger import setup_logging, get_logger
from .middleware.auth import AuthMiddleware
from .middleware.rate_limiter import RateLimiterMiddleware

setup_logging()
logger = get_logger(__name__)


app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0", debug=settings.DEBUG)


@app.on_event("startup")
def startup():
    # init_db()
    logger.info("Database initialized")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(AuthMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests and responses."""
    start_time = time.time()
    logger.info(f"Request: {request.method} {request.url}")

    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            f"Response: {response.status_code} - "
            f"Time: {process_time:.4f}s - "
            f"URL: {request.url}"
        )
        return response

    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            f"Error processing request: {str(e)} - "
            f"Time: {process_time:.4f}s - "
            f"URL: {request.url}"
        )
        raise


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions."""
    logger.error(f"Unhandled exception: {str(exc)} - URL: {request.url}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(patients_router, prefix="/patients")


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Hello World"}
