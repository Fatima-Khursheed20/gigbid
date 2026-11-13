"""Sign-in, onboarding profile, connected accounts and saved searches."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse

from common.settings import ROOT

from .. import db
from ..auth import token_store, upwork_oauth
from ..auth.security import COOKIE, CurrentUser, check_pw, create_user, make_token
from ..schemas.models import AuthOut, ConnectIn, LoginIn, Me, Ok, ProfileIn, RegisterIn, SavedSearch, SearchIn

router = APIRouter(prefix="/api", tags=["auth"])
TENANTS = ROOT / "data" / "tenants"


async def me_of(uid: str) -> Me:
    u = await db.fetchone("select u.id, u.email, u.name, u.is_reviewer, p.* from users u join profiles p on p.user_id=u.id "
                          "where u.id=%s", uid)
    return Me(**{**u, "categories": u.get("categories") or [], "connected": await token_store.connected(uid)})


def _set_cookie(resp: Response, token: str, request: Request) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=request.url.scheme == "https", max_age=72 * 3600)


@router.post("/auth/register", response_model=AuthOut, operation_id="register")
async def register(body: RegisterIn, request: Request, response: Response) -> AuthOut:
    if await db.fetchone("select 1 as x from users where email=%s", body.email.lower()):
        raise HTTPException(409, "email already registered")
    uid = await create_user(body.email, body.password, body.name)
    token = make_token(uid)
    _set_cookie(response, token, request)
    return AuthOut(token=token, user=await me_of(uid))


@router.post("/auth/login", response_model=AuthOut, operation_id="login")
async def login(body: LoginIn, request: Request, response: Response) -> AuthOut:
    u = await db.fetchone("select id, password_hash from users where email=%s", body.email.lower())
    if not u or not check_pw(body.password, u["password_hash"]):
        raise HTTPException(401, "wrong email or password")
    token = make_token(u["id"])
    _set_cookie(response, token, request)
    return AuthOut(token=token, user=await me_of(u["id"]))


@router.post("/auth/logout", response_model=Ok, operation_id="logout")
async def logout(response: Response) -> Ok:
    response.delete_cookie(COOKIE)
    return Ok()


@router.get("/auth/me", response_model=Me, operation_id="me")
async def me(user=CurrentUser) -> Me:
    return await me_of(user["id"])


@router.put("/profile", response_model=Me, operation_id="updateProfile")
async def update_profile(body: ProfileIn, user=CurrentUser) -> Me:
    fields = body.model_dump(exclude_none=True)
    if "persona" in fields:
        p = fields["persona"]
        fields["tenant"] = user["id"] if p == "own" else p  # a persona is a preloaded, read-only tenant
        if p != "own":
            fields.update({"ai_ml": {"hourly_rate": 45, "floor_rate": 30, "min_project": 300, "categories": ["ai_ml"]},
                           "fullstack": {"hourly_rate": 35, "floor_rate": 22, "min_project": 250, "categories": ["web"]},
                           "data_analyst": {"hourly_rate": 30, "floor_rate": 18, "min_project": 150, "categories": ["data"]},
                           }[p] | {k: v for k, v in fields.items() if k in ("hourly_rate", "floor_rate", "min_project")})
    if "categories" in fields:
        fields["categories"] = json.dumps(fields["categories"])
    if fields:
        sets = ", ".join(f"{k}=%s" for k in fields)
        await db.execute(f"update profiles set {sets} where user_id=%s", *fields.values(), user["id"])  # noqa: S608 - keys are whitelisted by the schema
    return await me_of(user["id"])


@router.post("/accounts/connect", response_model=Me, operation_id="connectAccount")
async def connect(body: ConnectIn, user=CurrentUser) -> Me:
    if not body.token.startswith("gs-"):
        raise HTTPException(422, "GigSim tokens start with 'gs-'")
    await token_store.put(user["id"], "gigsim", {"token": body.token})
    return await me_of(user["id"])


@router.delete("/accounts/{provider}", response_model=Me, operation_id="disconnectAccount")
async def disconnect(provider: str, user=CurrentUser) -> Me:
    await token_store.delete(user["id"], provider)
    return await me_of(user["id"])


@router.get("/auth/upwork/start", operation_id="upworkStart")
async def upwork_start(user=CurrentUser) -> dict:
    try:
        url = await upwork_oauth.start(user["id"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Could not reach the Upwork MCP server: {type(e).__name__}") from e
    return {"authorization_url": url}


@router.get("/auth/upwork/callback", include_in_schema=False)
async def upwork_callback(code: str, state: str | None = None, user=CurrentUser):
    upwork_oauth.finish(user["id"], code, state)
    return RedirectResponse("/settings?connected=upwork")


@router.post("/portfolio/upload", response_model=Ok, operation_id="uploadPortfolio")
async def upload(files: list[UploadFile] = File(...), user=CurrentUser) -> Ok:  # noqa: B008
    """Add work to your own portfolio; the Portfolio MCP server re-indexes incrementally on the next query."""
    root = TENANTS / user["id"]
    n = 0
    for f in files:
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(f.filename or "file").name)[:80]
        data = await f.read()
        if len(data) > 2_000_000:
            raise HTTPException(413, f"{name} is larger than 2 MB")
        sub = ("cv.pdf" if name.lower().endswith(".pdf") else
               "proposals.jsonl" if name.endswith(".jsonl") else
               f"case_studies/{name if name.endswith('.md') else name + '.md'}")
        path = root / sub
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        await db.execute("insert into portfolio_files(user_id,tenant,path,content) values (%s,%s,%s,%s) on conflict "
                         "(tenant,path) do update set content=excluded.content, uploaded_at=now()", user["id"], user["id"], sub, data)
        n += 1
    await db.execute("update profiles set tenant=%s, persona='own' where user_id=%s", user["id"], user["id"])
    return Ok(detail=f"{n} file(s) added; re-indexed on next search")


async def restore_uploads() -> None:
    """Uploaded portfolios live in Postgres; materialise them on boot (container disks are ephemeral)."""
    for r in await db.fetch("select tenant, path, content from portfolio_files"):
        p = TENANTS / r["tenant"] / r["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(bytes(r["content"]))


@router.get("/searches", response_model=list[SavedSearch], operation_id="listSearches")
async def list_searches(user=CurrentUser) -> list[SavedSearch]:
    rows = await db.fetch("select * from saved_searches where user_id=%s order by id", user["id"])
    return [SavedSearch(**{**r, "last_run_at": str(r["last_run_at"]) if r["last_run_at"] else None}) for r in rows]


@router.post("/searches", response_model=SavedSearch, operation_id="createSearch")
async def create_search(body: SearchIn, user=CurrentUser) -> SavedSearch:
    r = await db.fetchone("insert into saved_searches(user_id,name,query,category,pool,interval_minutes) values "
                          "(%s,%s,%s,%s,%s,%s) returning *", user["id"], body.name, body.query, body.category, body.pool,
                          body.interval_minutes)
    return SavedSearch(**{**r, "last_run_at": None})


@router.delete("/searches/{search_id}", response_model=Ok, operation_id="deleteSearch")
async def delete_search(search_id: int, user=CurrentUser) -> Ok:
    await db.execute("delete from saved_searches where id=%s and user_id=%s", search_id, user["id"])
    return Ok()
