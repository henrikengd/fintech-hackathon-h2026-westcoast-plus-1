"""Single-file HTML review sheet in NBIM's dark style. Read-only: decisions go through log_decision.

The page design lives in assets/ (style.css, report.js, logos). This module fills it with data, so every sheet stays one file.
"""
import base64
import json
import re
from hashlib import sha256
from html import escape

from desk import AGAINST, ROOT, RULES, UNCLEAR, WITH, rules_in_force

CALIBRATION = ROOT / "results" / "confidence.json"
SCREEN_FLAG = "similar to past votes against the board"
SCREEN_TEXT = "wording resembles proposals NBIM has opposed at other companies"
PAPERS = {  # position paper that sharpens each guideline section
    "1.1": ("Board independence", "https://www.nbim.no/contentassets/3bcb2b06ed0847c8ab5524e3a9baa555/board-independence.pdf"),
    "1.2": ("Board independence", "https://www.nbim.no/contentassets/3bcb2b06ed0847c8ab5524e3a9baa555/board-independence.pdf"),
    "1.3": ("Separation of chairperson and CEO", "https://www.nbim.no/contentassets/dbaeedf5d52749acab1528c0907c48d6/separation-of-chairperson-and-ceo.pdf"),
    "2.1": ("Time commitment of board members", "https://www.nbim.no/contentassets/081702e8e07a44fd9ab6236330523707/time-commitment-of-board-members.pdf"),
    "2.2": ("Industry expertise on the board", "https://www.nbim.no/contentassets/6410b1aa4870495a8079839b9143db3c/industry-expertise-on-the-board.pdf"),
    "2.3": ("Board diversity", "https://www.nbim.no/contentassets/577d15d0ed474f7884aaa2c722fbe241/board-diversity.pdf"),
    "3.1": ("Proxy access at US companies", "https://www.nbim.no/contentassets/cee61e4b036f45bc80d6ab888f4587ad/proxy-access-at-us-companies.pdf"),
    "3.3": ("CEO remuneration", "https://www.nbim.no/contentassets/24fdd154fecb4ca499faaf17e9bc9ba1/ceo-remuneration.pdf"),
    "4.1": ("Multiple share classes", "https://www.nbim.no/contentassets/c3fe8d1120bf47278fdd3167d85a3ea4/multiple-share-classes.pdf"),
    "4.2": ("Individual vote count in board elections", "https://www.nbim.no/contentassets/9a409564bfbd447790410f02ff4f7c90/individual-vote-count-in-board-elections.pdf"),
    "5.3": ("Corporate sustainability reporting", "https://www.nbim.no/contentassets/fc79158f623848b4b3417587ed1daede/corporate-sustainability-reporting_web.pdf"),
    "6.1": ("Shareholder rights in equity issuances", "https://www.nbim.no/contentassets/87c9372a06ac4c92800f81f928e44c26/shareholder-rights-in-equity-issuances.pdf"),
    "6.3": ("Related-party transactions", "https://www.nbim.no/contentassets/8dab7598dc29419f86fc14ddbf562c12/related-party-transactions.pdf"),
}
CSS = """
:root{--midnight:#001538;--blue:#0026ff;--sky:#faf9f5;--sand:#f5f2eb;--band:#f4cea4;--polar:#e7f6f8;
--muted:rgb(0 21 56/65%);--line:rgb(0 21 56/24%)}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--midnight);font:300 16px/24px "Hanken Grotesk",system-ui,sans-serif;font-variant-numeric:lining-nums tabular-nums}
.band{background:var(--band);padding:8px 24px;font-size:14px;font-weight:400}
.wrap{max-width:1024px;margin:auto;padding:0 24px}
header{background:var(--sand);padding:40px 0 32px}
h1{font-size:48px;line-height:60px;font-weight:500;letter-spacing:-.5px;margin:0 0 16px}
h2{font-size:24px;line-height:32px;font-weight:500;margin:40px 0 12px}
header p{margin:0}b{font-weight:500}
.figures{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:24px;margin:32px 0}
.figures div{border-top:1px solid var(--line);padding-top:8px;font-size:14px;color:var(--muted)}
.figures strong{display:block;font-size:40px;line-height:52px;font-weight:500;color:var(--midnight)}
table{width:100%;border-collapse:collapse}
th{background:var(--midnight);color:#fff;font-weight:500;text-align:left;padding:12px 16px}
td{padding:12px 16px;border-bottom:1px solid var(--line);vertical-align:top}
pre{white-space:pre-wrap;font:inherit}
tr.unclear td{background:var(--polar)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:32px;padding:0 12px;font-size:14px;font-weight:400;margin:0 8px 4px 0}
.tag.against{border-color:var(--midnight);background:var(--midnight);color:#fff}
.note{font-size:14px;line-height:20px;margin-top:8px}
.note span{color:var(--muted)}
blockquote{margin:8px 0;padding-left:12px;border-left:2px solid var(--blue);font-size:14px;line-height:20px}
a{color:var(--blue)}
details{font-size:14px;line-height:20px;margin-top:8px}summary{cursor:pointer}
.vote{font-weight:500}
footer{background:var(--sky);margin-top:48px;padding:24px 0;font-size:14px;line-height:20px;color:var(--muted)}
@media (max-width:640px){h1{font-size:32px;line-height:40px}td,th{padding:8px}}
@media print{.band{-webkit-print-color-adjust:exact;print-color-adjust:exact}details{display:none}}
"""
HEAD = ('<link rel="preconnect" href="https://fonts.gstatic.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@300;400;500&display=swap" rel="stylesheet">')
BAND = "Student prototype, Westcoast + 1, FinTech Hackathon H2026. Not an NBIM product."


def page(title, body):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{escape(title)}</title>{HEAD}<style>{CSS}</style></head><body><div class=band>{BAND}</div>{body}</body></html>")


def group(r):
    """Kinds of draft, as the 2024 calibration counts them."""
    flags = "screen" if clean(r.get("flags")) == SCREEN_FLAG else "flags" if clean(r.get("flags")) else "clean"
    return f"{r['lane']}|{r['confidence']}|{flags}"


def score(r):
    """Share of drafts of this kind that matched NBIM's vote in 2024. Below 95 goes to a person."""
    table = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    return table.get(group(r), table[r["lane"]])


def band(value):
    return "High" if value >= 95 else "Medium" if value >= 80 else "Low"


def audit(meeting_id, item):
    """One in twenty With board items goes to a person at random, so errors in that lane stay visible."""
    return int(sha256(f"{meeting_id}:{item}".encode()).hexdigest(), 16) % 20 == 0


def clean(value):
    return "" if value is None or str(value) in ("nan", "None", "") else str(value)


# Dark NBIM style pages ---------------------------------------------------------
ASSETS = ROOT / "assets"
LANE_KEY = {AGAINST: "against", UNCLEAR: "unclear", WITH: "with"}
FLAGS = "https://cdn.jsdelivr.net/npm/flag-icons@7.2.3/flags/4x3/{}.svg"
ISO = {"Australia": "au", "Belgium": "be", "Bermuda": "bm", "Brazil": "br", "British Virgin Islands": "vg", "Canada": "ca",
       "Cayman Islands": "ky", "Chile": "cl", "China": "cn", "Colombia": "co", "Denmark": "dk", "Egypt": "eg", "Finland": "fi",
       "France": "fr", "Germany": "de", "Hong Kong": "hk", "India": "in", "Indonesia": "id", "Ireland": "ie", "Italy": "it",
       "Japan": "jp", "Jersey": "je", "Kuwait": "kw", "Latvia": "lv", "Luxembourg": "lu", "Malaysia": "my", "Mexico": "mx",
       "Netherlands": "nl", "Norway": "no", "Poland": "pl", "Singapore": "sg", "South Africa": "za", "South Korea": "kr",
       "Spain": "es", "Sri Lanka": "lk", "Sweden": "se", "Switzerland": "ch", "Taiwan": "tw", "Thailand": "th",
       "United Arab Emirates": "ae", "United Kingdom": "gb", "United States": "us", "Vietnam": "vn"}
SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|ag|asa|ab|sa|nv|holdings?|group)\b")
NAV = """<nav class=nav aria-label="Account">
  <button class=lang type=button><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z"/></svg><span>Norsk</span></button>
  <a class=newreport href="/"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>New report</a>
  <span class=avatar aria-label="Profile" role="img"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c1.2-3.6 3.8-5.5 7-5.5s5.8 1.9 7 5.5"/></svg></span>
</nav>"""


def asset(name):
    return (ASSETS / name).read_text(encoding="utf-8")


def data_uri(path, kind):
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode()


def flag(country):
    code = ISO.get(str(country))
    return f'<img class=flag src="{FLAGS.format(code)}" alt="">' if code else ""


def logo(company):
    """A logo in assets/logos, named by the cleaned company name, or None."""
    name = " ".join(SUFFIX.sub(" ", re.sub(r"[^a-z0-9 ]", " ", str(company).lower())).split())
    path = ASSETS / "logos" / f"{name.replace(' ', '-')}.png"
    return data_uri(path, "image/png") if path.is_file() else None


def dark_page(title, body, script=""):
    bar = f'<div class=topbar><div class=bar><img class=logo src="{data_uri(ASSETS / "nbim-logo.svg", "image/svg+xml")}" alt="Norges Bank Investment Management">{NAV}</div></div>'
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{escape(title)}</title>{HEAD.replace('300;400;500', '400;500;600')}<style>{asset('style.css')}</style></head>"
            f"<body>{bar}{body}{script}</body></html>")


def sections(day):
    """Full text of each guideline section in force on the meeting date, for Read more."""
    out = {}
    for r in rules_in_force(day):
        part = out.setdefault(r["section"], {"heading": r["heading"], "quotes": []})
        if r["quote"] not in part["quotes"]:
            part["quotes"].append(r["quote"])
    return {k: {"heading": v["heading"], "text": " ".join(v["quotes"])} for k, v in out.items()}


def review(r):
    if r["lane"] != WITH:
        return "Person"
    return "Audit" if audit(r["meeting_id"], r["item"]) else "Batch"


def item(r):
    lane, section = r["lane"], clean(r.get("section"))
    rule = clean(r.get("rule"))
    template = RULES["templates"].get(section) if lane == AGAINST else None
    paper = PAPERS.get(section) if template else None
    return {"item": str(r["item"]), "lane": LANE_KEY[lane], "text": str(r["proposal_text"]), "board": clean(r.get("mgmt_rec")),
            "vote": clean(r.get("draft")), "score": score(r), "review": review(r), "why": clean(r.get("why")),
            "section": section if rule else "", "quote": clean(r.get("quote")) if rule else "", "cited": str(r.get("cited")) == "True",
            "evidence": clean(r.get("evidence")), "check": clean(r.get("fact")),
            "flags": clean(r.get("flags")).replace(SCREEN_FLAG, SCREEN_TEXT), "rationale": template or "", "paper": list(paper) if paper else None}


def counts(items):
    return {k: sum(i["lane"] == k for i in items) for k in ("against", "unclear", "with")}


def review_sheet(frame, cost=None, drafted_by=None):
    """One meeting. `frame` is the output of desk.decide_all. The page is drawn by assets/report.js from the embedded data."""
    first = frame.iloc[0]
    items = [item(r) for r in frame.to_dict("records")]
    day = str(first["meeting_date"])
    data = {"company": str(first["company"]), "country": clean(first.get("country")), "meeting_date": day,
            "items": items, "sections": sections(day), "counts": counts(items), "drafted_by": drafted_by or ""}
    info = [f"<li>Country: {escape(data['country'] or 'Not stated')} {flag(data['country'])}</li>"]
    if "record" in frame:
        info.append(f"<li>Vote record: {escape(str(first['record']))}</li>")
    if drafted_by:
        info.append(f"<li>Drafted by {escape(drafted_by)}, which is not the evaluated setup</li>")
    history = (f'<section><details class=history><summary>NBIM\'s earlier votes at this company</summary><pre>{escape(str(first["history"]))}</pre></details></section>'
               if "history" in frame and clean(first.get("history")) else "")
    body = f"""<header class=wrap>
  <p class=eyebrow>Stemmegivningsrapport</p>
  <h1>{escape(data['company'])}</h1>
  <ul class=info>{''.join(info)}</ul>
  <p class=meeting>General meeting {escape(day)}</p>
  <div class=overview>
    <div class="summary total" id=total></div>
    <div class=summary><div class=lanes id=lanes></div><div class=split id=split aria-hidden="true"></div></div>
  </div>
</header>
<main class=wrap data-company="{escape(data['company'], quote=True)}" data-date="{escape(day, quote=True)}">
  <section>
    <div class=bar-head><h2>Proposals</h2><div class=seg id=filters role=group aria-label="Show proposals"></div></div>
    <div class=cols aria-hidden="true"><span>#</span><span>Proposal</span><span>Board</span><span>Proposed</span><span>Confidence</span><span>Review</span><span></span></div>
    <div id=list></div>
    <div class=tools><button id=toggle type=button>Open all</button></div>
  </section>
  {history}
</main>"""
    payload = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
    script = f'<script id=data type="application/json">{payload}</script><script>{asset("report.js")}</script>'
    return dark_page(f"Review sheet, {data['company']}", body, script)


def sheet_data(html):
    """The data a sheet was drawn from, or None for sheets from before this design."""
    found = re.search(r'<script id=data type="application/json">(.*?)</script>', html, re.S)
    return json.loads(found.group(1).replace("<\\/", "</")) if found else None


def tile(data, href):
    """One earlier report on the upload page."""
    c = data.get("counts", {})
    total = sum(c.values())
    mark = logo(data["company"])
    picture = f'<img src="{mark}" alt="{escape(data["company"], quote=True)}">' if mark else f'<span class=word>{escape(data["company"])}</span>'
    return (f'<a class=tile href="{escape(href, quote=True)}"><h3>{escape(data["company"])}</h3>'
            f'<p class=sub><span class=place>{escape(data.get("country") or "Country not stated")} {flag(data.get("country"))}</span><br>General meeting {escape(data["meeting_date"])}</p>'
            f'<div class=stats><p><b>{total} proposals</b></p><p>{c.get("against", 0)} against the board</p><p>{c.get("unclear", 0)} unclear</p>'
            f'<p>{c.get("with", 0)} with the board</p></div><div class=mark>{picture}</div></a>')
