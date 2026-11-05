# Tidligere balansert modellvalg for avvik fra styret

Det aktive kriteriet er nå [maksimal F1 for avvik fra styret](README-f1.md). Denne siden dokumenterer det tidligere oppsettet, som prioriterte den laveste av precision og recall. Det bruker hele den tidligere perioden, ikke den blandede 80/20-delingen. Modellvalget skjer på 2019–2023, og beslutningsterskelen settes på 2024. Data, modellvekter og resultater fra denne kjøringen er bevart.

Det tidligere oppsettet gir **63,4 prosent precision, 60,2 prosent recall og 61,8 prosent F1 på terskelkalibreringen i 2024**. Dette er ikke en ny testscore. Kravet om begge mål over 85 prosent er avviklet. [Resultatsiden](http://127.0.0.1:8502/evaluation) viser det nye F1-oppsettet først og bevarer dette forsøket som historikk.

En separat [Claude-sammenligning](README-claude-board.md) bruker lokalt hentede historiske stemmer og samme 2024-utvalg. Den lokale modellen og resultatene nedenfor er bevart.

## Måldefinisjon

Positiv klasse er `nbim_vote != mgmt_rec`, forutsatt at begge stemmene er kjent. Manglende styreanbefaling eller NBIM-stemme gir ingen målverdi og er utelatt fra læring og evaluering.

| Styret anbefaler | NBIM stemmer | Avvik fra styret | NBIM stemmer MOT |
|---|---|---|---|
| FOR | MOT | Ja | Ja |
| MOT | FOR | Ja | Nei |
| MOT | MOT | Nei | Ja |
| FOR | FOR | Nei | Nei |
| FOR | AVSTÅ | Ja | Nei |
| Ukjent | MOT | Kan ikke avgjøres | Ja |

Precision er andelen av modellens flaggede avvik som faktisk er avvik. Recall er andelen av NBIMs faktiske avvik modellen finner. «Følg alltid styret» flagger ingen avvik: recall er null, og precision er udefinert.

Denne binære modellen velger ikke en av FOR, MOT og AVSTÅ. Et avviksflagg skal derfor ikke automatisk gjøres om til motsatt stemme av styret. Oppgaveteksten krever også precision/recall på MOT-stemmer; den målingen beholdes separat for modeller som gir en faktisk stemmeretning. Den nye modellens MOT-precision/recall er ikke definert.

## Datadeling

| Del | Rådata | Med kjent NBIM-stemme og styreanbefaling | Faktiske avvik | Bruk |
|---|---:|---:|---:|---|
| 2019–2023 | 8267 | 7993 | 477 | Læring og intern modellvalidering |
| 2024 | 1942 | 1883 | 98 | Valg av beslutningsterskel |
| 2025–2026 | 3548 | Ikke analysert på nytt | Ikke analysert på nytt | Tidligere kjørt testperiode; ingen ny kjøring |

10 209 av 13 757 rader ligger før 2025, altså omtrent 74 prosent. Resten utgjør omtrent 26 prosent. Dette er utviklingsperiode mot testperiode, ikke en tilfeldig 74/26-deling. 2024 er fortsatt skilt ut fra modelltreningen.

Selskap/møtedato-grupper og alle forslag fra samme møte følger datoen samlet. Samme selskap kan finnes i flere år og på begge sider av tidsgrensen. Det er forventet når formålet er å vurdere senere møter i selskaper vi allerede kjenner; dette er ikke en ren test av ukjente selskaper.

`board_experiment.load_temporal` kontrollerer kildehashen, datoene og saksidentitetene. Rader fra 2025–2026 brukes bare til å telle identiteter og omfang; deres stemmefelt brukes ikke. Fra treningsperioden utelates 210 rader uten NBIM-stemme og 64 med kjent NBIM-stemme, men ukjent styreanbefaling. Tilsvarende tall for 2024 er 45 og 14.

Den tidligere 80/20-delingen og alle resultater fra den er bevart. Den er **ikke aktiv i dette forsøket**. Tidligere reserverte blandede rader fra 2019–2024 inngår nå etter de nye tidsgrensene. Derfor skal ikke de gamle tallene på 1505 saker sammenlignes direkte med de nye tallene på 1883 saker, selv før forskjellen i måldefinisjon tas med.

## Låste modellvekter, oppdatert historikk

Tolv forhåndsbestemte lokale modellvarianter sammenlignes med validering fremover i tid. For validering i 2020 trenes modellen på 2019; for 2021 på 2019–2020; deretter tilsvarende for 2022 og 2023. Hele møter holdes samlet. Modell og intern terskel velges etter høyest verdi av den svakeste av precision og recall, med F1 og så precision som kriterier ved likhet.

Innen hvert valideringsår er modellvektene faste. Historikken kan vokse når tidligere møter blir tilgjengelige. Samme prinsipp brukes i 2024: modellen trenes én gang på 2019–2023, men en senere sak i 2024 kan bruke stemmer fra tidligere møter i 2024.

Hvert historisk bidrag må oppfylle:

```text
historisk møtedato < aktuell møtedato − 5 dager
historisk møte != aktuelt møte
```

Aktuell NBIM-stemme, senere møter og andre forslag fra eget møte brukes ikke til å beregne sakens egenskaper. Tidligere stemmer inngår som opplysninger, ikke som oppdatering av modellvektene. Møtedatoene brukes som tilnærming til informasjonstilgjengelighet; datagrunnlaget dokumenterer ikke det nøyaktige publiseringstidspunktet for alle stemmer.

Den valgte modellen er `semantic-history-boost`: gradient boosting med 59 historikk-/metadataegenskaper og 384 tekstvektordimensjoner fra den lokalt lagrede BGE-modellen. Historiske aggregater måler nå avvik fra styret. Faktiske NBIM-stemmer blir ikke omskrevet til syntetiske MOT/FOR-etiketter. Modelltilstand og egenskapsnavn lagrer hvilket mål de gjelder.

Etter at modellen er valgt og trent, scores 2024. De kjente 2024-utfallene brukes deretter til å velge beslutningsterskel. Terskelvalg er ikke kalibrering av sannsynligheter: skåren er fortsatt ikke et validert mål på sikkerhet. Den valgte terskelen er 0,22539900622680564. Før kalibreringen var terskelen fra 2020–2023-valideringen 0,20576439117132628.

## Målte resultater

| Måling | Saker | Avvik | Precision | Recall | F1 | Riktige avvik | Falske avvik | Oversette avvik |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020–2023, validering brukt til modellvalg | 6546 | 380 | 50,5 % | 50,5 % | 50,5 % | 192 | 188 | 188 |
| 2024, terskel låst fra tidligere validering | 1883 | 98 | 59,6 % | 60,2 % | 59,9 % | 59 | 40 | 39 |
| 2024, terskel valgt på 2024 | 1883 | 98 | 63,4 % | 60,2 % | 61,8 % | 59 | 34 | 39 |
| Tidligere agent, lagrede stemmer på samme 2024-saker | 1883 | 98 | 43,4 % | 46,9 % | 45,1 % | 46 | 60 | 52 |

Valideringsraden er brukt til modellvalg. 2024 er tidligere eksponerte utviklingsdata, og den kalibrerte raden er tilpasset de samme utfallene den måles på. Ingen av radene er en ny uavhengig sluttest. Den tidligere agenten har et annet oppsett og brukes som historisk referanse, ikke som en kontrollert ny sammenligning av modellarkitektur.

Av de 98 avvikene i 2024 er 88 styret FOR/NBIM MOT, ni styret MOT/NBIM FOR og ett styret FOR/NBIM AVSTÅ. Med den kalibrerte terskelen finner modellen henholdsvis 50, åtte og ett. Det finnes også ti saker der både styret og NBIM stemmer MOT; disse er ikke avvik. At antallet MOT og antallet avvik begge er 98 i dette utvalget er en tilfeldighet, ikke samme måldefinisjon.

Andre terskler viser avveiningen, men er også valgt på 2024:

| Terskelvalg | Precision | Recall |
|---|---:|---:|
| Balanse mellom begge | 63,4 % | 60,2 % |
| Presisjon over 85 prosent | 85,5 % | 48,0 % |
| Recall over 85 prosent | 18,8 % | 85,7 % |

## Hva vi kan si til juryen

For oppsettet er denne beskrivelsen presis:

> Tidsdelt evaluering med faste modellvekter innen hver evalueringsperiode. Modellen trenes på 2019–2023, og beslutningsterskelen settes på 2024. Historikken oppdateres med tidligere møter under en fast femdagersgrense. Avvik fra styrets anbefaling og MOT-stemmer rapporteres som forskjellige mål.

For **den nye lokale modellen** må det tilføyes at 2025–2026 ikke er evaluert på nytt. Den har foreløpig validerings- og kalibreringsresultater, ikke en ny testscore. Den tidligere modellens holdout-resultater kan ikke overføres til den nye.

En låst modell er enklere å kontrollere, men er ikke garantert å prestere dårligere enn en modell som trenes på nytt. Vi har ikke et kontrollert forsøk som dokumenterer forskjellen. Jevnlig ny trening og terskelvalg må også skje på data tilgjengelig før den aktuelle evalueringsperioden.

Påstanden om at alle historiske møter bruker dokumentert riktig regelversjon er heller ikke fullt verifisert. Den gamle agenten filtrerer regler etter møtedato, men bare seks av 79 regelposter har datogrenser; udaterte regler behandles som tilgjengelige historisk. Den nye lokale klassifikatoren bruker ikke regeltekster. Den kan derfor verken dokumentere regelversjon eller gi retningslinjesitater som begrunnelse for et avviksflagg.

Tallrekken 86/71/98 fra et mulig eldre forarbeid er ikke gjenfunnet i de kontrollerte nåværende resultatfilene og brukes ikke som resultat for dette forsøket. Den må kobles til riktig kjøring, terskel og nevner før den presenteres.

## Kjøring og sporbarhet

```bash
# Kjør fra voting-desk/. Alt skjer lokalt, uten Claude/API:
.venv/bin/python board_experiment.py run --output data/local-rag/board-disagreement-next

# Last den lagrede modellen og gjenskap én 2024-vurdering:
.venv/bin/python board_experiment.py predict --meeting 1832444 --item 6

.venv/bin/python -m unittest test_vote_targets test_board_experiment test_board_results -v
```

Resultatene ligger i `data/local-rag/board-disagreement-v1/`: `plan.json` før modellvalget, `selection.json` før 2024-scoring, `calibration.json` med terskelvalget, CSV-er med validering og kalibrering, og `summary.json` med måldefinisjon, datagrenser og hasher. `source/` bevarer koden brukt i kjøringen. `learner.joblib` er den lokale modellen. `reference/` inneholder 2019–2023-historikken, mens lagrede 2024-egenskaper muliggjør nøyaktig gjenspilling. Nye fremtidige vurderinger må få eksplisitt historikk tilgjengelig på det aktuelle tidspunktet.

Ingen nye avhengigheter eller eksterne modellkall er lagt til. Eksisterende resultater, blandede partisjoner, frossen `desk.py` og `rules.json` er bevart. Implementasjon, tester og rapport er laget med Codex-assistanse.

Metodisk støtte: scikit-learn om [tidsordnet validering](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) og [adskilt valg av beslutningsterskel](https://scikit-learn.org/stable/modules/classification_threshold.html). Oppgavens egne krav finnes i startpakkens README under «Krav til leveransen» og «Fallgruver».
