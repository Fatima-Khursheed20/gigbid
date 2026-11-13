"""Users, sessions (JWT in an httpOnly cookie or bearer header) and password hashing."""

from __future__ import annotations

import time
import uuid

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from common.settings import get_settings

from .. import db

COOKIE = "gigbid_session"


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], h.encode())
    except ValueError:
        return False


def make_token(user_id: str, hours: int = 72) -> str:
    return jwt.encode({"sub": user_id, "exp": int(time.time()) + hours * 3600, "jti": uuid.uuid4().hex},
                      get_settings().app_secret_key, algorithm="HS256")


def read_token(token: str) -> str | None:
    try:
        return jwt.decode(token, get_settings().app_secret_key, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        return None


async def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE) or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    uid = read_token(token) if token else None
    if not uid:
        raise HTTPException(401, "not signed in")
    user = await db.fetchone("select u.id, u.email, u.name, u.is_reviewer, p.* from users u left join profiles p "
                             "on p.user_id=u.id where u.id=%s", uid)
    if not user:
        raise HTTPException(401, "unknown user")
    return user


CurrentUser = Depends(current_user)


async def create_user(email: str, password: str, name: str, is_reviewer: bool = False) -> str:
    uid = "u-" + uuid.uuid4().hex[:10]
    await db.execute("insert into users(id,email,name,password_hash,is_reviewer) values (%s,%s,%s,%s,%s)",
                     uid, email.lower().strip(), name, hash_pw(password), is_reviewer)
    await db.execute("insert into profiles(user_id, tenant) values (%s,%s)", uid, uid)
    return uid
