from dataclasses import dataclass
from fastapi import Request


@dataclass(frozen=True)
class RequestContext:
    user_subject: str
    org_id: str
    request_id: str | None
    authorization: str | None


def context_from_request(request: Request) -> RequestContext:
    return RequestContext(
        user_subject=request.headers.get("X-User-Subject", "user:local-dev"),
        org_id=request.headers.get("X-Org-Id", "org:aegis-demo"),
        request_id=request.headers.get("X-Request-Id"),
        authorization=request.headers.get("Authorization"),
    )
