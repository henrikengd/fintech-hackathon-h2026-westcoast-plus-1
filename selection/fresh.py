"""Build the sealed test set from NBIM's voting API. Prints counts only, never 2026 outcomes.

    python fresh.py --check   compare the normalising against pre-2026 real_votes.csv rows
    python fresh.py           select, fetch (resumes from cache/), write fresh_votes.csv and fresh_manifest.json
"""
import csv, hashlib, json, os, random, re, sys, threading, time, urllib.error, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import pandas as pd

SEED, TARGET, CUT = 2026, 1000, "2026-01-01"
HERE = Path(__file__).parent
H = Path("C:/Users/nikki/Desktop/Industrial_Economics/Hackathon")
BASE = "https://vd.a.nbim.no/v1"
COLS = ["meeting_id", "company_id", "company", "ticker", "country", "market", "meeting_date", "item_no", "proposal_number",
        "proposal_text", "proponent", "mgmt_rec", "nbim_vote_raw", "nbim_vote", "against_board", "rationale_text", "rationale_section", "year"]
VOTE = {"For": "FOR", "Against": "MOT", "Withhold": "MOT", "Abstain": "AVSTÅ"}
MGMT = {"For": "FOR", "Against": "MOT", "Abstain": "AVSTÅ"}

KEY = re.search(r'^\s*NBIM_API_KEY1\s*=\s*["\']?([^"\'\s]+)', (H / "fintech-hackathon-h2026-westcoast-plus-1/.env").read_text(encoding="utf-8"), re.M).group(1)
errors, lock, slot = Counter(), threading.Lock(), [0.0]


def get(path):
    """GET at most 8 calls per second across threads. None means not found."""
    for attempt in range(6):
        with lock:
            wait = slot[0] - time.time()
            slot[0] = max(slot[0], time.time()) + 0.125
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(BASE + path, headers={"x-api-key": KEY, "User-Agent": "nbim-hackathon"})
        try:
            with urllib.request.urlopen(request, timeout=60) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            errors[f"http_{e.code}"] += 1
            if e.code in (401, 403):
                sys.exit(f"NBIM refused the request ({e.code})")
            if e.code == 404:
                return None
            if e.code == 429 and b"QUOTA" in e.read():
                sys.exit("NBIM quota reached. Rerun to resume.")
            time.sleep(min(int(e.headers.get("Retry-After") or 0) or 2 ** (attempt + 1), 60))
            continue
        except Exception as e:
            errors[type(e).__name__] += 1
            time.sleep(2 ** (attempt + 1))
            continue
        if data.get("status") == "error" or data.get("message") == "Not found":
            errors["rejected_or_not_found"] += 1
            return None
        return data
    sys.exit(f"Gave up after 6 attempts: {path.split('/')[2]}. Rerun to resume.")  # a silent gap would change the selection


def company_key(name):  # copied from fetch_sec.py
    name = re.sub(r"/[a-z]+/?$", "", name.lower())
    words = re.sub(r"[^a-z0-9 ]", " ", name).split()
    drop = {"the", "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "holdings", "holding", "group"}
    return " ".join(w for w in words if w not in drop)


def search_term(name):  # from arkiv/votes.py
    return re.split(r"[^\w .-]", name)[0].strip(" .-")


def rows_for(meeting, country, market, sections):
    """One real_votes.csv row per proposal, in API order, which is what item_no counts."""
    date = meeting["meetingDate"][:10]
    out = []
    for i, v in enumerate(meeting["meetingVotes"], 1):
        vote_raw, mgmt_raw = str(v["voteInstruction"]), str(v["managementRec"])
        vote, mgmt = VOTE.get(vote_raw, ""), MGMT.get(mgmt_raw, "")
        text = " ".join(r.get("publicRationaleOutgoing") or "" for r in v["voterRationale"] or []).strip()
        out.append({
            "meeting_id": meeting["meetingId"], "company_id": meeting["companyId"], "company": meeting["companyName"],
            "ticker": meeting["companyTicker"], "country": country, "market": market, "meeting_date": date, "item_no": i,
            "proposal_number": v["proposalNumber"], "proposal_text": v["proposalText"], "proponent": v["proponent"], "mgmt_rec": mgmt,
            "nbim_vote_raw": vote_raw, "nbim_vote": vote, "against_board": "" if not (mgmt and vote) else float(mgmt != vote),
            "rationale_text": text, "rationale_section": sections.get(text, "OTHER") if text else "", "year": int(date[:4])})
    return out


def development():
    """Rows before 2026 only: nothing here may come from a 2026 outcome."""
    real = pd.read_csv(H / "voting-desk/data/real_votes.csv", dtype=str, keep_default_na=False)
    dev = real[real.meeting_date < CUT]
    texted = dev[dev.rationale_text != ""]
    assert not texted.groupby("rationale_text").rationale_section.nunique().gt(1).any()
    named = texted.drop_duplicates("rationale_text")
    return real, dev, dict(zip(named.rationale_text, named.rationale_section))


def check():
    assert company_key("The Apple, Inc.") == company_key("APPLE INC") == "apple"
    assert search_term("10X Genomics, Inc.") == "10X Genomics"
    _, dev, sections = development()
    wanted = pd.concat([dev[dev.rationale_text != ""].drop_duplicates("meeting_id").sample(40, random_state=7), dev.drop_duplicates("meeting_id").sample(10, random_state=7)])
    bad, n = Counter(), 0
    for mid, country, market in wanted[["meeting_id", "country", "market"]].drop_duplicates("meeting_id").values:
        got = rows_for(get(f"/query/meeting/{mid}")["meeting"], country, market, sections)
        want = dev[dev.meeting_id == mid].sort_values("item_no", key=lambda s: s.astype(int)).to_dict("records")
        assert len(got) == len(want), mid
        for g, w in zip(got, want):
            n += 1
            for c in COLS:
                if str(g[c]) != w[c]:
                    if not bad[c]:
                        print("first mismatch", c, mid, repr(str(g[c]))[:90], repr(w[c])[:90])
                    bad[c] += 1
    found = (get("/query/company/Burgan%20Bank") or {}).get("companies")
    found = [found] if isinstance(found, dict) else found
    print("rows compared", n, "mismatches", dict(bad), "lookup keys", sorted(found[0]), "meeting keys", sorted(found[0]["meetings"][0]), "errors", dict(errors))


def cached(path, key_field):
    return {json.loads(line)[key_field]: json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()} if path.exists() else {}


def append(path, row):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    real, dev, sections = development()
    market_of = dict(zip(real.country, real.market))
    old_ids, old_keys = set(real.company_id), {company_key(n) for n in real.company}

    (HERE / "cache").mkdir(exist_ok=True)
    list_file = HERE / "cache" / "names.json"
    if not list_file.exists():
        list_file.write_text(json.dumps(get("/ds/companies")["dscompanies"]["companies"], ensure_ascii=False), encoding="utf-8")
    listed = sorted({c["n"] for c in json.loads(list_file.read_text(encoding="utf-8"))})
    names = [n for n in listed if company_key(n) not in old_keys]
    random.Random(SEED).shuffle(names)  # order fixed here, before any company or meeting is fetched
    order_sha = hashlib.sha256("\n".join(names).encode()).hexdigest()

    lookups, meetings = HERE / "cache" / "lookups.jsonl", HERE / "cache" / "meetings.jsonl"
    done_names = cached(lookups, "query")
    done_meetings = cached(meetings, "meetingId")
    pool = ThreadPoolExecutor(8)
    rows, seen, count = [], set(), Counter()
    open_2026 = 0

    for name in names:
        count["names_tried"] += 1
        if name not in done_names:
            term = search_term(name)
            data = get(f"/query/company/{quote(term, safe='')}") if len(term) > 2 else None
            found = (data or {}).get("companies") or []
            done_names[name] = {"query": name, "companies": [found] if isinstance(found, dict) else found}
            append(lookups, done_names[name])
        companies = done_names[name]["companies"]
        exact = [c for c in companies if c.get("name") == name] or [c for c in companies if company_key(c.get("name") or "") == company_key(name)]
        if not exact:
            count["names_unmatched"] += 1
        for c in exact:
            if c["id"] in seen or str(c["id"]) in old_ids or company_key(c.get("name") or "") in old_keys:
                count["dropped_after_lookup"] += 1
                continue
            seen.add(c["id"])
            ids = [m["meetingId"] for m in c["meetings"]]
            if not any(m["meetingDate"][:10] >= CUT for m in c["meetings"]):
                count["no_2026_meeting"] += 1
                continue
            todo = [i for i in ids if i not in done_meetings]
            for i, data in zip(todo, pool.map(lambda i: get(f"/query/meeting/{i}"), todo)):
                done_meetings[i] = (data or {}).get("meeting") or {"meetingId": i, "meetingVotes": [], "meetingDate": ""}
                append(meetings, done_meetings[i])
            got = [done_meetings[i] for i in ids]
            # A meeting counts if NBIM cast any vote; the direction is not read.
            scored = {m["meetingId"] for m in got if m["meetingDate"][:10] >= CUT and any(v["voteInstruction"] in VOTE for v in m["meetingVotes"])}
            if not scored:
                count["no_2026_meeting_with_votes"] += 1
                continue
            open_2026 += len(scored)
            count["companies_kept"] += 1
            for m in got:
                if m["meetingVotes"]:
                    rows += rows_for(m, c["country"], market_of.get(c["country"], ""), sections)
                else:
                    count["meetings_empty"] += 1
        if count["names_tried"] % 100 == 0:
            print(f"names {count['names_tried']}, companies {count['companies_kept']}, 2026 meetings {open_2026}, errors {dict(errors)}", flush=True)
        if open_2026 >= TARGET:
            break
    pool.shutdown()
    assert open_2026 >= TARGET

    frame = pd.DataFrame(rows, columns=COLS).drop_duplicates(["meeting_id", "item_no"])
    path = HERE / "fresh_votes.csv"
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    assert not set(frame.company_id.astype(str)) & old_ids
    assert not {company_key(n) for n in frame.company} & old_keys

    new = frame[frame.meeting_date >= CUT]
    per_year = frame.groupby("year").size().to_dict()
    unmapped = sorted(set(frame.country[frame.market == ""]))
    old_tickers = set(zip(real.ticker, real.country))
    facts = {
        "companies": int(frame.company_id.nunique()), "meetings": int(frame.meeting_id.nunique()), "rows": len(frame),
        "rows_per_year": {int(k): int(v) for k, v in per_year.items()},
        "rows_2026_on": len(new), "meetings_2026_on": int(new.meeting_id.nunique()), "meetings_2026_on_with_cast_vote": open_2026,
        "countries": int(frame.country.nunique()), "countries_without_market": unmapped,
        "mgmt_rec_present_share": round(float((frame.mgmt_rec != "").mean()), 4),
        "mgmt_rec_present_share_2026_on": round(float((new.mgmt_rec != "").mean()), 4),
        "same_ticker_and_country_as_the_194": len({(str(t), c) for t, c in zip(frame.ticker, frame.country)} & old_tickers),
        "selection_counts": dict(count), "api_errors": dict(errors)}
    manifest = {
        "seed": SEED, "target_meetings": TARGET, "cutoff": CUT, "api": BASE, "built": time.strftime("%Y-%m-%d"),
        "rule": ("Take /ds/companies names, unique and sorted. Drop any whose company_key (fetch_sec.py) matches one of the 194 in data/real_votes.csv. "
                 "random.Random(2026).shuffle the rest, before any company or meeting fetch. Walk in that order. Look each name up with /query/company, keep results "
                 "whose name equals the listed name, else whose company_key does. Drop a result whose id or company_key is among the 194, and one already taken. "
                 "Skip a company with no listed meeting from 2026-01-01, or none with a cast vote (For, Against, Abstain, Withhold; direction is not read). "
                 "Otherwise keep every meeting of that company, all years. Stop after the first name that brings the 2026 meeting count to at least 300."),
        "normalising": ("voteInstruction and managementRec stored as text. nbim_vote: For=FOR, Against/Withhold=MOT, Abstain=AVSTÅ, else blank. mgmt_rec same without Withhold. "
                        "against_board: blank if either is blank, else 1.0 if they differ. item_no: position in the API response. rationale_text: publicRationaleOutgoing joined. "
                        "rationale_section: exact text lookup from pre-2026 rows of real_votes.csv, OTHER if unseen. market: country map from real_votes.csv, blank if unmapped."),
        "name_order_sha256": order_sha, "csv": path.name, "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **facts}
    (HERE / "fresh_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(facts, ensure_ascii=False))


if __name__ == "__main__":
    check() if "--check" in sys.argv else main()
