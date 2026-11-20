"""FastAPI backend. Every /api route except sign-in requires a signed-in, active account,
checked on each request, so the rules cannot be bypassed by calling the backend directly."""
from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Callable, Iterable

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.dashboard.accounts import STAFF_ROLE, AccountStore
from src.dashboard.data import AuditView, NoSource, ScopeError

COOKIE = "skillalign_session"
APP_NAME = "skillalignrag-dashboard"  # Reported by /api/health, so a second start can recognise a running copy.
SESSION_SECONDS = 8 * 3600
FAILED_SIGN_IN_DELAY = 0.5


class SignIn(BaseModel):
    username: str
    password: str


class Sessions:
    """Server-side sessions held in memory; a restart signs everyone out."""

    def __init__(self, seconds: int = SESSION_SECONDS):
        self.seconds, self.tokens = seconds, {}

    def start(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        self.tokens[token] = (username, time.time() + self.seconds)
        return token

    def username(self, token: str | None) -> str | None:
        username, expires = self.tokens.get(token or "", (None, 0))
        if username and expires > time.time():
            return username
        self.tokens.pop(token or "", None)
        return None

    def end(self, token: str | None) -> None:
        self.tokens.pop(token or "", None)


def create_app(view: AuditView, accounts: AccountStore, static_dir: Path | None = None,
               extensions: Iterable[Callable] = (), cookie_name: str = COOKIE) -> FastAPI:
    """`extensions` are functions called as extension(app, current_user) to add more /api routes
    (for example the FYP's review features) before the catch-all route and the front end."""
    app = FastAPI(title="SkillAlignRAG dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    # Compressed responses travel faster through the VS Code tunnel; small ones are not worth it.
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    sessions = Sessions()

    def current_user(request: Request) -> dict:
        username = sessions.username(request.cookies.get(cookie_name))
        # Re-read the account each time, so disabling it or changing its roles takes effect at once.
        user = accounts.get(username) if username else None
        if not user:
            raise HTTPException(401, "Please sign in.")
        return {**user, "can_upload": STAFF_ROLE in user["roles"]}

    @app.exception_handler(ScopeError)
    async def out_of_scope(request: Request, exc: ScopeError):
        return JSONResponse({"detail": str(exc), "out_of_scope": True}, status_code=400)

    @app.exception_handler(NoSource)
    async def no_source(request: Request, exc: NoSource):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.get("/api/health")
    def health():
        # Needs no sign-in and reveals nothing: it only identifies the program on this port.
        return {"app": APP_NAME}

    @app.post("/api/sign-in")
    def sign_in(body: SignIn, response: Response):
        user = accounts.authenticate(body.username.strip().lower(), body.password)
        if not user:
            time.sleep(FAILED_SIGN_IN_DELAY)
            raise HTTPException(401, "Wrong username or password, or the account is disabled.")
        response.set_cookie(cookie_name, sessions.start(user["username"]), httponly=True, samesite="strict",
                            max_age=SESSION_SECONDS, path="/")
        return {**user, "can_upload": STAFF_ROLE in user["roles"]}

    @app.post("/api/sign-out")
    def sign_out(request: Request, response: Response):
        sessions.end(request.cookies.get(cookie_name))
        response.delete_cookie(cookie_name, path="/")
        return {"signed_out": True}

    @app.get("/api/me")
    def me(user: dict = Depends(current_user)):
        return user

    @app.get("/api/run")
    def run(user: dict = Depends(current_user)):
        return view.run_info()

    @app.get("/api/courses")
    def courses(user: dict = Depends(current_user)):
        return view.courses()

    @app.get("/api/skills")
    def skills(user: dict = Depends(current_user)):
        return view.skill_list()

    @app.get("/api/overview")
    def overview(course: str | None = None, skill: str | None = None, user: dict = Depends(current_user)):
        return view.rows(course=course or None, skill=skill or None)

    @app.get("/api/cells/{course}/{skill}/{level}")
    def cell(course: str, skill: str, level: str, user: dict = Depends(current_user)):
        return view.cell(course, skill, level)

    @app.get("/api/cells/{course}/{skill}/{level}/source")
    def source(course: str, skill: str, level: str, item: str = "citation", user: dict = Depends(current_user)):
        return view.source(course, skill, level, item)

    @app.get("/api/cells/{course}/{skill}/{level}/document")
    def document(course: str, skill: str, level: str, item: str = "citation", user: dict = Depends(current_user)):
        return JSONResponse(view.document(course, skill, level, item), headers={"Cache-Control": "no-store"})

    for extension in extensions:
        extension(app, current_user)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unknown(path: str, user: dict = Depends(current_user)):
        raise HTTPException(404, "Not found.")

    static_dir = Path(static_dir) if static_dir else None
    if static_dir and (static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="front-end")
    else:
        @app.get("/", response_class=HTMLResponse)
        def not_built():
            return "<p>The dashboard front end is not built. Run <code>npm ci && npm run build</code> in <code>dashboard/</code>.</p>"
    return app
