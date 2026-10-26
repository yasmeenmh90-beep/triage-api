from fastapi import APIRouter, Response

from src.config import get_settings
from src.llm.schema import STUB_VERDICT, TriageRequest, TriageResponse

router = APIRouter()


@router.post("/triage", response_model=TriageResponse)
def triage(body: TriageRequest, response: Response) -> TriageResponse:
    settings = get_settings()

    if settings.stub:
        response.headers["X-Triage-Source"] = "stub"
        return TriageResponse.from_verdict(STUB_VERDICT)

    # Model call arrives in Stage 2.
    response.headers["X-Triage-Source"] = "stub"
    return TriageResponse.from_verdict(STUB_VERDICT)
