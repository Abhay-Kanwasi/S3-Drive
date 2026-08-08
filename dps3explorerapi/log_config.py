from fastapi import FastAPI
import time
import logging.handlers


def configure_logger(name: str, level: str):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger


def customAccessLogger(app: FastAPI, logger) -> None:
    @app.middleware("http")
    async def log_request(request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            f"{request.method} {request.url} took {process_time:.2f} seconds {response.status_code}"
        )
        return response
