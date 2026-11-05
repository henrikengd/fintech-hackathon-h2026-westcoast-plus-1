# Lokal stemmemodell med vektorsøk

Det aktive forsøket [maksimerer F1 for avvik fra styrets anbefaling](README-f1.md). Modellen under er et tidligere MOT-forsøk som prioriterte recall alene. Et mellomliggende forsøk med en lært MOT-klassifikator er dokumentert i [README-learning.md](README-learning.md). Disse har andre måldefinisjoner og skal ikke rangeres direkte mot avviksmodellene.

Denne modellen bruker tidligere saker til å klassifisere en ny sak som MOT eller ikke MOT. Den kjører på CPU og gjør ingen Claude- eller andre modell-API-kall. Vektorene lages lokalt med den allerede nedlastede, ferdigtrente modellen `BAAI/bge-small-en-v1.5`. Vi har laget søket, den tidsavgrensede historikken, vektingen og beslutningsregelen selv. Vi har ikke trent en språkmodell fra bunnen av.

[Sammenlign modellene](http://127.0.0.1:8502/evaluation) eller [se historiske treff bak en vurdering](http://127.0.0.1:8502/vector).

## Hvordan den virker

1. Forslagsteksten, styrets anbefaling og forslagsstilleren omgjøres til en vektor med 384 dimensjoner. NBIM-stemmen, begrunnelsen og avledede kategorier inngår ikke i teksten som vektoriseres.
2. Modellen søker etter lignende saker i den tillatte treningshistorikken. Bare møter som ligger mer enn fem dager før den nye møtedatoen, kan brukes. Eget møte er utelukket.
3. De nærmeste sakene bidrar med sine historiske stemmer. Høy tekstlikhet gir større vekt. Ved nøyaktig likhet prioriteres samme selskap, deretter nyere møter og en stabil saksidentitet.
4. Den vektede MOT-andelen sammenlignes med en terskel valgt i valideringen. Score er ikke en kalibrert sannsynlighet for at anbefalingen er riktig.

Det valgte oppsettet bruker 128 naboer og firedobbel stemmevekt for naboer fra samme selskap. Terskelen er 0,03218997466919282. Nettsiden viser inntil fem eksempler, mens alle 128 naboer inngår i scoren. Det er dermed ikke nok å telle MOT blant de fem som vises.

Vektorindeksen er en lokal NumPy-matrise med tilhørende metadata og separate stemmeetiketter. Med 6470 referansesaker trenger vi foreløpig ingen egen databaseserver. En senere ANN-indeks kan gjøre større søk raskere uten å endre hva som regnes som tillatt historikk.

## Resultat 5. november 2026

Alle radene under gjelder de samme 1505 sakene fra 2024, med 77 MOT. Det er utviklingsdata som har vært brukt tidligere, ikke en ny uavhengig sluttest.

| Oppsett | MOT-presisjon | MOT-recall | F1 | Riktige MOT | Feilaktige MOT | Oversette MOT |
|---|---:|---:|---:|---:|---:|---:|
| Lokal vektormodell | 11,1 % | 89,6 % | 19,7 % | 69 | 553 | 8 |
| Tidligere lokal tekstmodell | 38,1 % | 41,6 % | 39,8 % | 32 | 52 | 45 |
| Tidligere Claude-modell, lagrede svar | 49,3 % | 44,2 % | 46,6 % | 34 | 35 | 43 |
| Følg styrets anbefaling | 41,7 % | 6,5 % | 11,2 % | 5 | 7 | 72 |

Vektormodellen passerer recall-målet på 85 prosent i dette utviklingsutvalget. Den flagger samtidig 622 av 1505 saker, og 553 av flaggene er feil. Den er derfor et mulig verktøy for å finne kandidater til kontroll, men resultatet er for svakt til å erstatte en ferdig stemmevurdering.

Modellene har ulike beslutningsterskler og utvalgskriterier. Tekstmodellen ble valgt etter F1. Vektormodellen ble valgt etter presisjon gitt minst 85 prosent recall. Claude-svarene er historiske og brukte andre prompter og mer historikk. Tabellen viser de lagrede oppsettene på samme saker; den beviser ikke at én metode er bedre ved samme recall-nivå.

Historiske naboer forklarer hvilke tidligere stemmer modellen bygger på. De er ikke sitater fra retningslinjer og dokumenterer ikke at en stemmeanbefaling følger dagens regler. Klassen «ikke MOT» omfatter både FOR og AVSTÅ. Oppgavens krav om kildebelegg, full stemmeanbefaling og menneskelig overlevering trenger derfor egne komponenter.

## Validering og datagrenser

Modellvalget sammenlignet seks forhåndsbestemte oppsett: 8, 32 eller 128 naboer, med samme-selskap-vekt 1 eller 4. Valideringen gikk fremover i tid. For hvert år fra 2020 til 2023 ble modellen bare gitt referanser fra tidligere år. Ingen stemmer fra valideringsåret ble lagt til underveis.

Modell og terskel ble låst før 2024 ble scoret. Valideringen hadde 5333 saker og 266 MOT. Det valgte oppsettet fikk samlet 85,3 prosent recall og 8,7 prosent presisjon. Recall var 91,0 prosent i 2020, 79,1 i 2021, 87,4 i 2022 og 81,2 i 2023. Målet ble dermed ikke nådd i alle år.

Sluttmodellen bruker 6470 kjente stemmer fra 2019–2023. Både trening, validering og 2024-utvalget ligger i den tidligere lagrede 80-prosentdelen. Reserverte testmøter og selskap/møtedato-grupper er utelukket. 2025–2026 er ikke scoret. Partisjonene og kildedataene kontrolleres mot manifestets SHA-256-hasher. Den ferdigtrente språkmodellens opprinnelige treningsdata er ikke kontrollert mot de historiske møtedatoene.

Manglende historikk gir ukjent score. Slike saker beholdes i nevneren og teller som oversette MOT når fasiten er MOT. Et nullsvar blir aldri omgjort til MOT bare fordi terskelen settes til null.

## Kjør lokalt

Kjør fra `voting-desk/` i prosjektets eksisterende miljø. Modellfilene for FastEmbed må allerede være lastet ned som beskrevet i [RAG-oppsettet](README-rag.md).

```bash
# Gjenbruk embedding-cache og opprett et nytt, separat forsøk:
.venv/bin/python vector_experiment.py run --output data/local-rag/vector-experiment-next

# Last modellen på nytt og beregn én av utviklingssakene uten API:
.venv/bin/python vector_experiment.py predict --meeting 1832444 --item 6

# Start nettsiden med kildesøk og modellresultater:
.venv/bin/python rag_app.py --db data/local-rag/development-2024.sqlite --no-browser

.venv/bin/python -m unittest test_vector_model test_vector_experiment test_vector_app test_rag_results -v
```

`VectorVoteModel.load(...)` og `predict(frame, embeddings, ...)` er også tilgjengelige direkte fra Python for nye saker. Query-radene trenger saksidentitet, selskap, dato, forslagstekst, styrets anbefaling og forslagsstiller. De trenger ingen fasit. Bruk samme lokale encoder som ved bygging av indeksen.

Eksisterende eksperimentmapper overskrives ikke. Nettsiden leser den faste mappen `data/local-rag/vector-experiment-v1/`, slik at nye forsøk ikke automatisk erstatter sammenligningen. Råresultater og modellfiler ligger utenfor Git:

- `selection.json`: låst valg før scoring av 2024.
- `validation.csv`: alle seks oppsettenes valideringsprediksjoner.
- `development.csv`: 2024-prediksjoner og feil.
- `neighbors.json`: historiske treff som vises i UI-et.
- `model/`: vektorindeks, metadata, etiketter og kontrollsummer.
- `summary.json`: mål, sammenligninger, kildeidentitet og kodehash.

Den fulle 2024-prediksjonen er gjentatt etter innlasting av de lagrede modellfilene og ga identiske scorer og klassifikasjoner. Dette var en kontroll av lagring og innlasting, uten ny tilpasning eller endring av terskelen.

Implementert med Codex-assistanse. Tidligere modeller og historiske resultater er bevart.
