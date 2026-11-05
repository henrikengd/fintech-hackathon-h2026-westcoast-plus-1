"""Write the one-page requirements response and three review sheets from results/. Needs no API key.

The sheets use a fixed seed over holdout meetings, so nobody picked the examples.
"""
import boot  # noqa: F401
import json
import random

import pandas as pd

import sheet
from run import OUT, SEED


def pct(x, d=1):
    return f"{x * 100:.{d}f}".replace(".", ",") + " %"


def points(x):
    return f"{x * 100:+.1f}".replace(".", ",").replace("-", "−")


def tall(x):
    return f"{x:,}".replace(",", " ")


def resistance_text(m):
    on = [r for r in m["resistance"] if r["defences"] and r["payload"] != "control"]
    changed = sum(r["to_for"] + r["to_avsta"] + r["omitted"] for r in on)
    total = sum(r["items"] for r in on)
    control = next(r for r in m["resistance"] if r["payload"] == "control")
    return (f"Alle {total} plantede instrukser i motstandstesten ble flagget, og ingen nådde samlet signering, mens utkastet endret seg i {changed} tilfeller, på nivå med harmløs tekst ({control['to_for']} av {control['items']}).")


def table(m):
    labels = {"Follow the board": "Følg styret", "Proposal type": "Forslagstype", "Earlier vote at company": "Tidligere stemme i selskapet",
              "Repeat the last vote": "Gjenta forrige stemme", "Text and precedent screen": "Tekstmodell med historikk",
              "Claude, guidelines only": "Claude, bare retningslinjer", "Full system, all sent to a person": "Hele systemet, alt til en person",
              "Full system, Against board lane only": "Hele systemet, bare sporet Mot styret"}
    rows = ""
    for b in m["baselines"]:
        if b["method"] in ("Earlier vote at company", "Claude, guidelines only"):
            continue
        strong = ' class="own"' if b["method"].startswith("Full system") else ""
        rows += (f"<tr{strong}><td>{labels[b['method']]}</td><td>{pct(b['recall'])}</td><td>{pct(b['cleared'])}</td>"
                 f"<td>{pct(b['precision']) if b['precision'] else '–'}</td></tr>")
    return ("<table><thead><tr><th>Metode, samme testperiode</th><th>Fanget av mot styret</th><th>Ikke flagget</th>"
            f"<th>Presisjon på flagg</th></tr></thead><tbody>{rows}</tbody></table>")


def page(m):
    q, p, a, ag, c = m["queue"], m["primary"], m["system"]["literal_mot_draft"], m["agent"], m["policy_chair_ceo"]
    b = m["system"]["literal_mot_follow_board"]
    con = m["confidence_bands"]
    figures = [(pct(m["recall"]), f"av stemmene mot styret når en person (intervall {pct(m['recall_ci'][0], 0)} til {pct(m['recall_ci'][1], 0)})"),
               (pct(m["cleared"]), f"av forslagene går til samlet signering (intervall {pct(m['cleared_ci'][0], 0)} til {pct(m['cleared_ci'][1], 0)})"),
               (pct(q["against_lane_precision"], 0), f"presisjon i sporet Mot styret, mot {pct(q['screen_top_same_size_precision'], 0)} for tekstmodellen med like mange saker"),
               (pct(con["High"]["draft_matches_nbim"]), f"av forslagene med høy konfidens fikk NBIMs stemme ({pct(con['Medium']['draft_matches_nbim'])} middels, {pct(con['Low']['draft_matches_nbim'])} lav)")]
    fig = "".join(f"<div><strong>{v}</strong>{k}</div>" for v, k in figures)
    built = ("Voting Desk er en digital kollega som leser sakslisten til en generalforsamling og foreslår FOR, MOT eller AVSTÅ på hvert forslag, med sitat fra retningslinjen som gjaldt på møtedatoen. "
             "Konfidensen er et tall: hvor ofte samme type utkast traff NBIMs stemme i 2024. Under 95 % og alle forslag mot styret går til en stewardship manager, resten signeres samlet med stikkprøve. "
             "Beslutningen vi støtter er hvilke forslag en person må lese før stemmeintensjonen publiseres. "
             f"I testperioden fikk alle {tall(m['coverage']['proposals'])} forslag en stemme og en konfidens, og en person vurderte {pct(m['review_share']['individual'])} enkeltvis ({pct(m['review_share']['with_audit'])} med stikkprøven).")
    verified = (f"Fasit er NBIMs publiserte stemmer, og målvariabelen er om NBIM stemte annerledes enn styret, fordi FOR på et aksjonærforslag også kan gå mot styret. "
                f"Vi justerte på 2023, satte terskelen på 2024, låste metoden og kjørte testperioden 2025–2026 én gang ({tall(m['scored'])} forslag, {m['against']} mot styret). "
                f"Vi måler presisjon og recall, ikke accuracy, fordi å alltid følge styret gir {pct(m['accuracy']['follow_board'])} accuracy og fanger ingen. "
                f"Systemet fanget {pct(m['recall'])}, og {pct(p['difference'])[:-2]} prosentpoeng flere forslag gikk til samlet signering enn med tekstmodellen ved samme fangst (intervall {points(p['ci'][0])} til {points(p['ci'][1])}). "
                f"På MOT-stemmer er presisjon {pct(a['precision'], 0)} og recall {pct(a['recall'], 0)}, mot {pct(b['precision'], 0)} og {pct(b['recall'], 0)} for å følge styret.")
    need = (f"De fleste stemmene mot styret avhenger av fakta som ikke står på stemmeseddelen. "
            f"En agent som søkte i innkallingen på {ag['meetings']} amerikanske møter ga mer konkrete grunner, men fanget ikke flere. "
            "Vi trenger dokumenter utenfor USA, posisjonsstørrelse og NBIMs selskapsspesifikke grunner. "
            "Neste steg er prøvedrift side om side med analytikere.")
    policy = (f"NBIM mildnet regelen om å kombinere styreleder og konsernsjef rundt mars 2026. Der utkastet siterte regelen, stemte NBIM mot styret i "
              f"{c['before']['against']} av {c['before']['n']} saker før endringen og {c['after']['against']} av {c['after']['n']} etter. Utvalget er lite, men historikk må vektes ned når en retningslinje endres.")
    limits = (f"{resistance_text(m)} "
              f"Testperioden er ikke helt blind, og rapporteringskoden ble rettet etter låsing. "
              f"Bare {pct(m['citation_coverage'], 0)} av forslagene siterer en regel som avgjør saken, de øvrige siterer utgangspunktet om å støtte styret. "
              f"Utvalget er {m['companies']} selskaper, og et kontrollert sitat viser at regelen finnes, ikke at den gjelder.")
    css = sheet.CSS + """
@page{size:A4;margin:0}
body{font-size:12.5px;line-height:17px}
.wrap{max-width:none;padding:0 28px}.band{padding:5px 28px;font-size:11px}
header{padding:12px 0 8px}h1{font-size:24px;line-height:30px;margin:0 0 2px}
h2{font-size:14.5px;line-height:19px;margin:9px 0 2px}p{margin:0}
.figures{margin:8px 0 2px;gap:14px}.figures div{font-size:11.5px;line-height:15px}.figures strong{font-size:24px;line-height:30px}
th{padding:5px 8px;font-size:12.5px}td{padding:4px 8px;font-size:12.5px}tr.own td{background:var(--sand);font-weight:500}
.limits{font-size:12px;line-height:16px;margin-top:8px}"""
    body = f"""<header><div class=wrap><h1>Voting Desk</h1><p>Kravrespons, case 1 Stemmegivningsagenten. Westcoast + 1, FinTech Hackathon H2026.</p></div></header>
<main class=wrap><div class=figures>{fig}</div>
<h2>Hva vi bygde</h2><p>{built}</p>
<h2>Hvordan vi verifiserte det</h2><p>{verified}</p>
<div style="margin-top:6px">{table(m)}</div>
<h2>Retningslinje mot praksis</h2><p>{policy}</p>
<h2>Hva vi ville trengt videre</h2><p>{need}</p>
<h2>Motstandstest og begrensninger</h2><p>{limits}</p></main>"""
    html = sheet.page("Voting Desk, kravrespons", body).replace(sheet.CSS, css).replace('lang="en"', 'lang="no"').replace(sheet.BAND, "Studentprototype, Westcoast + 1, FinTech Hackathon H2026. Ikke et NBIM-produkt.")
    (OUT / "kravrespons.html").write_text(html, encoding="utf-8")


def samples():
    test = pd.read_csv(OUT / "items_test.csv", dtype={"item": str, "meeting_id": str})
    ids = sorted(test["meeting_id"].unique())
    random.Random(SEED).shuffle(ids)
    folder = OUT / "sheets"
    folder.mkdir(exist_ok=True)
    for mid in ids[:3]:
        frame = test[test["meeting_id"] == mid]
        name = "".join(c if c.isalnum() else "_" for c in frame["company"].iloc[0]).strip("_")
        (folder / f"holdout_{name}.html").write_text(sheet.review_sheet(frame), encoding="utf-8")


if __name__ == "__main__":
    page(json.loads((OUT / "metrics.json").read_text(encoding="utf-8")))
    samples()
    print("wrote results/kravrespons.html and three holdout sheets")
