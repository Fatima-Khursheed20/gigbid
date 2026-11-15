"""Deploy GigBid to Render's free tier through the Render REST API (v1).

Creates (idempotently): free Postgres, free Key Value (Redis), and a Docker web service built from the public
GitHub repo with infra/docker/render.Dockerfile. Secrets go into Render env vars, never into the repo.
Reviewer credentials are generated once into data/processed/reviewer_credentials.json (git-ignored).

    python -m scripts.deploy_render [--status]
"""

from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.render.com/v1"
REPO = "https://github.com/Fatima-Khursheed20/gigbid"
REGION = "oregon"
CREDS = ROOT / "data" / "processed" / "reviewer_credentials.json"


def client() -> httpx.Client:
    key = dotenv_values(ROOT / ".env").get("RENDER_API_KEY")
    if not key:
        sys.exit("RENDER_API_KEY missing in .env")
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=60)


def owner_id(c: httpx.Client) -> str:
    r = c.get("/owners", params={"limit": 20})
    r.raise_for_status()
    return r.json()[0]["owner"]["id"]


def find(c: httpx.Client, path: str, name: str) -> dict | None:
    r = c.get(path, params={"name": name, "limit": 20})
    r.raise_for_status()
    for item in r.json():
        obj = next(iter(v for k, v in item.items() if isinstance(v, dict)), item)
        if obj.get("name") == name:
            return obj
    return None


def wait_available(c: httpx.Client, path: str) -> dict:
    for _ in range(90):
        r = c.get(path)
        r.raise_for_status()
        d = r.json()
        if d.get("status") in ("available", "running", None) and d.get("status") != "creating":
            return d
        time.sleep(10)
    raise TimeoutError(path)


def main() -> None:
    c = client()
    env = dotenv_values(ROOT / ".env")
    if "--status" in sys.argv:
        svc = find(c, "/services", "gigbid")
        print(json.dumps(svc, indent=1)[:2000])
        if svc:
            d = c.get(f"/services/{svc['id']}/deploys", params={"limit": 3}).json()
            print(json.dumps(d, indent=1)[:2000])
        return
    oid = owner_id(c)
    pg = find(c, "/postgres", "gigbid-db")
    if not pg:
        r = c.post("/postgres", json={"name": "gigbid-db", "ownerId": oid, "plan": "free", "region": REGION,
                                      "version": "16", "databaseName": "gigbid", "databaseUser": "gigbid"})
        print("postgres", r.status_code, r.text[:300])
        r.raise_for_status()
        pg = r.json()
    wait_available(c, f"/postgres/{pg['id']}")
    pg_conn = c.get(f"/postgres/{pg['id']}/connection-info").json()
    kv = find(c, "/key-value", "gigbid-redis")
    if not kv:
        r = c.post("/key-value", json={"name": "gigbid-redis", "ownerId": oid, "plan": "free", "region": REGION,
                                       "maxmemoryPolicy": "noeviction"})
        print("key-value", r.status_code, r.text[:300])
        r.raise_for_status()
        kv = r.json()
    wait_available(c, f"/key-value/{kv['id']}")
    kv_conn = c.get(f"/key-value/{kv['id']}/connection-info").json()
    if CREDS.exists():
        creds = json.loads(CREDS.read_text())
    else:
        creds = {"email": "reviewer@gigbid.app", "password": secrets.token_urlsafe(12)}
        CREDS.parent.mkdir(parents=True, exist_ok=True)
        CREDS.write_text(json.dumps(creds, indent=1))
    env_vars = {
        "DATABASE_URL": pg_conn["internalConnectionString"], "REDIS_URL": kv_conn["internalConnectionString"],
        "GROQ_API_KEY": env["GROQ_API_KEY"], "APP_SECRET_KEY": secrets.token_urlsafe(40),
        "MCP_MARKETPLACE_TOKEN": secrets.token_urlsafe(24), "GIGSIM_ADMIN_TOKEN": secrets.token_urlsafe(24),
        "REVIEWER_EMAIL": creds["email"], "REVIEWER_PASSWORD": creds["password"], "MODEL_PROFILE": "open",
        "MARKETPLACE_MODE": "gigsim", "LANGSMITH_TRACING": "true" if env.get("LANGSMITH_API_KEY") else "false",
        **({"LANGSMITH_API_KEY": env["LANGSMITH_API_KEY"]} if env.get("LANGSMITH_API_KEY") else {}),
    }
    svc = find(c, "/services", "gigbid")
    if not svc:
        body = {"type": "web_service", "name": "gigbid", "ownerId": oid, "repo": REPO, "branch": "main", "autoDeploy": "yes",
                "envVars": [{"key": k, "value": v} for k, v in env_vars.items()],
                "serviceDetails": {"runtime": "docker", "plan": "free", "region": REGION, "healthCheckPath": "/api/health",
                                   "envSpecificDetails": {"dockerfilePath": "./infra/docker/render.Dockerfile", "dockerContext": "."}}}
        r = c.post("/services", json=body)
        print("service", r.status_code, r.text[:500])
        r.raise_for_status()
        svc = r.json().get("service", r.json())
    else:
        c.put(f"/services/{svc['id']}/env-vars", json=[{"key": k, "value": v} for k, v in env_vars.items()]).raise_for_status()
        c.post(f"/services/{svc['id']}/deploys", json={"clearCache": "do_not_clear"}).raise_for_status()
    print(json.dumps({"service_id": svc["id"], "url": svc.get("serviceDetails", {}).get("url"),
                      "dashboard": svc.get("dashboardUrl")}, indent=1))


if __name__ == "__main__":
    main()
