"""FastAPI application: a thin HTTP adapter over ``ndoc_core``."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

from ndoc_core import Repo

from . import errors
from .auth import UserStore
from .builds import BuildManager
from .models import Health
from .routes import auth, build, data, project, users
from .settings import Settings

TITLE = "n-doc web API"
VERSION = "0.1.0"


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title=TITLE,
        version=VERSION,
        description=(
            "REST adapter of the n-doc core. Errors are `ErrorBody` objects "
            "(`code`, `message`, `details`). Every request except login and "
            "health needs the `ndoc_session` cookie; state-changing requests "
            "also need the `X-CSRF-Token` header (value of the `ndoc_csrf` cookie)."
        ),
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.state.repo = Repo(root=settings.repo_root, host_root=settings.host_root)
    app.state.users = UserStore(settings.users_db, session_hours=settings.session_hours)
    app.state.builds = BuildManager(app.state.repo)
    if settings.admin_user and settings.admin_password and not app.state.users.has_users():
        app.state.users.create_user(settings.admin_user, settings.admin_password, "admin")

    errors.install(app)

    @app.get("/api/health", response_model=Health, tags=["meta"])
    def health() -> Health:
        return Health()

    for module in (auth, users, project, data, build):
        app.include_router(module.router)
    return app


def create_app_from_env() -> FastAPI:
    """uvicorn factory (``ndoc-api serve``)."""
    return create_app()
