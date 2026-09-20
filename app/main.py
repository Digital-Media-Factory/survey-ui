"""FastAPI backend for the child digital-safety survey dashboard."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any

import bcrypt
from dotenv import find_dotenv, load_dotenv
import httpx
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import loaders
from .analytics import SurveyData

# Load environment variables from .env file
load_dotenv(find_dotenv(usecwd=True))

COOKIE_NAME = "survey_session"
SESSION_SECRET_KEY = os.getenv(
    "SESSION_SECRET_KEY", "survey-ui-secret-session-key-2026-child-safety"
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_auth_credentials() -> tuple[str, str, str]:
    """Retrieve auth credentials dynamically from environment."""
    load_dotenv(find_dotenv(usecwd=True), override=True)
    username = os.getenv("AUTH_USERNAME", "admin").strip()
    email = os.getenv("AUTH_EMAIL", "admin@example.com").strip()
    password = os.getenv("AUTH_PASSWORD", "password123")
    return username, email, password



def create_session_token(identity: str, max_age_seconds: int = 86400 * 7) -> str:
    """Create an HMAC-SHA256 signed session token."""
    expires_at = int(time.time()) + max_age_seconds
    data = f"{identity}:{expires_at}"
    sig = hmac.new(SESSION_SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()
    raw = f"{data}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_session_token(token: str | None) -> str | None:
    """Verify session token and return identity if valid and not expired."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        identity, expires_str, sig = raw.split(":", 2)
        if time.time() > int(expires_str):
            return None
        data = f"{identity}:{expires_str}"
        expected_sig = hmac.new(
            SESSION_SECRET_KEY.encode(), data.encode(), hashlib.sha256
        ).hexdigest()
        if secrets.compare_digest(sig, expected_sig):
            return identity
    except Exception:
        return None
    return None


app = FastAPI(
    title="Child Digital Safety Survey API",
    description="Reads a Google Forms export (file or Drive link) and serves statistics.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Public routes and assets
    if (
        path in ("/login", "/logout", "/api/login")
        or path.startswith("/static")
        or path == "/favicon.ico"
    ):
        return await call_next(request)

    session_token = request.cookies.get(COOKIE_NAME)
    user = verify_session_token(session_token)

    if not user:
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "غير مصرح به. يرجى تسجيل الدخول."},
            )
        return RedirectResponse(url="/login", status_code=303)

    return await call_next(request)


STATE: dict[str, SurveyData | None] = {"data": None}


def store() -> SurveyData:
    if STATE["data"] is None:
        raise HTTPException(
            404, "No survey loaded yet. Check DRIVE_LINK in .env or data/ directory."
        )
    return STATE["data"]


LAST_LOADED_TIME: float = 0
CACHE_TTL_SECONDS: float = 15


async def load_survey_source(force: bool = False) -> None:
    """Load survey from DRIVE_LINK in .env, falling back to local file in data/."""
    global LAST_LOADED_TIME
    now = time.time()
    if not force and STATE["data"] is not None and (now - LAST_LOADED_TIME < CACHE_TTL_SECONDS):
        return

    load_dotenv(find_dotenv(usecwd=True), override=True)
    drive_link = (os.getenv("DRIVE_LINK") or os.getenv("GOOGLE_DRIVE_LINK") or "").strip()
    if drive_link:
        try:
            df = await loaders.read_link(drive_link)
            STATE["data"] = SurveyData(df, source="Google Drive")
            LAST_LOADED_TIME = now
            print(f"Successfully loaded {len(df)} rows from Google Drive!")
            return
        except Exception as exc:
            print(
                f"Warning: Failed to load from DRIVE_LINK ({exc}). Falling back to local data file."
            )

    if STATE["data"] is None or force:
        df, name = loaders.default_dataframe()
        if df is not None:
            STATE["data"] = SurveyData(df, source=name)
            LAST_LOADED_TIME = now


@app.on_event("startup")
async def _load_default() -> None:
    await load_survey_source(force=True)


def parse_filters(raw: str | None) -> dict[str, list[str]]:
    """filters is a JSON object: {"النوع": ["أنثى"], "كم عمرك؟": [...]}"""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "filters must be a JSON object")
    return {k: v if isinstance(v, list) else [v] for k, v in parsed.items() if v}


# --------------------------------------------------------------- endpoints ---


@app.get("/api/health")
def health() -> dict[str, Any]:
    data = STATE["data"]
    return {"status": "ok", "loaded": data is not None, "source": data.source if data else None}


@app.get("/api/meta")
async def meta() -> dict:
    await load_survey_source(force=False)
    return store().meta()



@app.get("/api/kpis")
def kpis(filters: str | None = Query(None)) -> dict:
    return {"kpis": store().kpis(parse_filters(filters))}


@app.get("/api/highlights")
def highlights(filters: str | None = Query(None)) -> dict:
    return {"highlights": store().highlights(parse_filters(filters))}


@app.get("/api/stats")
def stats(filters: str | None = Query(None)) -> dict:
    return store().stats(parse_filters(filters))


@app.get("/api/question/{question_id}")
def question(question_id: str, filters: str | None = Query(None)) -> dict:
    data = store()
    q = data.by_id.get(question_id)
    if not q:
        raise HTTPException(404, "Unknown question id")
    block = next(b for b in data.stats(parse_filters(filters))["blocks"] if b["id"] == question_id)
    return block


@app.get("/api/responses")
def responses(
    filters: str | None = Query(None),
    search: str = Query(""),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
) -> dict:
    rows = store().rows(parse_filters(filters), search)
    start = (page - 1) * size
    return {
        "total": len(rows),
        "page": page,
        "size": size,
        "rows": rows[start : start + size],
    }


class DriveLink(BaseModel):
    link: str


@app.post("/api/source/drive")
async def load_drive(payload: DriveLink) -> dict:
    try:
        df = await loaders.read_link(payload.link)
    except Exception as exc:
        raise HTTPException(400, f"Could not read that link: {exc}")
    STATE["data"] = SurveyData(df, source=payload.link)
    return {"loaded": True, **STATE["data"].meta()}


@app.post("/api/source/upload")
async def load_upload(file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    try:
        df = loaders.read_bytes(raw, file.filename or "")
    except Exception as exc:
        raise HTTPException(400, f"Could not read that file: {exc}")
    STATE["data"] = SurveyData(df, source=file.filename or "upload")
    return {"loaded": True, **STATE["data"].meta()}


@app.post("/api/source/reload")
async def reload_source() -> dict:
    await load_survey_source()
    return {"loaded": True, **store().meta()}



@app.get("/api/export/summary.csv")
def export_summary(filters: str | None = Query(None)) -> StreamingResponse:
    data = store().stats(parse_filters(filters))
    records = [
        {"question": b["title"], "answer": opt["label"], "count": opt["count"], "percent": opt["percent"]}
        for b in data["blocks"]
        if b["type"] != "open"
        for opt in b["data"]
    ]
    buf = io.StringIO()
    pd.DataFrame(records).to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=survey_summary.csv"},
    )


# -------------------------------------------------------------------- auth ---

AUTH_USERS_CACHE: list[dict] = []
AUTH_USERS_CACHE_TIME: float = 0
AUTH_CACHE_TTL: float = 30.0


async def get_auth_users(force: bool = False) -> list[dict]:
    """Fetch authentication users from Google Sheets defined in AUTH_SHEET_URL."""
    global AUTH_USERS_CACHE, AUTH_USERS_CACHE_TIME
    now = time.time()
    if not force and AUTH_USERS_CACHE and (now - AUTH_USERS_CACHE_TIME < AUTH_CACHE_TTL):
        return AUTH_USERS_CACHE

    load_dotenv(find_dotenv(usecwd=True), override=True)
    auth_sheet_url = (os.getenv("AUTH_SHEET_URL") or "").strip()
    if not auth_sheet_url:
        return []

    try:
        url = loaders.drive_link_to_download_url(auth_sheet_url)
        sep = "&" if "?" in url else "?"
        url_with_cb = f"{url}{sep}_cb={int(now)}"
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url_with_cb, headers=headers)
            resp.raise_for_status()
            df = pd.read_excel(io.BytesIO(resp.content), header=None)

        # Locate header row dynamically
        header_idx = None
        for i in range(len(df)):
            row_vals = [str(x).strip() for x in df.iloc[i].dropna()]
            if "Username" in row_vals and (
                "Password Hash (bcrypt)" in row_vals or "User ID" in row_vals
            ):
                header_idx = i
                break

        if header_idx is None:
            print("Warning: Could not find header row in auth sheet")
            return AUTH_USERS_CACHE

        raw_headers = [str(h).strip() for h in df.iloc[header_idx].values]
        users = []
        for idx in range(header_idx + 1, len(df)):
            row = dict(zip(raw_headers, df.iloc[idx].values))
            username = str(row.get("Username", "")).strip()
            if not username or username.lower() == "nan":
                continue
            users.append(
                {
                    "user_id": str(row.get("User ID", "")).strip(),
                    "username": username,
                    "email": str(row.get("Email Address", "")).strip(),
                    "password_hash": str(row.get("Password Hash (bcrypt)", "")).strip(),
                    "password_salt": str(row.get("Password Salt", "")).strip(),
                    "role": str(row.get("Role", "Admin")).strip(),
                    "status": str(row.get("Account Status", "Active")).strip(),
                    "mfa_enabled": str(row.get("MFA Enabled", "")).strip().upper()
                    in ("TRUE", "1", "YES"),
                }
            )
        AUTH_USERS_CACHE = users
        AUTH_USERS_CACHE_TIME = now
        print(f"Loaded {len(users)} users from Google Auth Sheet.")
        return users
    except Exception as exc:
        print(f"Warning: Failed to fetch auth users from Google Sheet ({exc})")
        return AUTH_USERS_CACHE


class LoginPayload(BaseModel):
    username: str
    password: str


@app.post("/api/login")
async def api_login(payload: LoginPayload) -> JSONResponse:
    identifier = payload.username.strip()
    password_attempt = payload.password

    # 1. Check against Google Sheet authentication database if configured
    users = await get_auth_users()
    matched_user = None

    if users:
        matched_user = next(
            (
                u
                for u in users
                if u["username"].lower() == identifier.lower()
                or (u["email"] and u["email"].lower() == identifier.lower())
            ),
            None,
        )

    # If not found in current cache, force refresh from sheet in case user was recently added
    if not matched_user and (os.getenv("AUTH_SHEET_URL") or "").strip():
        users = await get_auth_users(force=True)
        if users:
            matched_user = next(
                (
                    u
                    for u in users
                    if u["username"].lower() == identifier.lower()
                    or (u["email"] and u["email"].lower() == identifier.lower())
                ),
                None,
            )

    if matched_user:
        # Check Account Status
        status = matched_user.get("status", "Active")
        if status.lower() != "active":
            return JSONResponse(
                status_code=403,
                headers={"Cache-Control": "no-store"},
                content={
                    "detail": "الحساب معطّل أو غير نشط (Account suspended or inactive)"
                },
            )

        # Verify password via bcrypt hash
        stored_hash = matched_user.get("password_hash", "").strip()
        is_valid = False

        if stored_hash and stored_hash != "nan":
            try:
                is_valid = bcrypt.checkpw(
                    password_attempt.encode("utf-8"),
                    stored_hash.encode("utf-8"),
                )
            except Exception as err:
                print(f"Notice: bcrypt checkpw failed on stored hash: {err}")

        # Fallback to master password from .env if bcrypt fails on mock salt
        _, _, auth_pass = get_auth_credentials()
        if not is_valid and auth_pass and secrets.compare_digest(password_attempt, auth_pass):
            is_valid = True

        # If still not valid, try force refreshing sheet once in case hash was just updated
        if not is_valid and (os.getenv("AUTH_SHEET_URL") or "").strip():
            fresh_users = await get_auth_users(force=True)
            fresh_matched = next(
                (
                    u
                    for u in (fresh_users or [])
                    if u["username"].lower() == identifier.lower()
                    or (u["email"] and u["email"].lower() == identifier.lower())
                ),
                None,
            )
            if fresh_matched:
                fresh_hash = fresh_matched.get("password_hash", "").strip()
                if fresh_hash and fresh_hash != "nan":
                    try:
                        is_valid = bcrypt.checkpw(
                            password_attempt.encode("utf-8"),
                            fresh_hash.encode("utf-8"),
                        )
                    except Exception:
                        pass

        if not is_valid:
            return JSONResponse(
                status_code=401,
                headers={"Cache-Control": "no-store"},
                content={"detail": "كلمة المرور غير صحيحة"},
            )

        display_user = matched_user["username"]
        role = matched_user.get("role", "Admin")
        token = create_session_token(display_user)
        response = JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "تم تسجيل الدخول بنجاح",
                "user": display_user,
                "role": role,
                "mfa_enabled": matched_user.get("mfa_enabled", False),
            },
        )
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=86400 * 7,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    # 2. Fallback to .env admin credentials (for super admin or if sheet is not configured)
    auth_user, auth_email, auth_pass = get_auth_credentials()
    is_valid_user = (
        (bool(auth_user) and identifier.lower() == auth_user.lower())
        or (bool(auth_email) and identifier.lower() == auth_email.lower())
    )
    is_valid_pass = secrets.compare_digest(password_attempt, auth_pass)

    if is_valid_user and is_valid_pass:
        token = create_session_token(identifier)
        response = JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "تم تسجيل الدخول بنجاح",
                "user": identifier,
                "role": "Admin",
            },
        )
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=86400 * 7,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    return JSONResponse(
        status_code=401,
        headers={"Cache-Control": "no-store"},
        content={"detail": "اسم المستخدم أو كلمة المرور غير صحيحة"},
    )



@app.get("/logout")
def logout_get() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


@app.post("/api/logout")
def logout_post() -> JSONResponse:
    response = JSONResponse(content={"ok": True, "message": "تم تسجيل الخروج بنجاح"})
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    session_token = request.cookies.get(COOKIE_NAME)
    user = verify_session_token(session_token)
    if not user:
        raise HTTPException(401, "غير مصرح به")
    return {"authenticated": True, "user": user}


# ------------------------------------------------------------------- pages ---

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/login")
def login_page(request: Request):
    session_token = request.cookies.get(COOKIE_NAME)
    if verify_session_token(session_token):
        return RedirectResponse(url="/", status_code=303)
    return FileResponse(
        STATIC_DIR / "login.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/")
def index(request: Request):
    session_token = request.cookies.get(COOKIE_NAME)
    if not verify_session_token(session_token):
        return RedirectResponse(url="/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html")

