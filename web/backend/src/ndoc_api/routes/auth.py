"""Login, logout, current user, own password."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from ..auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Session,
    UserStore,
    current_session,
    get_store,
)
from ..errors import responses
from ..models import LoginRequest, PasswordChange, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookies(request: Request, response: Response, token: str, csrf: str) -> None:
    settings = request.app.state.settings
    max_age = int(settings.session_hours * 3600)
    common = {"secure": settings.cookie_secure, "samesite": "strict", "max_age": max_age}
    response.set_cookie(SESSION_COOKIE, token, httponly=True, path="/api", **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, path="/", **common)


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/login", response_model=User, responses=responses(401, 422, 429))
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    store: UserStore = Depends(get_store),  # noqa: B008
) -> User:
    """Check the credentials and start a session (cookies ``ndoc_session``,
    HttpOnly, and ``ndoc_csrf``, to be echoed in ``X-CSRF-Token``)."""
    user = store.verify_password(body.username, body.password)
    token, csrf = store.create_session(user)
    _set_cookies(request, response, token, csrf)
    return User(username=user.username, role=user.role, disabled=user.disabled)


@router.post("/logout", status_code=204, response_class=Response, responses=responses(401, 403))
def logout(
    store: UserStore = Depends(get_store),  # noqa: B008
    session: Session = Depends(current_session),  # noqa: B008
) -> Response:
    store.delete_session(session.token_sha256)
    response = Response(status_code=204)
    _clear_cookies(response)
    return response


@router.get("/me", response_model=User, responses=responses(401))
def me(session: Session = Depends(current_session)) -> User:  # noqa: B008
    u = session.user
    return User(username=u.username, role=u.role, disabled=u.disabled)


@router.post(
    "/password", status_code=204, response_class=Response, responses=responses(401, 403, 422, 429)
)
def change_password(
    body: PasswordChange,
    store: UserStore = Depends(get_store),  # noqa: B008
    session: Session = Depends(current_session),  # noqa: B008
) -> Response:
    """Change the own password; other sessions of the user end."""
    store.verify_password(session.user.username, body.current_password)
    store.update_user(
        session.user.username, password=body.new_password, keep_session=session.token_sha256
    )
    return Response(status_code=204)
