# Test modellvariantene fra NK

Modellpakken samler de lagrede forsøkene på avvik fra styrets anbefaling. Klon `NK` med `git clone --branch NK <repo-url>`, eller oppdater `NK` med `git pull --ff-only origin NK` hvis du allerede står på branchen. Kjør kommandoene nedenfor fra `voting-desk/`.

## Start resultatsiden og test lokalmodellene

Bruk Python 3.12. På macOS og Linux:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python model_kit.py install
.venv/bin/python rag_app.py --results-only
```

På Windows oppretter du miljøet med `py -3.12 -m venv .venv` og bruker `.venv\Scripts\python.exe` i resten av kommandoene. Resultatsiden ligger på [localhost:8502/evaluation](http://127.0.0.1:8502/evaluation). Oppstarten bruker de lagrede rapportene og trenger verken API-nøkkel, dokumentindeks eller nedlasting av embeddingmodellen.

Kjør de fire lokale variantene på den samme lagrede saken:

```sh
.venv/bin/python model_kit.py replay --meeting 1841869 --item 1
```

Kommandoen laster de trente modellene og beregner en ny skår fra de lagrede egenskapene for saken. Resultatet viser oppsett-ID, modellnavn, skår, terskel og om modellen varsler avvik. Legg til `--setup VD-L01` for å kjøre bare den valgte lokalmodellen. Bruk `meeting_id` og `item_no` fra `data/local-rag/relevance-board-v1/calibration.csv` for å velge andre saker. Alle kommer fra 2024-kalibreringen.

Pakken har sju navngitte oppsett i sammenligningen. Bruk ID-en når dere deler resultater, for eksempel «sjekk opp mot VD-L01». Samme ID vises på resultatsiden. Gi fremtidige varianter en ny ID når modellen, terskelen eller forsøksoppsettet endres. [Resultatoversikt per oppsett-ID](PERFORMANCE.md)

| ID | Navn | Modell eller oppsett | F1 på utviklingsdata fra 2024 |
|---|---|---|---:|
| `VD-L01` | Lokal standard | `semantic-history-boost`, valgt lokalmodell | 62,3 % |
| `VD-L02` | Lokal hybrid historikk | `hybrid-history-boost` | 52,5 % |
| `VD-L03` | Lokal hybrid semantisk | `hybrid-semantic-boost` | 60,9 % |
| `VD-L04` | Lokal hybrid logistisk | `hybrid-semantic-logistic` | 41,2 % |
| `VD-C01` | Claude referanse | Tidligere vektorsøk, lagrede svar | 57,0 % |
| `VD-C02` | Claude hybrid historikk | Hybrid historikksøk | 63,5 % |
| `VD-C03` | Claude hybrid dokumenter | Hybrid historikksøk og dokumenter | 65,9 % med lavere svarandel |

Resultatsiden viser hvordan manglende svar påvirker sammenligningen med dokumenter. På dokumentdekkede saker der begge nye Claude-oppsettene svarte, fikk begge 66,7 % F1. Se [forsøksrapporten](../README-relevance.md).

## Prøv Claude på ett møte

Legg din egen `ANTHROPIC_API_KEY` i `voting-desk/.env` eller i miljøet ditt. Hver av disse kommandoene sender én betalt forespørsel for samme møte med oppsettet fra den låste forsøksplanen. Svaret skrives til terminalen.

```sh
.venv/bin/python model_kit.py claude --meeting 1841869 --setup VD-C02
.venv/bin/python model_kit.py claude --meeting 1841869 --setup VD-C03
```

For å beregne Claude-målingene på nytt fra lagrede svar, kopier `data/local-rag/relevance-claude-v1/` til en ny mappe og kjør `.venv/bin/python relevance_claude.py report --output <kopiens-sti>`. Dette bruker null API-kall og skriver de beregnede målingene til kopien. Dokumentindeksen og BGE-modellen trengs først når du vil hente nye utdrag eller trene på nytt. Fremgangsmåten står i [forsøksrapporten](../README-relevance.md) og [oppsettet for lokalt dokumentsøk](../README-rag.md).

Hele testpakken bruker også de valgfrie søkeavhengighetene. Installer med `.venv/bin/python -m pip install -r requirements.txt -r requirements-rag.txt` og kjør `.venv/bin/python -m unittest discover -q`.

## Hva som deles

`experiments-v1.zip` inneholder de lokale modellvektene, låste egenskaper og valideringsresultater, Claude-planene med de kontrollerte forespørslene og svarene, og sammendraget fra oktober-testen. `manifest.json` navngir hver fil med en SHA-256-kontrollsum. Installeringen verifiserer pakken og fyller inn manglende artefakter i `data/local-rag/`. Bruk en fersk klone hvis du har en lokal kjøring med samme navn og andre resultater.

NKs opprinnelige inngang er fortsatt `app.py`. Modellpakken bruker `model_kit.py` og `rag_app.py`. Kildedata som allerede er versjonert i NK ligger på sine opprinnelige stier. Legg nye forsøk i egne utmapper, og gi neste delte modellpakke et nytt versjonsnummer.
