# Modellvalg etter F1

Det aktive kriteriet er nå å maksimere **F1 for avvik fra styrets anbefaling**. Kravet om både precision og recall over 85 prosent er tatt ut av modellvalget. Precision og recall vises fortsatt, slik at vi ser hva en endring i F1 innebærer.

Positiv klasse er fortsatt kjent NBIM-stemme ulik kjent styreanbefaling. Vi bruker binær F1 for denne klassen, ikke accuracy, mikro-F1 eller et gjennomsnitt dominert av enighet med styret.

```text
F1 = 2 × riktige avvik / (2 × riktige avvik + falske alarmer + oversette avvik)
```

F1 kombinerer precision og recall. Korrekt enighet med styret gir ikke i seg selv høy F1 for avvik. Valget følger definisjonen i [scikit-learns dokumentasjon](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.f1_score.html).

## Hva som er endret

Vi vurderer de tolv tidligere lokale modellvariantene på nytt med F1 som hovedkriterium. Variantene omfatter logistisk regresjon, gradient boosting og ekstra tilfeldige trær, med historikkegenskaper, TF-IDF og BGE-tekstvektorer. De lagrede valideringsprediksjonene dekker samme 6546 saker fra 2020–2023, med 380 faktiske avvik. Hver prediksjon ble laget av en modell trent på tidligere år.

For hver variant finner vi terskelen med høyest F1 på dette valideringsgrunnlaget. Deretter velges modellen med høyest F1. Ingen minimumsgrenser for precision eller recall brukes. Den valgte modellen er fremdeles `semantic-history-boost`. Derfor gjenbrukes de eksisterende modellvektene uendret. Dette er et nytt modellvalg og terskelvalg, ikke ny trening av vinneren.

Modellen er trent på 2019–2023. Modellvalget skjer på den tidsordnede valideringen fra 2020–2023. Etter at modellen er valgt, velges en egen F1-terskel på 2024. Dette holder modellvalget og den siste terskeltilpasningen atskilt. Terskelvalget følger prinsippet om å bruke separate data fra modelltreningen, beskrevet i [scikit-learns terskelveiledning](https://scikit-learn.org/stable/modules/classification_threshold.html).

| Beslutning | Tidligere kriterium | Nytt kriterium |
|---|---|---|
| Modellvalg | Maksimer den laveste av precision og recall | Maksimer F1 |
| Lokal modell | `semantic-history-boost` | Samme modell |
| Terskel valgt på 2020–2023 | 0,20576439117132628 | 0,27660363779726793 |
| Terskel tilpasset 2024 | 0,22539900622680564 | 0,24417457727599695 |
| Oktober-testen | Låst tidligere oppsett | Beholdes som tidligere test, brukes ikke i valget |

## Sammenligning på 2024

Alle radene under gjelder de samme 1883 sakene og 98 faktiske avvik. Dette er tidligere eksponerte utviklingsdata. Rader med terskel valgt på 2024 er tilpasset de samme utfallene som de måles mot.

| Oppsett | F1 | Precision | Recall | Riktige avvik | Falske alarmer | Oversette avvik |
|---|---:|---:|---:|---:|---:|---:|
| Lokal modell, F1-terskel fra 2024 | 62,3 % | 67,1 % | 58,2 % | 57 | 28 | 41 |
| Lokal modell, F1-terskel fra 2020–2023 | 62,1 % | 69,6 % | 56,1 % | 55 | 24 | 43 |
| Lokal modell, tidligere balansert terskel fra 2024 | 61,8 % | 63,4 % | 60,2 % | 59 | 34 | 39 |
| Claude med historiske vektortreff, lagrede svar | 57,0 % | 60,2 % | 54,1 % | 53 | 35 | 45 |
| Følg alltid styret | 0,0 % | Ikke definert | 0,0 % | 0 | 0 | 98 |

Den nye tilpassede F1-terskelen gir seks færre falske alarmer og to flere oversette avvik enn den gamle tilpassede terskelen. F1 øker med omtrent **0,52 prosentpoeng**. Det er en liten forbedring på kalibreringsgrunnlaget, ikke dokumentasjon på bedre ytelse på nye møter.

Claude gir en stemmeretning eller et nullsvar, ikke en numerisk avviksskår som kan få en ny terskel. Vi beregner F1 fra de lagrede svarene og lar dem inngå som sammenligning. Claude-prompten og vektene er ikke optimalisert på nytt i dette arbeidet. De fem tidligere feilede møtene beholdes i målingen. Endringen krever ingen nye API-kall.

De eldre rene vektor-, tekst- og dokument-RAG-forsøkene målte hovedsakelig MOT på andre saksutvalg. De beholdes som historiske forsøk og rangeres ikke direkte mot avviksmodellene. Høy F1 for MOT på 1505 saker kan ikke overføres til F1 for avvik på 1883 saker.

## Hvorfor oktober-resultatet var svakt

Den [låste oktober-testen](README-fresh-test.md) består av 36 forslag, hvorav 33 kan måles mot styret. Begge modeller overså tre avvik og laget to falske alarmer. Testen gir F1 på null for det opprinnelige oppsettet. Den nye F1-terskelen er ikke evaluert på oktober, og vi erstatter ikke den lagrede testscoren.

Feilanalysen viser at en terskelendring alene ikke løser disse feilene. Alle tre oversette avvik hadde lavere lokal modellskår enn begge de falske alarmene. Historikken inneholdt heller ikke alle de konkrete situasjonene i de nye forslagene. Hos PT Solusi endret NBIM stemme mellom to møter med identisk kort sakstekst. Modellenes input beskriver dermed ikke nødvendigvis forholdet som avgjør stemmen.

Se [den detaljerte analysen av oktober-testen](analysis-october-test.md) for forslagene, de faktiske historiske treffene og skillet mellom dokumenterte funn og mulige forklaringer. Analysen bruker testutfallene til å forstå svakheter. Den bruker dem ikke til å velge den nye modellen eller terskelen.

Videre utvikling bør sammenligne historikk alene med historikk kombinert med innkalling, full forslagstekst og relevante retningslinjer på utviklingsdata. NBIMs begrunnelse for den aktuelle stemmen er fasitnær informasjon og skal ikke brukes som input. Eventuelle nye varianter trenger en ny urørt testperiode. Målkriteriet ble endret etter at oktoberresultatet var kjent, selv om oktoberverdiene ikke inngår i beregningen av ny modell eller terskel. Oktober skal derfor ikke presenteres som en ny uavhengig test ved senere omkjøringer.

## Kjøring og kontroll

Fra `voting-desk/`:

```bash
.venv/bin/python f1_experiment.py run
.venv/bin/python f1_experiment.py predict --meeting 1832444 --item 6
.venv/bin/python -m unittest test_f1_experiment test_f1_results -v
```

Det nye oppsettet lagres under `data/local-rag/f1-board-v1/`. Tidligere kjøringer og den frosne oktober-testen beholdes. Rapporten dokumenterer kildehasher, kandidatene, valgt modell og tersklene. Resultatene vises først på [resultatsiden](http://127.0.0.1:8502/evaluation). Siden leser lagrede rapporter og starter ingen modellkall.

259 programtester bestod etter endringen. En uavhengig beregning bekreftet F1-terskelen og forvekslingsmatrisen. En faktisk gjenspilling av møte 1841869, sak 1, ga skår 0,2281254891 og skiftet fra avviksflagg til enighet med styret ved den nye terskelen. Alle åtte endrede 2024-prediksjoner følger terskelendringen. Frontend er kontrollert i nettleseren. Modellfilen er byte-identisk med den tidligere modellen, og alle 17 kildefiler fra den låste oktober-testen har beholdt kontrollsummene sine.
