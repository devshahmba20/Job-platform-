import os, time, asyncio
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

APP_ID = os.environ.get("ADZUNA_APP_ID")
APP_KEY = os.environ.get("ADZUNA_APP_KEY")
URL = "https://api.adzuna.com/v1/api/jobs/in/search/{}"
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

def clean(j, rel):
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
        "rel": rel,
    }

async def one(client, q, where, page):
    base = {"app_id": APP_ID, "app_key": APP_KEY, "results_per_page": 30,
            "where": where, "distance": 40, "sort_by": "date"}
    if not q:
        modes = [({}, False)]
    else:
        modes = [({"what_phrase": q}, False), ({"what": q}, False), ({"what_or": q}, True)]
    for extra, rel in modes:
        r = await client.get(URL.format(page), params={**base, **extra})
        r.raise_for_status()
        d = r.json()
        if d.get("results"):
            return d.get("count", 0), [clean(j, rel) for j in d["results"]]
    return 0, []

@app.get("/api/jobs")
async def jobs(q: str = "", where: str = "Ahmedabad", page: int = 1):
    if not APP_ID or not APP_KEY:
        raise HTTPException(500, "Adzuna keys missing")
    q = " ".join(q.split())
    places = [p.strip() for p in where.split(",") if p.strip()][:5] or ["India"]
    key = (q.lower(), tuple(p.lower() for p in places), page)
    hit = cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            res = await asyncio.gather(*[one(c, q, p, page) for p in places])
    except Exception:
        raise HTTPException(502, "Adzuna request failed")
    seen, merged = set(), []
    for _, lst in res:
        for j in lst:
            if j["id"] not in seen:
                seen.add(j["id"])
                merged.append(j)
    merged.sort(key=lambda j: (j["rel"], j["d"]))
    out = {"count": sum(n for n, _ in res), "jobs": merged}
    cache[key] = (time.time(), out)
    return out

@app.get("/")
async def home():
    return FileResponse("static/index.html")
    
