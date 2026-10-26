from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.llm.schema import STUB_VERDICT, TriageRequest, TriageResponse
from src.llm.service import TriageFailed, triage_text

router = APIRouter()


@router.post("/triage", response_model=TriageResponse)
def triage(body: TriageRequest, response: Response):
    settings = get_settings()

    if settings.stub:
        response.headers["X-Triage-Source"] = "stub"
        return TriageResponse.from_verdict(STUB_VERDICT)

    try:
        result = triage_text(body.text)
    except TriageFailed as exc:
        # Never return raw model text — only a clear message. The raw output is in quarantine.
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_model_output",
                "message": "The model's answer failed validation twice and was quarantined.",
                "detail": str(exc),
            },
        )

    response.headers["X-Triage-Source"] = "model"
    return result
