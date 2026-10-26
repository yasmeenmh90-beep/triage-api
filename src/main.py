import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.routes.triage import router as triage_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(title="triage-api", version="1.0.0")


@app.exception_handler(RequestValidationError)
async def bad_input(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Bad input is a 400 that names the field — and costs zero model calls."""
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err["loc"] if p != "body"]
        errors.append({"field": ".".join(loc) or "body", "message": err["msg"]})
    return JSONResponse(status_code=400, content={"error": "invalid_input", "details": errors})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(triage_router)
