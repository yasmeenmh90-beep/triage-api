from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.llm.client import LLMTimeout, LLMUnavailable
from src.llm.schema import STUB_VERDICT, TriageRequest, TriageResponse
from src.llm.service import FALLBACK_VERDICT, TriageFailed, triage_text

router = APIRouter()


def _error(status: int, code: str, message: str, detail: str | None = None) -> JSONResponse:
    content = {"error": code, "message": message}
    if detail:
        content["detail"] = detail
    return JSONResponse(status_code=status, content=content)


@router.post("/triage", response_model=TriageResponse)
def triage(body: TriageRequest, response: Response):
    settings = get_settings()

    # Kill switch first: someone who is not the developer can turn the model off without a deploy.
    if not settings.enabled:
        response.headers["X-Triage-Source"] = "fallback"
        return TriageResponse.from_verdict(FALLBACK_VERDICT)

    if settings.stub:
        response.headers["X-Triage-Source"] = "stub"
        return TriageResponse.from_verdict(STUB_VERDICT)

    try:
        result = triage_text(body.text)
    except TriageFailed as exc:
        # Never return raw model text — only a clear message. The raw output is in quarantine.
        return _error(422, "invalid_model_output",
                      "The model's answer failed validation twice and was quarantined.", str(exc))
    except LLMTimeout as exc:
        return _error(504, "model_timeout", str(exc))
    except LLMUnavailable as exc:
        return _error(502, "model_unavailable", str(exc))

    response.headers["X-Triage-Source"] = "model"
    return result
