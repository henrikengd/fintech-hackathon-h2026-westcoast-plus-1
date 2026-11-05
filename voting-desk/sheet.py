"""Single-file HTML review sheet in the column order of NBIM's voting records. Read-only: decisions go through log_decision."""
import json
from hashlib import sha256
from html import escape

from desk import AGAINST, MODEL, EFFORT, PROMPT_HASH, ROOT, RULES, UNCLEAR, WITH

GUIDELINES = RULES["source"]
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


def row_html(r):
    lane, why, rule, section = r["lane"], clean(r.get("why")), clean(r.get("rule")), clean(r.get("section"))
    needs = "Person" if lane != WITH else "Audit" if audit(r["meeting_id"], r["item"]) else "Batch"
    tag = f'<span class="tag{" against" if lane == AGAINST else ""}">{lane}</span>'
    if rule:
        basis = f'<a href="{GUIDELINES}">Global Voting Guidelines {escape(section)}</a>' + ("" if r.get("cited") else ", quote not verified")
    else:
        basis = f'<a href="{GUIDELINES}">Global Voting Guidelines</a>, starting point: support the board'
    detail = ""
    if rule:
        detail += f"<blockquote>{escape(clean(r.get('quote')))}</blockquote>"
    if clean(r.get("evidence")):
        detail += f"<blockquote>From the filing: {escape(clean(r['evidence']))}</blockquote>"
    if clean(r.get("flags")):
        detail += f"<div class=note><span>Sent to a person:</span> {escape(clean(r['flags']).replace(SCREEN_FLAG, SCREEN_TEXT))}</div>"
    template = RULES["templates"].get(section)
    if template and lane == AGAINST:
        paper = PAPERS.get(section)
        link = f' <a href="{paper[1]}">Position paper: {escape(paper[0])}</a>.' if paper else ""
        detail += f"<div class=note><b>Vote rationale:</b> {escape(template)}{link}</div>"
    fold = f"<details><summary>Reason and source</summary>{detail}</details>" if detail else ""
    check = f'<div class=note><span>Check:</span> {escape(clean(r.get("fact")))}</div>' if clean(r.get("fact")) and lane != WITH else ""
    return (f'<tr data-item="{escape(str(r["item"]))}" data-vote="{escape(clean(r["draft"]))}"{" class=unclear" if lane == UNCLEAR else ""}>'
            f'<td>{escape(str(r["item"]))}</td><td>{tag}<div>{escape(str(r["proposal_text"]))}</div>'
            f'<div class=note><span>Draft reason:</span> {escape(why)}</div><div class=note><span>Basis:</span> {basis}</div>{check}{fold}</td>'
            f'<td>{escape(clean(r["mgmt_rec"])) or "Not stated"}</td><td class=vote>{escape(clean(r["draft"]))}</td>'
            f'<td>{band(score(r))} {score(r)} %</td><td>{needs}</td></tr>')


def review_sheet(frame, cost=None, drafted_by=None):
    """One meeting. `frame` is the output of desk.decide_all."""
    first = frame.iloc[0]
    n = len(frame)
    lanes = frame["lane"].value_counts()
    figures = [(n, "proposals"), (lanes.get(AGAINST, 0), "against the board"), (lanes.get(UNCLEAR, 0), "unclear"), (lanes.get(WITH, 0), "with the board")]
    fig = "".join(f"<div><strong>{v}</strong>{k}</div>" for v, k in figures)
    rows = "".join(row_html(r) for r in frame.to_dict("records"))
    spent = f" Cost ${cost:.3f}." if cost is not None else ""
    made = f"Drafted by {drafted_by}, which is not the evaluated setup." if drafted_by else f"Model {MODEL}, effort {EFFORT}, prompt {PROMPT_HASH}."
    record = f"<p><b>Vote record used:</b> {escape(str(first['record']))}</p>" if "record" in frame else ""
    history = (f"<details><summary>NBIM's earlier votes at this company</summary><pre>{escape(str(first['history']))}</pre></details>"
               if "history" in frame else "")
    body = f"""<header><div class=wrap><h1>{escape(str(first['company']))}</h1>
<p><b>Country:</b> {escape(str(first['country']))}</p><p><b>Meeting date:</b> {escape(str(first['meeting_date']))}</p>
{record}</div></header>
<main class=wrap data-company="{escape(str(first['company']), quote=True)}" data-date="{escape(str(first['meeting_date']), quote=True)}"><div class=figures>{fig}</div>
<table><thead><tr><th>#</th><th>Proposal</th><th>Mgt rec</th><th>Proposed vote</th><th>Confidence</th><th>Review</th></tr></thead><tbody>{rows}</tbody></table>
{history}<p class=note>Nothing is published before a stewardship manager has signed off. A verified quote shows that the rule exists and was in force, not that it applies.</p></main>
<footer><div class=wrap>{made}{spent} Sources: company documents and NBIM's published guidelines and votes. This page is not investment advice.</div></footer>"""
    return page(f"Review sheet, {first['company']}", body)
