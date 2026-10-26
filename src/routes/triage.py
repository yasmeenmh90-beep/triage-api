from fastapi import APIRouter, Response

from src.config import get_settings
from src.llm.client import chat
from src.llm.prompt import build_messages, prompt_version
from src.llm.schema import STUB_VERDICT, TriageRequest, TriageResponse

router = APIRouter()


@router.post("/triage")
def triage(body: TriageRequest, response: Response):
    settings = get_settings()

    if settings.stub:
        response.headers["X-Triage-Source"] = "stub"
        return TriageResponse.from_verdict(STUB_VERDICT)

    # Stage 2 only: return the raw model text so we can read it. Stage 3 replaces this.
    raw = chat(build_messages(body.text, prompt_version()))
    response.headers["X-Triage-Source"] = "model"
    return {"raw": raw, "prompt_version": prompt_version()}
