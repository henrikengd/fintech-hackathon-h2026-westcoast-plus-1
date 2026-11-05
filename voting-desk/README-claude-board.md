# Claude med lokalt søk i historiske stemmer

Det aktive modellvalget [maksimerer nå F1 for avvik fra styret](README-f1.md). Claude-svarene dokumentert her gjenbrukes uendret i sammenligningen. De gir ikke en numerisk skår som kan få en ny terskel.

Dette forsøket sammenligner Claude med den [lokale avviksmodellen](README-board.md) på de samme 1883 sakene fra 168 møter i 2024. Målet er å finne når NBIM stemmer annerledes enn styret anbefaler. Det er en utviklingsmåling på tidligere brukte data, ikke en ny uavhengig test. Ingen stemmeutfall fra 2025–2026 brukes i forsøket.

## Resultat fra kjøringen 5. november 2026

| Oppsett, samme 1883 saker | Precision for avvik | Recall for avvik | F1 | Riktige avvik | Falske alarmer | Oversette avvik |
|---|---:|---:|---:|---:|---:|---:|
| Claude Sonnet 5.5 med historiske vektortreff | 60,2 % | 54,1 % | 57,0 % | 53 | 35 | 45 |
| Lokal modell, terskel fra tidligere validering | 59,6 % | 60,2 % | 59,9 % | 59 | 40 | 39 |
| Lokal modell, terskel valgt på 2024 | 63,4 % | 60,2 % | 61,8 % | 59 | 34 | 39 |

Claude ble forsøkt på alle 168 møter. 163 ga validerte svar, fire svar ble underkjent av svarvalideringen, og ett kall feilet med en forbindelsesfeil. Disse feilene er beholdt; ingen kall ble gjentatt for å forbedre resultatet. De fem møtene omfatter 53 saker, inkludert 13 faktiske avvik. Claude ga gyldig stemmeprediksjon for 1830 av 1883 saker, altså 97,2 prosent dekning. Uavhengig opptelling fra de lagrede enkeltresultatene bekrefter rapportens riktige og gale prediksjoner.

Som en sekundær feilanalyse gir de 1830 sakene med godkjente Claude-svar 60,2 prosent precision og 62,4 prosent recall. På nøyaktig disse sakene har den lokale modellen med 2024-terskelen 62,5 prosent precision og 58,8 prosent recall. Dette utvalget er valgt etter at svarene forelå og erstatter ikke hovedmålingen. Det viser at håndtering av ugyldige svar bidrar til forskjellen i systemenes samlede recall. Feilregistrene skiller ikke mellom alle mulige årsaker til underkjent svar, så årsaken til hver valideringsfeil er ikke fastslått.

For det separate målet **MOT på forslaget** fikk Claude 61,7 prosent precision og 51,0 prosent recall: 50 riktige MOT, 31 falske MOT og 48 oversette MOT. Den lokale binære avviksmodellen har ingen direkte MOT-prediksjon.

Registrert tokenbruk var 3 546 885 inputtokens og 129 791 outputtokens. Beregnet kostnad er 8,39 USD med det oppgitte prisgrunnlaget. Kall uten returnert tokenbruk kan medføre kostnader utover dette anslaget.

Denne Claude-varianten ga lavere F1 enn den lokale modellen på samme 2024-utvalg. Resultatet sier ikke hva Claude ville oppnådd med bedre dokumentgrunnlag, flere historiske trekk eller et annet oppsett. Prompten ble ikke endret under denne kjøringen. Ingen av resultatene er en uavhengig sluttest.

## Hva som kjører hvor

Den ferdigtrente BGE-modellen lager tekstvektorer lokalt. Det lokale søket finner tidligere lignende forslag ved cosinuslikhet. For hvert nytt forslag hentes inntil åtte treff fra hele historikken og åtte fra samme selskap. Treff som finnes i begge listene tas med én gang. Valget bruker tekstlikhet, selskap og dato, ikke utfallet av den historiske stemmen.

Claude får tekst, styrets anbefaling, dato og NBIMs tidligere stemme for disse treffene. Rå vektorkoordinater sendes ikke. Det er programmet som utfører søket og sender et avgrenset grunnlag til Anthropic; Claude får ingen direkte databaseforbindelse eller generell filtilgang.

Historikkregelen er den samme som for den lokale modellen:

```text
historisk møtedato < aktuell møtedato − 5 dager
historisk møte != aktuelt møte
```

Tidligere møter fra 2024 kan inngå som historikk for senere møter fra 2024. Fasiten for det aktuelle møtet og senere møter er utelatt. Utfallet fra Claude føres ikke tilbake som historisk fasit. Møtedato med fem dagers margin er en tilnærming; eksakte publiseringstidspunkter for alle historiske stemmer er ikke dokumentert.

## Hva som sammenlignes

Den lokale modellen er trent på 2019–2023. Den bruker 384 tekstvektordimensjoner og 59 historikk-/metadataegenskaper. Claude er en ferdigtrent ekstern språkmodell som får historiske eksempler i konteksten; vi trener ikke Claude på disse dataene.

Claude gir en predikert FOR-, MOT- eller AVSTÅ-stemme, eller `null` når den ikke kan predikere. Avvik beregnes deretter som predikert stemme ulik styrets anbefaling. En manglende prediksjon regnes ikke som enighet med styret. Dersom NBIM faktisk avvek, blir en manglende prediksjon en falsk negativ.

Vi rapporterer:

- Avvik: precision, recall, F1, riktige avvik, falske alarmer og oversette avvik.
- MOT: separat precision og recall for den faktiske predikerte stemmeretningen.
- Dekning: andel saker med gyldig prediksjon, samt feilede og ufullførte kall.
- API-bruk: registrerte input-/outputtokens og et prisanslag, ikke en faktura.

Lokale sammenligningstall beregnes på nøyaktig de samme sakene som er forsøkt vurdert av Claude, også ved delvis kjøring. Feilede kall beholdes i nevnerne. Både den lokale terskelen fra tidligere validering og terskelen som ble valgt på 2024 vises. Sistnevnte har vært tilpasset 2024-fasiten. Claude-prompten låses før kjøringen. Dette er samme evalueringsutvalg og tidsgrenser, men ikke identiske læringsmetoder eller inputrepresentasjoner.

## Avgrensning mot dokument-RAG

Dette forsøket gir Claude historiske stemmeeksempler. Det gir ikke innkallinger eller retningslinjer. Henvisning til en tidligere stemme forklarer en analogi, men dokumenterer ikke at en stemmeanbefaling følger en regel. Alle resultater er prediksjoner til vurdering, ikke faktiske stemmehandlinger.

Den eksisterende `rag_review.py`-koblingen gir allerede Claude dokumentutdrag fra det lokale SQLite-søket. Det tidligere dokumentforsøket dekker bare 22 møter i et annet utvalg. Tallene kan derfor ikke sammenlignes direkte med denne målingen på 1883 saker. Et senere forsøk med både historikk og dokumenter må sammenligne alle modellene på samme dokumentdekkede utvalg.

Både Claude og BGE er forhåndstrente. Vi kan tidsavgrense opplysningene programmet henter frem, men ikke dokumentere at modellene aldri har sett opplysninger fra senere år under sin opprinnelige trening.

## Kjøring og etterprøving

Fra `voting-desk/`:

```bash
# Lokalt: lag alle kontekster og lås oppsettet før API-kall.
.venv/bin/python claude_board_experiment.py prepare

# Betalt: ett kall per møte, inntil fire parallelle kall.
.venv/bin/python claude_board_experiment.py run

# Lokalt: beregn rapporten fra allerede lagrede svar.
.venv/bin/python claude_board_experiment.py report
```

`--limit 1` kan brukes for å kontrollere ett møte først. En senere full kjøring gjenbruker det lagrede svaret. `--output` velger en egen mappe for et nytt forsøk. Tidligere kontekster, svar og oppsett overskrives ikke. SDK-en gjør ingen automatiske omkjøringer. Et avbrutt kall uten lagret svar må undersøkes før det forsøkes igjen.

Under `data/local-rag/claude-board-v1/` lagres:

- `plan.json`: utvalg, modell, prompt, skjema, kildehasher og tidsregler.
- `bundles/`: nøyaktig grunnlag for hvert møte, uten aktuell fasit.
- `evaluation-labels.csv`: separat fasit og lokale modellskårer; sendes ikke til Claude.
- `requests/` og `responses/`: forespørselsmarkører, validerte svar, feilstatus og tokenbruk.
- `source/`: koden som ble låst før kjøringen.
- `report.json` og `predictions.json`: sammenligning og enkeltresultater.

Rapporten vises på [resultatsiden](http://127.0.0.1:8502/evaluation). Siden leser lagrede data og starter ingen API-kall. Den opprinnelige avviksmodellen og eldre holdout-resultater er bevart.

API-formatet følger [Anthropics dokumentasjon for strukturerte svar](https://platform.claude.com/docs/en/build-with-claude/structured-outputs). Prisgrunnlaget for den konfigurerte Sonnet 5.5-modellen er [Anthropics publiserte priser](https://www.anthropic.com/claude-sonnet-5-5), kontrollert 5. november 2026. Feil uten returnert tokenbruk kan gi kostnader som ikke inngår i anslaget.
