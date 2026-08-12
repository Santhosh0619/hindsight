from fastapi import APIRouter, Request, Response, status

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import RateLimitedError, UnauthorizedError
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MembershipOut,
    MeResponse,
    SignupRequest,
    UserOut,
)
from app.services import auth_service
from app.services.rate_limit import demo_signup_bucket
from app.services.workspace_service import list_my_workspaces

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE_NAME = "refresh_token"
# Must match the mounted path, not just the router's own prefix — app.main mounts this
# router under /api/v1, so the cookie has to be scoped to /api/v1/auth or a browser
# won't send it back to /api/v1/auth/refresh at all (cookie path is a URL-path prefix
# match, not router-relative). Caught by an actual curl walkthrough, not by ruff/mypy.
_REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        path=_REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: DbSession, response: Response) -> AuthResponse:
    user, access_token, raw_refresh = await auth_service.signup(
        db, email=payload.email, password=payload.password, full_name=payload.full_name
    )
    _set_refresh_cookie(response, raw_refresh)
    return AuthResponse(access_token=access_token, user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: DbSession, response: Response) -> AuthResponse:
    user, access_token, raw_refresh = await auth_service.login(
        db, email=payload.email, password=payload.password
    )
    _set_refresh_cookie(response, raw_refresh)
    return AuthResponse(access_token=access_token, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: Request, db: DbSession, response: Response) -> AuthResponse:
    raw_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if raw_token is None:
        raise UnauthorizedError("Missing refresh token cookie")

    user, access_token, new_raw_refresh = await auth_service.refresh(db, raw_token=raw_token)
    _set_refresh_cookie(response, new_raw_refresh)
    return AuthResponse(access_token=access_token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: DbSession, response: Response) -> None:
    raw_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    await auth_service.logout(db, raw_token=raw_token)
    response.delete_cookie(key=_REFRESH_COOKIE_NAME, path=_REFRESH_COOKIE_PATH)


@router.post("/demo", response_model=AuthResponse)
async def demo(request: Request, db: DbSession, response: Response) -> AuthResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not demo_signup_bucket.consume(client_ip):
        raise RateLimitedError("Too many demo sessions requested — try again shortly")

    user, access_token, raw_refresh = await auth_service.create_demo_guest(db)
    _set_refresh_cookie(response, raw_refresh)
    return AuthResponse(access_token=access_token, user=UserOut.model_validate(user))


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser, db: DbSession) -> MeResponse:
    memberships = await list_my_workspaces(db, current_user)
    return MeResponse(
        user=UserOut.model_validate(current_user),
        memberships=[
            MembershipOut(
                workspace_id=workspace.id,
                workspace_name=workspace.name,
                workspace_slug=workspace.slug,
                role=role,
            )
            for workspace, role in memberships
        ],
    )
