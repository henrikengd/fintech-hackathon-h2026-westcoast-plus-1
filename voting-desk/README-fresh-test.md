# Nye oktobermøter med låst modelloppsett

Denne kjøringen er bevart med sitt opprinnelige oppsett. Det senere [F1-baserte modellvalget](README-f1.md) bruker ikke oktoberdata og erstatter ikke resultatene her.

Denne testen sammenligner den lokale avviksmodellen og Claude med historiske vektortreff på møter fra **1.–31. oktober 2026**. De gamle prosjektdataene slutter 30. september 2026. Møtene i det nye utvalget finnes verken blant de gamle møte-ID-ene eller blant gamle kombinasjoner av selskap og møtedato.

Utvalget ble fastsatt før de nye stemmeutfallene ble hentet. Vi søkte etter alle 194 selskapsnavn fra det gamle datasettet på NBIMs offentlige nettsider, krevde eksakt navnetreff og tok med alle oktobermøter som søkene fant. Det ga sju møter: seks ekstraordinære og ett ordinært. Dette er et lite, sesongpreget utvalg fra tidligere kjente selskaper, ikke et representativt utvalg av hele fondet.

De sju møtene har til sammen 36 forslag. Ingen saksrader er valgt bort før prediksjon.

| Dato | Selskap | Møte-ID | Møtetype hos NBIM |
|---|---|---|---|
| 6. oktober | Berger Paints India Limited | 2115133 | Special |
| 8. oktober | Colruyt Group NV | 2119706 | Extraordinary Shareholders |
| 13. oktober | TCC Group Holdings CO., LTD. | 2108581 | Special |
| 20. oktober | Everbright Securities Company Limited | 2120187 | Extraordinary Shareholders |
| 21. oktober | PT Solusi Sinergi Digital Tbk | 2121576 | Extraordinary Shareholders |
| 29. oktober | Woolworths Group Limited | 2120636 | Annual |
| 30. oktober | Hainan Jinpan Smart Technology Co., Ltd. | 2124394 | Special |

## Resultat fra 5. november 2026

33 av 36 forslag har både kjent NBIM-stemme og styreanbefaling. Tre av disse er faktiske avvik. Én sak uten kjent NBIM-stemme og to med kjent NBIM-stemme, men ukjent styreanbefaling, er utelatt fra avviksmålingen etter prediksjon.

| Modell | Precision | Recall | F1 | Riktige avvik | Falske alarmer | Oversette avvik |
|---|---:|---:|---:|---:|---:|---:|
| Lokal modell, låst terskel | 0,0 % | 0,0 % | 0,0 % | 0 | 2 | 3 |
| Claude med historiske vektortreff | 0,0 % | 0,0 % | 0,0 % | 0 | 2 | 3 |

Begge modellene overser de samme tre avvikene og lager de samme to falske alarmene. Alle 33 målbare saker har en prediksjon fra begge modeller. Alle sju Claude-kall ga godkjente svar; det er ingen feil eller omkjøringer i denne testen. Den separate MOT-målingen for Claude dekker 35 saker og gir også 0 prosent precision, recall og F1: null riktige MOT, to falske MOT og tre oversette MOT.

Dette er et svakt resultat på de nye møtene. Det dokumenterer ikke at den generelle recall er null; tre avvik fra to møter er for lite til en presis vurdering av ytelsen i drift. En modell som alltid følger styret, ville fått 30 av 33 saker riktig, altså 90,9 prosent accuracy, men fortsatt oversett alle avvikene.

De tre oversette avvikene gjelder Colruyts fullmakter til tilbakekjøp og gjenutstedelse av aksjer, og en endring av styrets myndighet hos PT Solusi. Claude begrunner sine FOR-prediksjoner med lignende tidligere saker. De to falske alarmene gjelder andre vedtekts- og styreendringer hos PT Solusi, hvor Claude viser til tidligere MOT-stemmer. Historisk tekstlikhet var dermed ikke nok til å skille disse nye sakene riktig. Dette er en beskrivelse av feilmønsteret, ikke en dokumentert årsaksforklaring eller en ny innstilling av modellen.

Etter skåring ble også NBIMs egne begrunnelser kontrollert. For [Colruyt](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting?m=2119706) gjelder de hensynet til aksjonærgodkjenning og tiltak som kan hindre oppkjøp. For [PT Solusi](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/meeting?m=2121576) gjelder den oversette saken aksjonærenes rettigheter ved grunnleggende vedtektsendringer. Disse begrunnelsene inngikk ikke i modellinput. De brukes bare til etterkontroll, siden en begrunnelse for dagens NBIM-stemme ville røpet fasiten.

Registrert API-bruk: 87 855 inputtokens og 3 101 outputtokens. Beregnet kostnad: **0,20672 USD**, omtrent 0,21 USD, etter samme prisgrunnlag som den tidligere Claude-sammenligningen. Prediksjonene ble låst kl. 21:38 UTC, og skåringen ble lagret kl. 21:38:53 UTC. Den lokale terskelen og Claude-oppsettet ble ikke endret etter kildeinnhentingen.

Uavhengig opptelling fra enkeltprediksjonene bekrefter alle resultatene i `verification.json`. En separat rekonstruksjon fra de sju arkiverte HTML-tabellene bekrefter alle 36 tekster, styreanbefalinger, NBIM-stemmer og saksidentiteter i `extraction-verification.json`. Seks elementer med NBIM-begrunnelse eller policyinnhold er utelatt fra forslagstekstene. Ingen feilkoblinger eller utelatte forslag ble funnet. Den samlede programtestpakken bestod 243 tester; den siste teksten i resultatvisningen ble i tillegg kontrollert med 39 relevante tester.

## Låst oppsett

| Del | Hva brukes i testen? |
|---|---|
| Lokal klassifikator | Uendret `semantic-history-boost`, trent på 2019–2023 |
| Lokal beslutningsterskel | Uendret 0,22539900622680564, valgt på 2024 |
| Tekstvektorer | Samme lokalt lagrede BGE-modellvekter |
| Claude | `claude-sonnet-5-5`, effort `medium`, samme prompt og svarskjema |
| Claude-historikk | Inntil åtte globale og åtte selskapsspesifikke teksttreff per forslag |
| Historisk datagrunnlag | 13 325 gamle saker med kjent NBIM-stemme og styreanbefaling, til og med 30. september 2026 |
| Tidsgrense | Historisk møtedato må være strengt før aktuell møtedato minus fem dager |
| Nye testutfall | Ingen tilbakeføring til historikken, heller ikke mellom oktobermøtene |

Modellvektene trenes ikke på nytt. Gamle stemmer fra 2025–2026 er tilgjengelig historikk for oktober, men brukes ikke til ny modelltrening eller terskelvalg. Begge modellene får samme tilgjengelige historiske periode; de representerer og bruker historikken forskjellig. Den lokale modellen bruker historikkegenskaper i tillegg til tekstvektorer. Claude får utvalgte teksteksempler og deres gamle stemmer.

Denne testen har **fast historikk fra før testperioden**. Det er strengere enn den tidligere løsningen, hvor historikken kunne vokse mellom møter i evalueringsperioden. Vi bruker ikke fasit fra et tidlig oktobermøte til å predikere et senere oktobermøte.

## Adskilt input og fasit

NBIMs offentlige sakstabell har stemmebegrunnelser og lenker til policytekst inne i samme celle som forslagsteksten. Uttrekket bruker bare de direkte tekstnodene i forslagets tekstfelt. Underliggende begrunnelser, policylenker og NBIM-stemmer tas ikke med i input. Alle saksrader beholdes, også når styrets anbefaling eller NBIM-stemmen ikke kan normaliseres til FOR, MOT eller AVSTÅ.

Arbeidsrekkefølgen er dokumentert med kontrollsummer:

1. Utvalgsregelen, gamle data, modell, prompt og terskel lagres.
2. Identitetene til alle aktuelle møter finnes uten å åpne de nye sakstabellene.
3. Koden, utvalget og uttrekksspesifikasjonen låses i `preflight-freeze.json`.
4. Sakstekst og styreanbefaling lagres i `source-ballots.csv`. NBIM-stemmer lagres separat i `references.csv`. Råuttrekk og filenes kontrollsummer lagres samtidig.
5. Modellinput kontrolleres mot en tillatt feltliste. `prepare` lager vektorer og kontekster og låser dem i `freeze.json` uten å lese referansestemmene.
6. Begge modellene predikerer. Godkjente svar og feil beholdes. `prediction-seal.json` låser resultatene før skåring.
7. Først deretter åpner `score` referansestemmene. Kontrollsummen må stemme med kilden som ble lagret før prediksjon.

Dette er en kontrollert programflyt og en etterprøvbar lokal logg, ikke en kryptografisk ordning som hindrer en person med filtilgang i å åpne fasiten. Kildeinnhentingen må håndtere stemmefeltene for å lagre dem separat. Prediksjonskoden leser dem ikke. Ingen modeller, terskler eller søkeregler endres etter at nye sakstabeller åpnes.

## Måldefinisjon og begrensninger

Hovedmålet er **NBIMs stemme ulik styrets anbefaling**, med precision, recall og F1 på samme saker for begge modellene. Ukjente målverdier utelates først etter prediksjon og telles separat. Manglende modellprediksjon på et faktisk avvik teller som oversett avvik. Den lokale modellen predikerer bare avvik, ikke en full FOR/MOT/AVSTÅ-stemme. MOT rapporteres derfor separat bare for Claude.

Kilden er [NBIMs publiserte stemmeintensjoner](https://www.nbim.no/en/responsible-investment/voting/our-voting-records/), ikke en uavhengig bekreftelse på faktisk avgitte stemmer. NBIM sier at instruksjoner publiseres fem dager før møtet der det er praktisk mulig, og at informasjonen kan endres. Eksakte historiske publiseringstidspunkter er ikke dokumentert i vårt datagrunnlag.

Testen gjennomføres i ettertid. Den dokumenterer at møtene var nye for prosjektets lagrede utviklingsdata, ikke at prediksjonene ble laget før møtene fant sted. Oktober ligger etter Sonnet 5.5s [oppgitte treningsdatagrense i juni 2026](https://platform.claude.com/docs/en/models/sonnet-5-5/overview). Det reduserer bekymringen for at de konkrete oktoberutfallene finnes i forhåndstreningen, men gir ingen full garanti om alt modellen vet.

Et lite antall faktiske avvik gir stor usikkerhet om recall og F1. Resultatene brukes ikke til å justere denne kjøringen. Dersom de brukes til videre modellutvikling, trengs et nytt urørt utvalg for neste sluttest.

## Etterprøving

Fra `voting-desk/`, etter separat kildeinnhenting og forhåndslåsing:

```bash
.venv/bin/python fresh_test.py prepare --ballots data/local-rag/fresh-test-2026-10-v1/source-ballots.csv
.venv/bin/python fresh_test.py local
.venv/bin/python fresh_test.py claude --workers 4
.venv/bin/python fresh_test.py score --references data/local-rag/fresh-test-2026-10-v1/references.csv
.venv/bin/python fresh_test.py status
```

Disse stegene er ikke ment å kjøre om igjen over eksisterende resultater. Forberedelse og skåring nekter å erstatte lagrede artefakter. Prediksjon gjenbruker lagrede svar og feil. Avbrutte API-kall må undersøkes før de eventuelt forsøkes på nytt; det gjøres ingen automatiske omkjøringer.

Alle testartefakter ligger under `data/local-rag/fresh-test-2026-10-v1/`, som er utelatt fra Git. `discovery.json` dokumenterer selskapssøkene; `source-extraction-spec.json` dokumenterer uttrekket; `source-capture.json` binder kildene til kontrollsummer; `bundles/` viser nøyaktig Claude-input; `responses/` og `local-predictions.json` inneholder enkeltprediksjonene; `report.json` er den samlede rapporten. Resultatsiden leser denne rapporten uten å starte nye modellkall.
