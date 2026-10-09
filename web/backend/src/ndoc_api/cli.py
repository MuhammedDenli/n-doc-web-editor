"""``ndoc-api``: serve the API, create users, export the OpenAPI contract."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from .errors import ApiError
from .settings import Settings

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"


def openapi_json() -> str:
    """The contract as committed in ``web/contracts/openapi.json``."""
    from .app import create_app

    spec = create_app(_contract_settings()).openapi()
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def _contract_settings() -> Settings:
    import tempfile

    from ndoc_core.repo import find_repo_root

    return Settings(
        repo_root=find_repo_root(Path(__file__).resolve().parent),
        data_dir=Path(tempfile.mkdtemp(prefix="ndoc-api-contract-")),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ndoc-api")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the API with uvicorn")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    create = sub.add_parser("create-user", help="add a user (password read from stdin/tty)")
    create.add_argument("username")
    create.add_argument("--role", choices=["admin", "editor"], default="editor")

    export = sub.add_parser("export-openapi", help="write web/contracts/openapi.json")
    export.add_argument("--check", action="store_true", help="fail if the file differs")

    args = parser.parse_args(argv)
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "ndoc_api.app:create_app_from_env",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    elif args.command == "create-user":
        from .auth import UserStore

        settings = Settings.from_env()
        if sys.stdin.isatty():
            password = getpass.getpass("password: ")
            if getpass.getpass("repeat: ") != password:
                sys.exit("passwords differ")
        else:
            password = sys.stdin.readline().rstrip("\n")
        try:
            UserStore(settings.users_db).create_user(args.username, password, args.role)
        except ApiError as exc:
            sys.exit(f"ndoc-api: {exc.code}: {exc.message}")
        print(f"created {args.role} '{args.username}' in {settings.users_db}")
    elif args.command == "export-openapi":
        text = openapi_json()
        if args.check:
            current = CONTRACT.read_text(encoding="utf-8") if CONTRACT.exists() else ""
            if current != text:
                sys.exit(f"{CONTRACT} is out of date; run ndoc-api export-openapi")
            return
        CONTRACT.write_text(text, encoding="utf-8")
        print(f"wrote {CONTRACT}")
