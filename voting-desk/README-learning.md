# Tidligere lokal MOT-modell

Dette er det tidligere forsøket på **MOT versus ikke-MOT** innen den blandede 80/20-delingen. Det aktive forsøket [maksimerer F1 for NBIM ulikt styrets anbefaling](README-f1.md) med en ren tidsdeling. Resultatene under er bevart og skal ikke omtolkes til avvik fra styret. Målet om både precision og recall over 85 prosent gjaldt denne tidligere kjøringen og er ikke lenger aktivt.

**Det daværende målet ble ikke nådd.** Modellen ga 63,0 prosent MOT-presisjon og 37,7 prosent MOT-recall på 1505 utviklingssaker fra 2024. Den bruker vektorsøk og lærer mønstre i tidligere stemmer, uten Claude eller andre modell-API-kall. Resultatene vises som historikk på [resultatsiden](http://127.0.0.1:8502/evaluation).

Dette arbeidet tester om mer læring fra dagens forslagstekster og stemmehistorikk kan løse problemet. Ingen av de 12 prøvde modellvariantene oppnår begge målene i valideringen. Det er ikke bevis for at 85/85 er umulig, men vi har ikke grunnlag for å love det med disse opplysningene.

## Resultater på samme saker

Alle radene gjelder 1505 saker, hvor NBIM stemte MOT i 77. 2024 er tidligere eksponerte utviklingsdata, ikke en uavhengig sluttest.

| Oppsett | Precision | Recall | F1 | Riktige MOT | Feilaktige MOT | Oversette MOT |
|---|---:|---:|---:|---:|---:|---:|
| Ny lært modell, v2 | 63,0 % | 37,7 % | 47,2 % | 29 | 17 | 48 |
| Ren vektormodell, tidligere | 11,1 % | 89,6 % | 19,7 % | 69 | 553 | 8 |
| Lokal tekstmodell, tidligere | 38,1 % | 41,6 % | 39,8 % | 32 | 52 | 45 |
| Tidligere Claude-modell, lagrede svar | 49,3 % | 44,2 % | 46,6 % | 34 | 35 | 43 |
| Følg styrets anbefaling | 41,7 % | 6,5 % | 11,2 % | 5 | 7 | 72 |

Den nye modellen har høyere presisjon og F1 enn den rene vektormodellen, men betydelig lavere recall. Ulike terskler og utvalgskriterier gjør at tabellen ikke alene dokumenterer at én metode er bedre. Claude-svarene brukte dessuten andre prompter og mer historikk. Ingen av de lagrede oppsettene når begge målene.

V2s balanserte terskel er 0,9597931749175228. En annen terskel, valgt på tidligere års validering for recall over 85 prosent, gir 98,7 prosent recall og 7,3 prosent presisjon i 2024. Terskelen valgt for presisjon over 85 prosent gir ingen MOT i 2024: presisjon er udefinert og recall er null. Dette viser at terskler fra validering ikke garanterer samme ytelse i et senere år. Skårene er ikke kalibrerte sannsynligheter.

## Hva som er gjennomført

- `vote_features.py` beregner 59 egenskaper: selskapets stemmehistorikk, samme person og forslag tidligere, tekstbaserte sakstyper, historikkens alder, samt globale og selskapsspesifikke vektortreff. Styrets anbefaling og forslagsstiller er også med.
- `vote_learner.py` sammenligner logistisk regresjon, gradient boosting og ekstra tilfeldige trær, med egne varianter som også bruker TF-IDF eller de 384 BGE-dimensjonene direkte. De 12 variantene er fastsatt før kjøring. Tellinger og alder har faste øvre grenser for å redusere ekstrapolering når historikken vokser.
- `vote_experiment.py` velger modell og terskel etter høyest verdi av den svakeste av precision og recall. F1 og deretter precision avgjør likhet. Den skriver forsøksplan og arkiverer kildekoden før validering, og låser modellvalget før utviklingsåret scores.
- `vote_diagnostics.py` lager feiloversikt, dokumentdekning og oppgaver for kildekontroll. Den endrer ikke modellen eller terskelen.
- Nettsiden viser det felles 85/85-målet, målingene og de tre forhåndsvalgte tersklene. Et avrundet tall på 85,0 prosent regnes ikke automatisk som måloppnåelse.

Alle historiske stemmer må ligge i tillatt referanseutvalg og være datert mer enn fem dager før saken. Eget møte er utelukket. Forslagets fasit, begrunnelser og fasitavledede kategorier brukes ikke som egenskaper. Å sende en sak til menneskelig kontroll regnes ikke som en korrekt MOT-prediksjon.

## Valideringsoppsett og oppstartsår

Det første forsøket, `vote-learning-v1`, trente også på 2019 og validerte 2020–2023. Det valgte logistisk regresjon og fikk 37,0 prosent presisjon og 36,8 prosent recall i samlet validering. Den låste terskelen ga 69,6 prosent presisjon og 20,8 prosent recall i 2024. Dette forsøket er bevart.

En kontroll av bare valideringsprediksjonene viste store forskjeller i skårenes nivå mellom år. Det første treningsåret hadde særlig lite tidligere historikk å lære sammenhengene fra. V2 bruker derfor 2019 som referansehistorikk, mens klassifikatoren trenes fra 2020. Tellinger begrenses til 50 og alder til tre år før skalering. Dette er et nytt, eksplorativt oppsett, ikke en uavhengig bekreftelse av v1.

For v2 trenes og valideres modellen fremover i tid:

| Valideringsår | Læringsår | Referansehistorikk | Precision | Recall |
|---|---|---|---:|---:|
| 2021 | 2020 | 2019–2020 | 48,1 % | 30,2 % |
| 2022 | 2020–2021 | 2019–2021 | 43,8 % | 40,2 % |
| 2023 | 2020–2022 | 2019–2022 | 39,3 % | 50,7 % |
| Samlet | — | — | 42,3 % | 41,7 % |

Valideringen har 4128 saker og 199 MOT. Tallene brukes til modellvalg og er dermed ikke en objektiv sluttest. Den ferdige v2-klassifikatoren lærer fra 5333 saker fra 2020–2023 og kan hente historiske referanser fra 6470 saker fra 2019–2023. Valgt modell er logistisk regresjon med `C=0.1` og balanserte klassevekter.

Alle nye lærings- og utviklingssaker ligger i den lagrede 80-prosentdelen. Reserverte 20-prosentetiketter og det tidligere 2025–2026-holdoutet er ikke brukt. Hashkontroller og tester beskytter grensene. BGE er ferdigtrent; det er ikke kontrollert om dens opprinnelige treningsmateriale følger de historiske datoene.

En bootstrap med 1000 uttrekk av hele selskap/møtedato-grupper gir omtrentlige 95-prosentintervaller på 45,9–85,7 prosent for presisjon og 23,7–53,5 prosent for recall. Intervallene gjelder den faste modellens utviklingsprediksjoner. De korrigerer ikke for modellvalg eller gjentatt bruk av utviklingsdata.

## Hva som mangler for 85/85

På 77 MOT krever recall strengt over 85 prosent minst **66 riktige MOT**. Ved 66 riktige kan det være høyst **11 feilaktige MOT** for å få presisjon over 85 prosent. Dagens v2 har 29 riktige og 17 feilaktige. Å nå akkurat dette punktet krever derfor 37 flere riktige MOT og seks færre falske alarmer. Det innebærer å rette minst 37 av de 48 oversette MOT-sakene uten å innføre nye feil i andre saker.

Feilene fordeler seg slik, etter sakstype hentet bare fra forslagsteksten:

| Sakstype | Riktige MOT | Feilaktige MOT | Oversette MOT | Opplysninger å kontrollere |
|---|---:|---:|---:|---|
| Styrevalg | 15 | 14 | 29 | Uavhengighet, CEO/styreleder, komiteer, oppmøte og andre verv |
| Lønn og insentiver | 5 | 0 | 7 | Opptjening, utvanning, prestasjonskrav, størrelse og bindingstid |
| Andre forslag | 9 | 3 | 12 | Full forslagstekst, styrets svar, garantier, kapitalvilkår og relevante regler |

Disse opplysningene er begrunnede kandidater til bedre modellinput. Feilene beviser ikke at ett bestemt forhold forklarer NBIMs stemme. Navn eller en tittel som «Approve Executive Compensation» inneholder ikke nødvendigvis faktaene som avgjør stemmen. I referansegrunnlaget fra 2019–2023 har 58 identiske tekstinputgrupper både MOT og ikke-MOT. Også når selskapet tas med, finnes motstridende utfall mellom år. Dette viser en begrensning ved disse inputene, ikke en generell øvre grense for modellens mulige ytelse.

Den eksisterende evalueringsindeksen har daterte dokumenter for **232 av 1505 saker**, med **11 av de 77 MOT-sakene**. Bare **5 av 48 oversette MOT-saker** har dokumenter i denne indeksen. De øvrige **43** trenger kildeinnhenting før dagens dokumentsøk kan bidra med samtidige fakta. At et dokument finnes i indeksen betyr heller ikke at det nødvendige faktumet er hentet ut eller bekreftet.

Neste nødvendige arbeid er derfor:

1. Utvide dokumentgrunnlaget for de relevante selskapene og årene, også tidligere treningsår. Lagre publiseringsdato, selskap, møte, kilde-URL og tekstposisjoner. Kilder publisert etter beslutningstidspunktet skal ikke brukes.
2. Hente og kontrollere fakta for styrevalg først: denne gruppen står for 43 av 65 feil. Lagre hver verdi sammen med et presist sitat og kildeposisjon. Manglende fakta skal være ukjent, ikke automatisk et regelbrudd.
3. Gjøre det samme for lønn, kapital og aksjonærforslag. Knytte faktaene til retningslinjen som gjaldt på møtedatoen. Vektorsøk brukes til å finne relevant tekst; selve faktaene og reglene må avgjøre vurderingen.
4. Trene og validere på tidligere års kontrollerte fakta. Velge én modell og terskel før en ny, uavhengig evaluering. Rapportere alle kjente stemmer, inkludert saker uten tilstrekkelig kontekst.

En konkret arbeidsliste for alle 65 feil ligger i `data/local-rag/vote-learning-v2-diagnostics/error-review.csv`. Den oppgir sak, feiltype, skår, dokumentdekning og hvilke fakta som må undersøkes. Oppgavene står som uavklarte. Vi har ikke hentet eller verifisert de manglende selskapsdokumentene i denne modellkjøringen, og kan derfor ikke hevde at faktalaget eller 85/85-målet er ferdig.

## Kjør og kontroller

Bruk det eksisterende miljøet i `voting-desk/`. Alle nye modellkall er lokale. Modellen lager MOT/ikke-MOT, ikke en komplett FOR/MOT/AVSTÅ-anbefaling med kildebelegg.

```bash
# Beregn én lagret sak på nytt, uten trening eller API-kall:
.venv/bin/python vote_experiment.py predict --meeting 1832444 --item 6

# Et nytt forsøk får sin egen mappe. Gamle resultater overskrives ikke:
.venv/bin/python vote_experiment.py run --output data/local-rag/vote-learning-next

# Åpne eksisterende kildesøk og resultatside:
.venv/bin/python rag_app.py --db data/local-rag/development-2024.sqlite --no-browser

.venv/bin/python -m unittest test_vote_features test_vote_experiment test_vote_diagnostics test_rag_results -v
```

V2 ligger i `data/local-rag/vote-learning-v2/`. `plan.json` angir kandidatene og utvalgskriteriet, `selection.json` det låste valget, `validation.csv` alle valideringsprediksjonene og `development.csv` de 1505 utviklingsprediksjonene. `learner.joblib`, `reference/`, `feature_names.json` og `development-inputs.npz` gjør gjenbruk mulig. `source/` inneholder kildekoden brukt i forsøket. `summary.json` binder resultatene til data-, kode- og artefakthasher. Modellfiler er lokale pickle-baserte filer og skal bare lastes fra egen, kontrollert kjøring.

Alle 1505 scorer og avgjørelser i både v1 og v2 er kontrollert etter ny innlasting og er nøyaktig like de lagrede resultatene. Etter forsøket ble versjonering av forbehandlingen lagt til i kode for å bevare denne oppførselen også ved gjenbruk av eldre modeller. Ingen modell eller terskel ble endret i denne kontrollen.

Metodisk støtte: scikit-learns dokumentasjon om [validering og adskilte datasett](https://scikit-learn.org/stable/modules/cross_validation.html) og [gradient boosting](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html). Implementasjon og dokumentasjon er laget med Codex-assistanse. De frosne modellene og holdout-resultatene er bevart.
