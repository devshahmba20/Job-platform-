import os, time
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

APP_ID = os.environ.get("ADZUNA_APP_ID")
APP_KEY = os.environ.get("ADZUNA_APP_KEY")
app = FastAPI()
cache = {}

def days_ago(created):
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 999

def lpa(v):
    return round(v / 100000, 1) if v else None

def clean(j):
    lo, hi = lpa(j.get("salary_min")), lpa(j.get("salary_max"))
    ty = ""
    if j.get("contract_type") == "contract":
        ty = "Contract"
    elif j.get("contract_time") == "full_time":
        ty = "Full-time"
    elif j.get("contract_time") == "part_time":
        ty = "Part-time"
    return {
        "id": str(j.get("id")),
        "t": j.get("title", ""),
        "c": (j.get("company") or {}).get("display_name", ""),
        "a": (j.get("location") or {}).get("display_name", ""),
        "f": (j.get("category") or {}).get("label", ""),
        "s": [lo, hi or lo] if lo else None,
        "pred": j.get("salary_is_predicted") == "1",
        "ty": ty,
        "d": days_ago(j.get("created", "")),
        "ds": j.get("description", ""),
        "url": j.get("redirect_url", ""),
    }

@app.get("/api/jobs")
async def jobs(q: str = "", page: int = 1):
    if not APP_ID or not APP_KEY:
        raise HTTPException(500, "Adzuna keys missing")
    key = (q.lower().strip(), page)
    hit = cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    params = {"app_id": APP_ID, "app_key": APP_KEY, "results_per_page": 30,
              "where": "Ahmedabad", "distance": 25, "sort_by": "date"}
    if q.strip():
        params["what"] = q.strip()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"https://api.adzuna.com/v1/api/jobs/in/search/{page}", params=params)
        r.raise_for_status()
        d = r.json()
    except Exception:
        raise HTTPException(502, "Adzuna request failed")
    out = {"count": d.get("count", 0), "jobs": [clean(j) for j in d.get("results", [])]}
    cache[key] = (time.time(), out)
    return out

@app.get("/")
async def home():
    return FileResponse("static/index.html")
