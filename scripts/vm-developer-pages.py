"""Developers' price lists on script-heavy pages, read in the computer-use VM (docs/STRATEGY.md 5.2 D, 5.4).

    .venv/bin/python scripts/vm-developer-pages.py --site https://qayem.ai

Holds content-engine's shared desktop lock for the whole run (exit 75 from the lock: nothing is done).
Inside it, each page in src/qayem/data/vm_pages.json opens in Qayem's own Brave profile in the VM
(`vm-cu brave qayem <url>`), its text is read from the accessibility tree (no CDP, no login, no
form), Pi/GLM proposes price rows, and the page and rows go to the review queue (/admin/review).
Never used to get past a block, a captcha or a login: such a page is skipped and reported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
ENGINE = Path.home() / "projects" / "content-engine"
PAGES = ROOT / "src" / "qayem" / "data" / "vm_pages.json"
BLOCKED = re.compile(r"captcha|verify you are human|access denied|attention required|sign in|log in|تسجيل الدخول", re.I)
INSTRUCTIONS = """You read the text of an Egyptian developer's project page. Return one row per unit type or unit whose
price the page states: compound or project, unit type, area in m², total price in EGP, down payment and instalment
years when stated. Copy numbers as stated, converted to plain EGP ("مليون" = million). Return no rows when the page
states no price ("call for price")."""


def page_text(tree: str) -> str:
    """The readable names in an accessibility tree dump, without the element plumbing."""
    names = re.findall(r'^\s*- \[\d+\] [\w ]+? "(.*?)"', tree, flags=re.M)
    lines = [n.strip() for n in names if n.strip() and not re.fullmatch(r"[￼\s]*", n)]
    return "\n".join(dict.fromkeys(lines))


def inside(site: str, token: str) -> list[dict]:
    from qayem.ai import run_pi
    from qayem.articles import Site
    from qayem.intake import ROWS
    folder = ROOT / ".artifacts" / "vm-pages"
    folder.mkdir(parents=True, exist_ok=True)
    instructions = folder / "instructions.md"
    instructions.write_text(INSTRUCTIONS, encoding="utf-8")
    api = Site(site, token)
    out = []
    for page in json.loads(PAGES.read_text()):
        subprocess.run(["vm-cu", "brave", "qayem", page["url"]], check=True, capture_output=True, timeout=120)
        time.sleep(page.get("wait", 15))
        tree = subprocess.run(["vm-cu", "tree", "brave"], capture_output=True, text=True, timeout=120).stdout
        text = page_text(tree)
        stamp = time.strftime("%Y-%m-%d")
        (folder / f"{page['developer']}-{stamp}.txt").write_text(text, encoding="utf-8")
        if BLOCKED.search(text[:3000]) or len(text) < 200:
            out.append({"developer": page["developer"], "status": "skipped", "reason": "blocked, login or empty page"})
            continue
        if page.get("kind") == "terms_check":
            terms_note = bool(re.search(r"terms|شروط|privacy|خصوصية|copyright|حقوق", text, re.I))
            out.append({"developer": page["developer"], "status": "terms_checked", "terms_found": terms_note,
                        "chars": len(text)})
            continue
        rows = [r for r in run_pi(text[:20_000], ROWS, instructions)["rows"] if r.get("price")]
        stored = api.post("/api/admin/inbox", {"source": page["url"], "text": text[:15_000], "rows": rows})
        out.append({"developer": page["developer"], "status": "queued", "rows": len(rows), "stored": stored["stored"]})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="https://qayem.ai")
    parser.add_argument("--token-file", default=str(ROOT / ".artifacts/cloudflare/admin-token"))
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    token = Path(args.token_file).read_text().strip()
    if args.inside:
        print(json.dumps(inside(args.site, token), ensure_ascii=False))
        return
    command = [str(ENGINE / ".venv/bin/python"), "-m", "studio.desktop_lock", "run", "--brand", "qayem",
               "--owner", "qayem-developer-pages", "--task", "developer-price-pages", "--wait", "900", "--",
               sys.executable, __file__, "--inside", "--site", args.site, "--token-file", args.token_file]
    result = subprocess.run(command, cwd=ENGINE)
    if result.returncode == 75:
        print("The desktop lock was not taken: no computer use this run.")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
