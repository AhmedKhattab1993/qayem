"""The weekly content brief: three Arabic data stories with chart cards, straight from the catalogue.

Egyptian property feeds are broker pitches; Qayem's edge is numbers nobody else publishes. Each
week `qayem content-brief` writes three ready-to-post stories (a hook, a short body, a tracked
link back to the page that proves it) and a 1080×1350 card for each, as SVG and optionally PNG.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from html import escape
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import quote, urlencode

from .seo import LEVEL_AR, SITE, name_ar, place_ar, ppm_ar

W, H = 1080, 1350
COLORS = {"night": "#0c1512", "paper": "#efe7d6", "muted": "#a9a294", "brass": "#e3bb66", "nile": "#3fb3a3",
          "clay": "#d9754f", "line": "#24342f"}
FONT = "'IBM Plex Sans Arabic','Geeza Pro','Noto Naskh Arabic',Tahoma,sans-serif"
HASHTAGS = ["#عقارات_مصر", "#ريسيل", "#قيّم", "#شقق_للبيع", "#التجمع_الخامس", "#الساحل_الشمالي"]


@dataclass
class Story:
    slug: str
    title: str
    hook: str
    body: list[str]
    path: str
    bars: list[tuple[str, float, str, str]]  # label, value, shown value, colour
    chart_title: str
    hashtags: list[str] = field(default_factory=list)


def tracked(path: str, campaign: str) -> str:
    params = urlencode({"utm_source": "social", "utm_medium": "post", "utm_campaign": campaign})
    return f"{SITE}{path}{'&' if '?' in path else '?'}{params}"


def _pct(value: float) -> str:
    return f"{abs(round(value * 100))}%"


def wrap(text: str, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + ([line] if line else [])


def market_story(overview: dict) -> Story:
    levels = overview["opportunities"]
    rated = sum(n for level, n in levels.items() if level != "unrated")
    good = levels.get("strong", 0) + levels.get("good", 0)
    not_cheaper = rated - good
    share = not_cheaper / rated if rated else 0
    order = [("strong", COLORS["nile"]), ("good", COLORS["nile"]), ("in_line", COLORS["muted"]),
             ("mixed", COLORS["muted"]), ("pricier", COLORS["clay"])]
    bars = [(LEVEL_AR[level], levels.get(level, 0), f"{levels.get(level, 0):,}", colour) for level, colour in order
            if levels.get(level)]
    return Story(
        "market", "كم وحدة ريسيل لقطة فعلًا؟",
        f"{_pct(share)} من وحدات الريسيل ليست أرخص من البدائل المتاحة اليوم. إزاي تلاقي الـ{_pct(1 - share)} اللقطة؟",
        [f"قارنّا {rated:,} وحدة ريسيل معروضة الآن بسعر المطور اليوم لوحدة مماثلة وبالوحدات المماثلة في نفس الكمبوند، "
         "كاش وبقيمة الأقساط اليوم.",
         f"النتيجة: {good:,} وحدة فقط أرخص بوضوح (فرصة قوية أو جيدة)، والباقي في المتوسط أو أغلى.",
         "قبل ما تدفع عربون: قارن الوحدة مجانًا وشوف ترتيبها بين المماثل."],
        "/units?level=strong", bars, "الوحدات المُقارنة حسب التقييم", HASHTAGS[:4])


def compound_story(compounds: dict, week: int) -> Story | None:
    candidates = [c for c in compounds.values() if c.get("launch") and c["launch"].get("median_gap") is not None
                  and c["launch"]["compared"] >= 15 and any(k.get("developer_ppm") for k in c["classes"])]
    if not candidates:
        return None
    candidates.sort(key=lambda c: -c["launch"]["compared"])
    compound = candidates[week % min(len(candidates), 8)]
    name, developer = name_ar(compound), name_ar(compound.get("developer")) or "المطور"
    main = max((k for k in compound["classes"] if k.get("developer_ppm")), key=lambda k: k["units"])
    gap = compound["launch"]["median_gap"]
    cheaper = gap < 0
    bars = [("ريسيل، سعر العقد", main["median_asking_ppm"], ppm_ar(main["median_asking_ppm"]), COLORS["nile"]),
            (f"{developer} اليوم", main["developer_ppm"], ppm_ar(main["developer_ppm"]), COLORS["brass"])]
    if main.get("median_cash_ppm") and main.get("developer_cash_ppm"):
        bars += [("ريسيل، بقيمة اليوم", main["median_cash_ppm"], ppm_ar(main["median_cash_ppm"]), COLORS["nile"]),
                 ("المطور، بقيمة اليوم", main["developer_cash_ppm"], ppm_ar(main["developer_cash_ppm"]), COLORS["brass"])]
    return Story(
        f"compound-{compound['key']}", f"{name}: ريسيل ولا من المطور؟",
        f"تشتري في {name} ريسيل ولا من {developer}؟ الوحدة الريسيل النموذجية {'أرخص' if cheaper else 'أغلى'} "
        f"{_pct(gap)} من وحدة مماثلة جديدة.",
        [f"قارنّا {compound['launch']['compared']} وحدة ريسيل في {name} بوحدات {developer} المعروضة اليوم "
         "بنفس النوع والتشطيب والمساحة، على الأقل تفضيلًا بين السعر المعلن وقيمته اليوم.",
         f"{compound.get('good_count', 0)} وحدة في {name} أرخص بوضوح من البدائل الآن.",
         f"قبل ما تشتري في {name}: شوف كل الوحدات مرتبة من الأفضل."],
        f"/compounds/{quote(compound['key'])}", bars, f"متوسط سعر المتر في {name}",
        [f"#{name.replace(' ', '_')}", *HASHTAGS[:3]])


def movers_story(compounds: dict, overview: dict) -> Story:
    with_history = [c for c in compounds.values() if (c.get("history") or {}).get("turnover_30d") is not None
                    and c["units"] >= 25]
    fast = sorted(with_history, key=lambda c: -c["history"]["turnover_30d"])[:5]
    if fast and fast[0]["history"]["delisted_30d"]:
        bars = [(name_ar(c), c["history"]["turnover_30d"], _pct(c["history"]["turnover_30d"]), COLORS["nile"]) for c in fast]
        history = overview.get("history") or {}
        return Story(
            "movers", "أسرع الكمبوندات بيعًا الآن",
            f"أسرع 5 كمبوندات بيعًا في سوق الريسيل الآن: {name_ar(fast[0])} خرج منها {_pct(fast[0]['history']['turnover_30d'])} "
            "من المعروض في 30 يومًا.",
            [f"في آخر 30 يومًا خرج {history.get('delisted_30d', 0):,} إعلان ريسيل من السوق "
             f"({_pct(history.get('turnover_30d') or 0)} من المعروض). الخروج قد يعني البيع أو سحب الإعلان.",
             "الكمبوند اللي وحداته بتخرج بسرعة سعره عادل أو أرخص من البدائل؛ اللي وحداته قاعدة شهور غالبًا سعره عالي.",
             "شوف الوحدات اللي نزل سعرها مؤخرًا."],
            "/units?price_dropped=true", bars, "نسبة المعروض التي خرجت في 30 يومًا",
            HASHTAGS[:3] + ["#استثمار_عقاري"])
    below = sorted((c for c in compounds.values() if c.get("launch") and c["launch"].get("median_gap") is not None
                    and c["launch"]["compared"] >= 10), key=lambda c: c["launch"]["median_gap"])[:5]
    bars = [(name_ar(c), abs(c["launch"]["median_gap"]), _pct(c["launch"]["median_gap"]), COLORS["nile"]) for c in below]
    return Story(
        "below-developer", "الريسيل الأرخص من المطور",
        f"5 كمبوندات الريسيل فيها أرخص بوضوح من سعر المطور اليوم، أولها {name_ar(below[0])}." if below
        else "الريسيل مقابل سعر المطور اليوم",
        ["قارنّا كل وحدة ريسيل بسعر المطور اليوم لوحدة مماثلة في نفس الكمبوند، كاش وبقيمة الأقساط اليوم.",
         "دي الكمبوندات اللي الوحدة النموذجية فيها أبعد تحت سعر المطور."],
        "/units?sort=launch_gap", bars, "كم الريسيل أرخص من المطور", HASHTAGS[:4])


def card_svg(story: Story, stamp: str) -> str:
    """A portrait card: the hook, one chart and the link, in Qayem's colours."""
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" direction="rtl">',
             f'<rect width="{W}" height="{H}" fill="{COLORS["night"]}"/>',
             f'<text x="{W - 72}" y="118" fill="{COLORS["brass"]}" font-family="{FONT}" font-size="64" font-weight="700" '
             f'text-anchor="start">قيّم</text>',
             f'<text x="72" y="112" fill="{COLORS["muted"]}" font-family="{FONT}" font-size="30" direction="ltr" '
             f'text-anchor="start">qayem.ai</text>']
    y = 250
    for line in wrap(story.hook, 26)[:5]:
        parts.append(f'<text x="{W - 72}" y="{y}" fill="{COLORS["paper"]}" font-family="{FONT}" font-size="54" '
                     f'font-weight="700" text-anchor="start">{escape(line)}</text>')
        y += 76
    y += 40
    parts.append(f'<text x="{W - 72}" y="{y}" fill="{COLORS["muted"]}" font-family="{FONT}" font-size="32" '
                 f'text-anchor="start">{escape(story.chart_title)}</text>')
    y += 50
    top = max((value for _, value, _, _ in story.bars), default=1) or 1
    room = H - 190 - y
    step = min(120, room / max(1, len(story.bars)))
    for label, value, shown, colour in story.bars:
        width = max(6, (W - 144 - 260) * value / top)
        parts.append(f'<text x="{W - 72}" y="{y + 34}" fill="{COLORS["paper"]}" font-family="{FONT}" font-size="32" '
                     f'text-anchor="start">{escape(label[:24])}</text>')
        parts.append(f'<rect x="{W - 72 - width}" y="{y + 50}" width="{width}" height="30" rx="8" fill="{colour}"/>')
        parts.append(f'<text x="{W - 72 - width - 16}" y="{y + 75}" fill="{COLORS["paper"]}" font-family="{FONT}" '
                     f'font-size="30" font-weight="700" text-anchor="start">{escape(shown)}</text>')
        y += step
    parts.append(f'<line x1="72" y1="{H - 150}" x2="{W - 72}" y2="{H - 150}" stroke="{COLORS["line"]}" stroke-width="2"/>')
    parts.append(f'<text x="{W - 72}" y="{H - 90}" fill="{COLORS["paper"]}" font-family="{FONT}" font-size="34" '
                 f'text-anchor="start">قارن أي وحدة مجانًا قبل ما تدفع عربون</text>')
    parts.append(f'<text x="72" y="{H - 90}" fill="{COLORS["muted"]}" font-family="{FONT}" font-size="26" '
                 f'direction="ltr" text-anchor="start">{escape(stamp)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def build(snapshot, today: date | None = None) -> list[Story]:
    today = today or snapshot.today
    week = today.isocalendar().week
    stories = [market_story(snapshot.overview), compound_story(snapshot.compounds, week),
               movers_story(snapshot.compounds, snapshot.overview)]
    return [story for story in stories if story]


def write(stories: list[Story], out: Path, today: date, png: bool = False, chrome: str | None = None) -> dict:
    """brief.md (posts to copy), cards/*.svg (and .png with Chrome), index.html (a preview), brief.json."""
    year, week, _ = today.isocalendar()
    campaign = f"brief-{year}-w{week:02d}"
    cards = out / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    stamp = f"{today.isoformat()} · qayem.ai"
    lines = [f"# موجز قيّم الأسبوعي — {today.isoformat()}", "",
             "ثلاث قصص جاهزة للنشر (تيك توك / ريلز / لينكدإن / فيسبوك). كل رابط مُتتبَّع، فتظهر الزيارات في تقرير القمع.", ""]
    exported = []
    for index, story in enumerate(stories, 1):
        link = tracked(story.path, f"{campaign}-{index}")
        svg = cards / f"{index}-{story.slug}.svg"
        svg.write_text(card_svg(story, stamp), encoding="utf-8")
        image = svg.name
        if png and chrome:
            target = svg.with_suffix(".png")
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={W},{H}",
                            f"--screenshot={target}", svg.resolve().as_uri()], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            if target.exists():
                image = target.name
        lines += [f"## {index}. {story.title}", "", f"**{story.hook}**", "", *story.body, "",
                  f"🔗 {link}", "", " ".join(story.hashtags), "", f"![{story.title}](cards/{image})", ""]
        exported.append({"slug": story.slug, "title": story.title, "hook": story.hook, "body": story.body,
                         "link": link, "hashtags": story.hashtags, "card": f"cards/{image}"})
    (out / "brief.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "brief.json").write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
    items = "".join(f'<section><img src="{escape(e["card"])}" width="360" alt=""><div><h2>{escape(e["title"])}</h2>'
                    f'<p><b>{escape(e["hook"])}</b></p>' + "".join(f"<p>{escape(p)}</p>" for p in e["body"]) +
                    f'<p><a href="{escape(e["link"])}">{escape(e["link"])}</a></p><p>{escape(" ".join(e["hashtags"]))}</p>'
                    "</div></section>" for e in exported)
    (out / "index.html").write_text(
        f'<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>موجز قيّم {today}</title>'
        '<style>body{font-family:system-ui,sans-serif;max-width:980px;margin:40px auto;padding:0 16px;line-height:1.7}'
        'section{display:flex;gap:24px;margin:32px 0;align-items:flex-start}img{border-radius:12px;flex:none}'
        '@media(max-width:700px){section{flex-direction:column}}</style>'
        f"<h1>موجز قيّم الأسبوعي — {today}</h1>{items}</html>", encoding="utf-8")
    return {"stories": len(exported), "out": str(out), "campaign": campaign, "png": png and bool(chrome)}


def find_chrome() -> str | None:
    for candidate in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome",
                      "chromium", "chromium-browser"):
        if Path(candidate).exists() or shutil.which(candidate):
            return candidate if Path(candidate).exists() else shutil.which(candidate)
    return None
