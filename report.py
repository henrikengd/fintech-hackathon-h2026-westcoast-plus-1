"""Write the one-page requirements response and the seed-picked review sheets from results/. Needs no API key.

Every number on the page comes from results/metrics.json. The sheets use a fixed seed, so nobody picked the examples.
"""
import boot  # noqa: F401
import json
import random

import pandas as pd

import desk
import sheet
from run import OUT, SEED

MONTHS = "januar februar mars april mai juni juli august september oktober november desember".split()
VIEWS = (("Agenten med styret, modellen lav", "with_board_model_low"), ("Agenten med styret, modellen høy", "with_board_model_high"), ("Agenten usikker", "unsure"),
         ("Agenten mot styret, modellen lav", "against_model_low"), ("Agenten mot styret, modellen høy", "against_model_high"))


def pct(x, d=1):
    return f"{x * 100:.{d}f}".replace(".", ",") + " %"


def num(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


def points(x):
    return f"{x * 100:+.1f}".replace(".", ",").replace("-", "−")


def tall(x):
    return f"{x:,}".replace(",", " ")


def day(iso):
    return f"{int(iso[8:])}. {MONTHS[int(iso[5:7]) - 1]} {iso[:4]}"


def planted(m):
    """Attempts in the ballot text with the defences on."""
    on = [r for r in m["resistance"] if r["defences"] and r["payload"] != "control"]
    return sum(r["items"] for r in on), sum(r["flagged"] for r in on), sum(r["reached_with_board"] for r in on)


def table(s, q):
    named = {b["method"]: b for b in s["baselines"]}
    history, lane = s["baselines_after_freeze"][0], s["against_lane"]
    rows = [("Følg styret", 0, 1, None, ""), *[(label, named[key]["recall"], named[key]["cleared"], named[key]["precision"], "")
                                               for label, key in (("Gjenta forrige stemme", "Repeat the last vote"),)],
            ("Historikkmodell, enkel og lokal", history["recall"], history["cleared"], history["precision"], ""),
            ("Voting Desk, alt til en person", s["reach_person"], s["cleared"], q["routed_precision"], " class=own"),
            ("Voting Desk, sporet Mot styret", lane["recall"], 1 - (lane["tp"] + lane["fp"]) / s["scored"], lane["precision"], " class=own")]
    cells = "".join(f"<tr{own}><td>{name}</td><td>{pct(a)}</td><td>{pct(b)}</td><td>{pct(c) if c else '–'}</td></tr>" for name, a, b, c, own in rows)
    return f"<table><thead><tr><th>Forseglet test</th><th>Mot styret fanget</th><th>Ikke flagget</th><th>Presisjon</th></tr></thead><tbody>{cells}</tbody></table>"


def two_views(views):
    cells = "".join(f"<tr><td>{name}</td><td>{tall(views[key]['proposals'])}</td><td>{pct(views[key]['against_board'])}</td></tr>" for name, key in VIEWS)
    return f"<table><thead><tr><th>To uavhengige syn, beregnet etter kjøringen</th><th>Forslag</th><th>NBIM mot styret</th></tr></thead><tbody>{cells}</tbody></table>"


def page(m):
    s, q, d, c, f, late = m["sealed"], m["sealed_queue"], m["development"], m["policy_chair_ceo"], m["policy_founder"], m["sealed_after_run"]
    ag, lane, mot, board = m["agent_sealed"], s["against_lane"], s["literal_mot_draft"], s["literal_mot_follow_board"]
    history = s["baselines_after_freeze"][0]
    base_rate = 1 - s["against"] / s["scored"]
    high = s["confidence_bands"]["High"]["draft_matches_nbim"]
    arms = {a["wording"]: a for a in m["document_resistance"]["arms"]}
    wide = m["document_resistance_20"]
    wide_arms = {a["wording"]: a for a in wide["arms"]}
    direct, indirect, false = wide_arms["case"], wide_arms["indirect"], wide_arms["false_statement"]
    followed = max(a["followed_filings"] for a in (direct, indirect, false))
    x = d["after_sealed_run"]
    local, frozen, season, rules = x["local_model"], x["frozen_history"], x["lane_by_season"], x["rule_entries"]
    tried, flagged, reached = planted(m)
    figures = [(pct(s["reach_person"]), f"av stemmene mot styret når en person (intervall {pct(s['reach_person_ci'][0])} til {pct(s['reach_person_ci'][1])})"),
               (pct(s["cleared"]), f"av forslagene går til samlet signering (intervall {pct(s['cleared_ci'][0])} til {pct(s['cleared_ci'][1])})"),
               (pct(lane["precision"]), f"presisjon når agenten foreslår å stemme mot styret, og {pct(lane['recall'])} recall")]
    fig = "".join(f"<div><strong>{v}</strong>{k}</div>" for v, k in figures)
    rule = late["deciding_rule"]
    cuts = "; ".join(f"{num(r['cut'], 2)}{' (låst)' if r['frozen'] else ''} gir {pct(r['reach_person'])} og {pct(r['cleared'])}" for r in s["operating_points"]["rows"])
    built = ("Voting Desk leser sakslisten til en generalforsamling og foreslår FOR, MOT eller AVSTÅ på hvert forslag. "
             "Beslutningen vi støtter, er hvilke forslag en stewardship manager må lese før stemmen publiseres. "
             "Agenten foreslår, koden kontrollerer, og mennesket bestemmer. "
             "Hvert utkast viser regelen det hviler på, og lav konfidens går alltid til en person.")
    verified = (f"Fasit er NBIMs publiserte stemmer, og målet er om NBIM stemte annerledes enn styret. "
                f"Accuracy duger ikke: å alltid følge styret gir {pct(base_rate)} og fanger ingen. "
                f"Vi låste systemet og kjørte det én gang på {tall(s['meetings'])} møter i {s['companies']} selskaper utenfor utviklingen, {s['against']} stemmer mot styret. "
                "Vi slår å følge styret og å gjenta forrige stemme, men ikke vår egen enkle modell på ruting. Den gir ingen stemme eller begrunnelse.")
    match, unread = late["section_match"], late["unread"]
    notes = (f"Terskelen {num(s['operating_points']['rows'][1]['cut'], 2)} på tekstmodellens risikoskår avgjør hva en person leser. Den ble satt før testen, ved om lag 90 % fangst i andre selskaper, og er teamets valg: {cuts} (når en person, samlet signering). "
             f"MOT: presisjon {pct(mot['precision'])}, recall {pct(mot['recall'])}; å følge styret gir {pct(board['precision'])} og {pct(board['recall'])}. Høy konfidens stemte med NBIM i {pct(high)} av tilfellene. "
             "Fasit for 2026 er fra NBIMs stemme-API, klarert med arrangøren; systemet trenger det ikke i drift.")
    fn, fy = f["not_founder"], f["founder"]
    policy = (f"Retningslinjene åpnet til og med 2025 for å støtte grunnleggere som er både styreleder og konsernsjef, og NBIM stemte mot i {fn['against']} av {fn['n']} saker uten grunnlegger og {fy['against']} av {fy['n']} med (etikettene er våre). "
              f"Etter at «will not» ble «may not» i 2026, falt stemmene mot fra {c['before']['against']} av {c['before']['n']} til {c['after']['against']} av {c['after']['n']}. "
              "Utvalgene er små, men historikk må vektes ned når en regel endres.")
    need = (f"Vi testet {d['ideas_failed']} ideer mot krav skrevet på forhånd, og ingen besto. "
            f"En lokal modell vi prøvde i gruppen, var ikke like god, {pct(local['batch_at_equal_reach'])} til samlet signering ved lik fangst, men forskjellen er ikke bevist. "
            "Med én uke til ville vi hentet fakta fra innkallinger utenfor USA, testet Opus og en lokal språkmodell, og lagt til posisjonsstørrelse.")
    limits = (f"Agenten fulgte ingen plantet instruks: {reached} av {tried} nådde samlet signering i sakslisten, og {followed} av {wide['filings_complete']} innkallinger ble fulgt. "
              "Indirekte ordlyd slipper likevel forbi skanningen.")
    caveats = (f"<b>Begrensninger:</b> {unread['against_in_batch']} av {s['against']} stemmer mot styret ble ikke lest. "
               "Testen leste saksteksten, ikke innkallinger. "
               f"Sporet Mot styret er svakt fra juli, {season['from_july'][0]} av {season['from_july'][1]} rett. "
               f"{rules['undated']} av {rules['total']} regler bruker dagens tekst. "
               "Modellminne kan ikke utelukkes.")
    values = ("<b>NBIMs verdier:</b> Kvalitet: én låst test. Integritet: svake tall står her. Innovasjon: test på ukjente selskaper. Lagånd: digital kollega og stewardship manager deler arbeidet.")
    css = sheet.CSS + """
@page{size:A4;margin:0}
body{font-size:13px;line-height:16.7px}
.wrap{max-width:none;padding:0 26px}.band{padding:3px 26px;font-size:10.8px;line-height:13px}
header{padding:5px 0 4px}h1{font-size:21px;line-height:25px;margin:0}header p{font-size:11.6px;line-height:14px}
h2{font-size:15px;line-height:20px;margin:18px 0 3px}p{margin:0}
.figures{margin:4px 0 0;gap:14px;grid-template-columns:repeat(3,1fr)}.figures div{font-size:10.6px;line-height:13px;padding-top:3px}.figures strong{font-size:21px;line-height:25px}
.tables{display:grid;grid-template-columns:1.12fr 1fr;gap:12px;margin-top:5px}table{margin:0}th{padding:2px 6px;font-size:10.8px;line-height:13.6px}td{padding:1px 6px;font-size:10.8px;line-height:13.8px}tr.own td{background:var(--sand);font-weight:500}
.small{font-size:11.5px;line-height:15px;margin-top:9px}"""
    body = f"""<header><div class=wrap><h1>Voting Desk</h1><p>Kravrespons, case 1 Stemmegivningsagenten.</p></div></header>
<main class=wrap><div class=figures>{fig}</div>
<h2>Hva vi bygde</h2><p>{built}</p>
<h2>Hvordan vi verifiserte det</h2><p>{verified}</p>
<div class=tables>{table(s, q)}{two_views(late["two_views"])}</div><p class=small>{notes}</p>
<h2>Retningslinje mot praksis</h2><p>{policy}</p>
<h2>Hva vi ville trengt videre</h2><p>{need}</p>
<h2>Motstandstest og begrensninger</h2><p>{limits}</p>
<p class=small>{caveats}</p>
<p class=small>{values}</p></main>"""
    html = sheet.page("Voting Desk, kravrespons", body).replace(sheet.CSS, css).replace('lang="en"', 'lang="no"').replace(sheet.BAND, "Studentprototype, Westcoast + 1, FinTech Hackathon H2026. Ikke et NBIM-produkt.")
    (desk.ROOT / "results" / "Kravrespons.html").write_text(html, encoding="utf-8")


def write_sheet(frame, prefix):
    name = "".join(c if c.isalnum() else "_" for c in frame["company"].iloc[0]).strip("_")
    (OUT / "sheets" / f"{prefix}_{name}.html").write_text(sheet.review_sheet(frame), encoding="utf-8")


def seeded(frame):
    ids = sorted(frame["meeting_id"].unique())
    random.Random(SEED).shuffle(ids)
    return ids


def samples():
    (OUT / "sheets").mkdir(exist_ok=True)
    kinds = {"item": str, "meeting_id": str, "company_id": str}
    test = pd.read_csv(OUT / "items_test.csv", dtype=kinds)
    for mid in seeded(test)[:3]:
        write_sheet(test[test["meeting_id"] == mid], "holdout")
    sealed = pd.read_csv(OUT / "items_sealed.csv", dtype=kinds)
    lanes = sealed.groupby("meeting_id")["lane"].agg(set)
    missed = set(sealed.loc[(sealed["against"] == 1) & (sealed["lane"] == sheet.WITH), "meeting_id"])
    order = seeded(sealed)
    pick = next(m for m in order if m in missed and sheet.AGAINST in lanes[m])  # the first meeting in seed order that shows both a catch and a miss
    frame = sealed[sealed["meeting_id"] == pick]
    write_sheet(frame, "sealed")
    miss = frame[(frame["against"] == 1) & (frame["lane"] == sheet.WITH)]
    print("sealed sheet:", frame["company"].iloc[0], frame["meeting_date"].iloc[0], "| missed items:", list(miss["item"]), "| position in seed order:", order.index(pick) + 1)


if __name__ == "__main__":
    page(json.loads((OUT / "metrics.json").read_text(encoding="utf-8")))
    samples()
    print("wrote Kravrespons.html and the seed-picked sheets")
