"""Sprint 13A.5 — FastAPI default soak driver.

Drives a full realistic novel workflow against a LIVE ``weaver serve`` FastAPI
cockpit over HTTP (127.0.0.1). No Flask. Uses the ``fake`` provider (repo rule:
no live LLM in CI/soak). Prints a step log and a final JSON summary; exits
non-zero on the first hard failure.

Reusable for the Sprint 13B decommission re-validation cycle.

Usage: python scripts/soak_13a5.py <base_url> <books_dir>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

PROVIDER = "fake"
TERMINAL = ("done", "failed", "cancelled")


def main(base: str, books_dir: str) -> int:
    root = Path(books_dir)
    epub = root / "aozora_sample.epub"
    txt = root / "volume_two.txt"
    html = root / "volume_three.html"
    log: list[str] = []
    summary: dict[str, object] = {}

    c = httpx.Client(base_url=base, timeout=60.0)

    def step(name: str, ok: bool, detail: object = "") -> None:
        mark = "OK " if ok else "FAIL"
        line = f"[{mark}] {name} :: {detail}"
        log.append(line)
        print(line, flush=True)
        if not ok:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            sys.exit(1)

    def poll(url: str) -> dict:
        for _ in range(120):
            r = c.get(url)
            if r.status_code != 200:
                return {"_http": r.status_code, "_body": r.text}
            data = r.json()
            if data.get("status") in TERMINAL:
                return data
            time.sleep(0.25)
        return {"status": "TIMEOUT"}

    # 1. liveness
    h = c.get("/health")
    step("GET /health", h.status_code == 200, h.json())
    v = c.get("/version")
    step("GET /version", v.status_code == 200, v.json())

    # 2. create project from EPUB (real public-domain Aozora source)
    with epub.open("rb") as fh:
        r = c.post(
            "/projects/create",
            files={"file": ("aozora_sample.epub", fh, "application/epub+zip")},
            data={"provider": PROVIDER},
        )
    step("POST /projects/create (epub)", r.status_code in (200, 201), r.text[:200])
    proj = r.json()["project_name"]
    summary["project"] = proj
    summary["create"] = r.json()

    # 3. list projects
    r = c.get("/projects")
    has_proj = r.status_code == 200 and any(p["name"] == proj for p in r.json()["projects"])
    step("GET /projects", has_proj, len(r.json()["projects"]))

    # 4. import TXT as volume 2
    with txt.open("rb") as fh:
        r = c.post(f"/projects/{proj}/import", files={"file": ("volume_two.txt", fh, "text/plain")})
    step("POST import (txt)", r.status_code in (200, 201), r.text[:160])

    # 5. import HTML as volume 3
    with html.open("rb") as fh:
        r = c.post(
            f"/projects/{proj}/import",
            files={"file": ("volume_three.html", fh, "text/html")},
        )
    step("POST import (html)", r.status_code in (200, 201), r.text[:160])

    # 6. tree — expect 3 volumes
    r = c.get(f"/projects/{proj}/tree")
    vols = r.json()["volumes"]
    step(
        "GET /tree (3 volumes)",
        r.status_code == 200 and len(vols) == 3,
        [(x["id"], x["chapter_count"]) for x in vols],
    )
    summary["volumes"] = [
        (x["id"], x["source_format"], x["chapter_count"], x["segment_count"]) for x in vols
    ]
    cid = vols[0]["chapters"][0]["id"]

    # 7. workspace read
    r = c.get(f"/projects/{proj}/chapters/{cid}/workspace")
    ws = r.json()
    step("GET workspace", r.status_code == 200 and ws["segment_count"] > 0, ws["segment_count"])
    sid = ws["segments"][0]["id"]

    # 8. manual save (status -> manual)
    r = c.patch(
        f"/projects/{proj}/chapters/{cid}/segments/{sid}/translation",
        json={"translated_text": "MANUAL SOAK EDIT"},
    )
    step(
        "PATCH segment (manual save)",
        r.status_code == 200 and r.json()["status"] == "manual",
        r.json().get("status"),
    )

    # 9. history
    r = c.get(f"/projects/{proj}/chapters/{cid}/segments/{sid}/translations")
    step("GET segment history", r.status_code == 200 and len(r.json()) >= 1, len(r.json()))

    # 10. translate chapter (skip_existing -> manual segment protected)
    r = c.post(f"/projects/{proj}/chapters/{cid}/translate", json={"provider": PROVIDER})
    step("POST translate chapter (202)", r.status_code == 202, r.json())
    res = poll(f"/projects/{proj}/jobs/{r.json()['job_id']}")
    step("translate job terminal", res.get("status") == "done", res.get("result") or res)
    summary["translate"] = res.get("result")

    # 11. retranslate force_selected (overwrites incl. manual)
    r = c.post(
        f"/projects/{proj}/chapters/{cid}/retranslate",
        json={"mode": "force_selected", "provider": PROVIDER},
    )
    step("POST retranslate force (202)", r.status_code == 202, r.json())
    res = poll(f"/projects/{proj}/jobs/{r.json()['job_id']}")
    step("retranslate job terminal", res.get("status") == "done", res.get("result") or res)

    # 12. glossary CRUD + candidate review
    r = c.post(
        f"/projects/{proj}/glossary",
        json={"source": "魔王", "target": "Demon Lord", "category": "title"},
    )
    step("POST glossary term", r.status_code in (200, 201), r.text[:160])
    r = c.get(f"/projects/{proj}/glossary")
    body = r.json()
    n_terms = len(body.get("terms", body)) if isinstance(body, dict) else len(body)
    step("GET glossary list", r.status_code == 200, n_terms)
    r = c.patch(f"/projects/{proj}/glossary/魔王", json={"target": "Maou"})
    step("PATCH glossary term", r.status_code == 200, r.json())
    r = c.get(f"/projects/{proj}/glossary/candidates")
    step("GET glossary candidates", r.status_code == 200, r.json().get("counts"))

    # 13. character DB
    r = c.post(
        f"/projects/{proj}/characters",
        json={"jp_name": "エリナ", "en_name": "Elina", "role": "protagonist"},
    )
    step("POST character", r.status_code in (200, 201), r.text[:160])
    r = c.get(f"/projects/{proj}/characters")
    body = r.json()
    n_chars = len(body.get("characters", [])) if isinstance(body, dict) else len(body)
    step("GET characters", r.status_code == 200, n_chars)

    # 14. translation memory (populated by the fake translate above)
    r = c.get(f"/projects/{proj}/memory")
    step("GET memory", r.status_code == 200, r.json().get("total_entries"))
    summary["memory"] = r.json()

    # 15. config read + write (project scope)
    r = c.get(f"/config?project={proj}")
    step(
        "GET /config?project",
        r.status_code == 200,
        {"provider_type": r.json().get("provider_type")},
    )
    r = c.patch(
        "/config",
        json={
            "scope": "project",
            "project": proj,
            "provider_type": PROVIDER,
            "model": "fake-model",
        },
    )
    step("PATCH /config (project)", r.status_code == 200, r.json().get("model"))

    # 16. batch translate whole novel
    r = c.post(
        f"/projects/{proj}/batch/novel", json={"mode": "skip_existing", "provider": PROVIDER}
    )
    step("POST batch/novel (202)", r.status_code == 202, r.json())
    res = poll(f"/projects/{proj}/batch/jobs/{r.json()['job_id']}")
    result = res.get("result") or {}
    step("batch job terminal", res.get("status") == "done" and result.get("failed", 1) == 0, result)
    summary["batch"] = result

    # 17-19. export EPUB / TXT / HTML (whole novel) + on-disk verification
    artifacts: dict[str, object] = {}
    for target in ("epub", "txt", "html"):
        r = c.post(f"/projects/{proj}/export/novel", json={"target": target})
        step(f"POST export/novel ({target}) 202", r.status_code == 202, r.json())
        res = poll(f"/projects/{proj}/export/jobs/{r.json()['job_id']}")
        result = res.get("result") or {}
        paths = [a["output_path"] for a in result.get("artifacts", [])]
        exist = [p for p in paths if Path(p).exists()]
        ok = res.get("status") == "done" and len(paths) > 0 and len(exist) == len(paths)
        step(f"export {target} artifacts on disk", ok, {"paths": len(paths), "exist": len(exist)})
        artifacts[target] = {"count": len(paths), "exist": len(exist), "sample": paths[:1]}
    summary["export"] = artifacts

    print("\n=== SOAK SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("\nALL STEPS PASSED — Flask fallback NOT used.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
