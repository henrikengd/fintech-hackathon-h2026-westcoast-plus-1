# Modellresultater etter oppsett-ID

Modellpakke v1, oppdatert 6. november 2026. Hovedtabellen viser F1 for å oppdage når NBIM stemmer annerledes enn styret anbefaler. Alle sju oppsett er målt på de samme 1 883 utviklingssakene fra 2024, med 98 faktiske avvik. Tersklene for lokalmodellene er tilpasset dette utvalget. [Forsøksrapport](../README-relevance.md)

| Plass | Oppsett-ID | Oppsettnavn | F1 | Precision | Recall | Saker med svar |
|---:|---|---|---:|---:|---:|---:|
| 1 | `VD-C03` | Claude hybrid dokumenter | **65,9 %** | 76,0 % | 58,2 % | 1 683 / 1 883 |
| 2 | `VD-C02` | Claude hybrid historikk | **63,5 %** | 65,9 % | 61,2 % | 1 777 / 1 883 |
| 3 | `VD-L01` | Lokal standard | **62,3 %** | 67,1 % | 58,2 % | 1 883 / 1 883 |
| 4 | `VD-L03` | Lokal hybrid semantisk | 60,9 % | 65,1 % | 57,1 % | 1 883 / 1 883 |
| 5 | `VD-C01` | Claude referanse | 57,0 % | 60,2 % | 54,1 % | 1 830 / 1 883 |
| 6 | `VD-L02` | Lokal hybrid historikk | 52,5 % | 56,5 % | 49,0 % | 1 883 / 1 883 |
| 7 | `VD-L04` | Lokal hybrid logistisk | 41,2 % | 50,7 % | 34,7 % | 1 883 / 1 883 |

`VD-L01` er den valgte lokalmodellen og har høyest F1 av lokalmodellene. `VD-C02` finner flest faktiske avvik på hele utvalget, 60 av 98. `VD-C03` har høyest målt F1 og lavest svarandel. På de 95 dokumentdekkede sakene der `VD-C03` manglet svar og `VD-C02` svarte, forsvant 13 falske alarmer og tre riktige avvik fra prediksjonene. Svarandelen må derfor leses sammen med F1.

## Sammenligning der begge oppsett svarte

| Utvalg | Oppsett | Saker | F1 |
|---|---|---:|---:|
| Saker besvart av både referansen og hybrid historikk | `VD-C01` Claude referanse | 1 724 | 62,2 % |
| Samme saker | `VD-C02` Claude hybrid historikk | 1 724 | 63,7 % |
| Dokumentdekkede saker besvart av begge hybridoppsett | `VD-C02` Claude hybrid historikk | 243 | 66,7 % |
| Samme saker | `VD-C03` Claude hybrid dokumenter | 243 | 66,7 % |

Den låste oktober-testen gjelder tidligere oppsett og rapporteres separat. [Oktober-testen](../README-fresh-test.md)

## Før inn nye målinger

Behold oppsett-ID-en når du tester samme modell, terskel og forsøksoppsett. Bruk en ny ID ved endring av disse. Legg nye utvalg i egne tabeller, og noter dato, antall saker, F1, precision, recall, svarandel og sti til resultatfilen. Behold tidligere målinger slik at laget kan følge utviklingen over tid.

Tallene i denne oversikten kommer fra `relevance-board-v1/summary.json`, `relevance-claude-v1/report.json` og `relevance-claude-v1/independent-verification.json` i modellpakken. [Bruksanvisning](README.md)
