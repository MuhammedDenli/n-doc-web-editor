"""User administration (admin role)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..auth import UserRecord, UserStore, get_store, require_admin
from ..errors import responses
from ..models import User, UserCreate, UserUpdate

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
    responses=responses(401, 403, 422),
)


def _user(u: UserRecord) -> User:
    return User(username=u.username, role=u.role, disabled=u.disabled)


@router.get("", response_model=list[User])
def list_users(store: UserStore = Depends(get_store)) -> list[User]:  # noqa: B008
    return [_user(u) for u in store.list_users()]


@router.post("", status_code=201, response_model=User, responses=responses(409, 422))
def create_user(body: UserCreate, store: UserStore = Depends(get_store)) -> User:  # noqa: B008
    return _user(store.create_user(body.username, body.password, body.role))


@router.patch("/{username}", response_model=User, responses=responses(404, 409, 422))
def update_user(
    username: str,
    body: UserUpdate,
    store: UserStore = Depends(get_store),  # noqa: B008
) -> User:
    """Change role, password or disabled. The last active admin cannot be
    demoted or disabled (409 ``last_admin``)."""
    return _user(
        store.update_user(username, role=body.role, password=body.password, disabled=body.disabled)
    )


@router.delete(
    "/{username}", status_code=204, response_class=Response, responses=responses(404, 409)
)
def delete_user(username: str, store: UserStore = Depends(get_store)) -> Response:  # noqa: B008
    store.delete_user(username)
    return Response(status_code=204)
