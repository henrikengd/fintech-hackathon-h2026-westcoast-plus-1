# Kontroll av datalekkasje 5. november 2026

## Vurdering

Det er ikke påvist direkte lekkasje av aktuell fasit eller fremtidige stemmer i den aktive lokale avviksmodellen eller de lagrede Claude-kontekstene. Dette er ikke en garanti for at hele evalueringen er uavhengig: 2024 er brukt til utvikling og terskelvalg, eldre testresultater er allerede kjent, og Claude kan ha sett offentlig informasjon om testårene under sin opprinnelige trening.

Kontrollen var lesende. Ingen modell ble trent på nytt, ingen API-kall ble gjort, og ingen stemmeutfall fra 2025–2026 ble undersøkt. Denne rapporten endrer ingen tidligere resultater.

## Kontrollerte grenser

| Kontroll | Resultat |
|---|---|
| Lokal trening | 7993 saker fra 2019–2023; siste treningsdato 6. desember 2023 |
| Utvikling/terskelvalg | 1883 saker fra 2024; første dato 17. januar 2024 |
| Overlapp mellom trening og 2024 | Ingen felles møte-ID eller selskap/dato-gruppe |
| Skalering, imputering og eventuell TF-IDF | Tilpasses treningsradene i hver fold; ikke 2024 |
| Endelig lagret skalerer | 7993 treningsobservasjoner |
| Modellvalg i den nye kjøringen | Validering fremover i tid på 2020–2023 |
| Valg av endelig terskel | Bruker uttrykkelig 2024-fasiten |
| Embeddingtekst | Bare forslagstekst, styreanbefaling og forslagsstiller |
| Historiske bidrag | Strengt eldre enn aktuelt møte minus fem dager; eget møte utelukkes |

Felles beregning av BGE-vektorer for trening og 2024 er ikke i seg selv læring fra 2024: den ferdigtrente koderen behandler hver tillatte tekst separat. Den nye klassifikatorens tilpasning av skala og modellvekter skjer bare på de tillatte treningsradene.

39 relevante tester for egenskaper, måldefinisjon, lokal forsøksprotokoll, Claude-kontekst og Claude-kjøring passerte. I en ekstra kontroll av tolv virkelige 2024-saker ble aktuell målverdi, begrunnelse og kategori erstattet, og alle ikke-tillatte historiske stemmer ble snudd. Alle 59 beregnede egenskaper forble identiske, inkludert manglende verdier. Sakene dekket januar til desember.

## De faktisk lagrede Claude-kontekstene

Alle 168 kontekster ble kontrollert mot sine lagrede hasher. De inneholder 1883 aktuelle forslag, 15 201 historiske oppføringer fordelt på møtekontekstene og 23 593 koblinger fra aktuelle forslag til historikk.

- Ingen brudd på dato-, femdagers- eller eget-møte-grensen.
- Ingen uventede felt med aktuell NBIM-stemme, utfallsbegrunnelse eller lokal modellskår.
- Ingen avvik fra konteksthashene; åtte av åtte arkiverte kildefiler samsvarer med den låste kjøringen.
- Den yngste historiske oppføringen er seks dager eldre enn saken som vurderes.
- Aktuell fasit og lokale skårer ligger i en separat evalueringsfil som ikke sendes til Claude.

964 forslag fikk historikk fra tidligere møter i 2024. Dette er tilsiktet oppdatering av tilgjengelig informasjon, ikke oppdatering av modellvektene. Det er bare forsvarlig som driftssimulering dersom disse tidligere utfallene faktisk var tilgjengelige ved beslutningstidspunktet.

## Begrensninger som står igjen

**Utvikling på 2024.** Å velge terskel på et valideringssett er vanlig, men resultatet på samme sett er ikke en uavhengig sluttest. 2024 har også vært brukt i tidligere modellforsøk og feilanalyser. At den siste kjøringen velger modell programmatisk uten 2024, fjerner ikke påvirkningen fra tidligere utvikling. Den tidligere 2025–2026-testen er allerede evaluert og kan heller ikke beskrives som helt urørt.

**Ferdigtrent Claude.** Anthropic oppgir juni 2026 som kunnskapsgrense for Sonnet 5.5. Modellen kan derfor ha sett offentlige opplysninger fra 2024 før vårt forsøk. Vi vet ikke om akkurat NBIM-utfallene inngikk i treningen. En instruksjon om bare å bruke gitt kontekst beviser ikke at tidligere kunnskap er utelukket. Forsøket er en ettertidsevaluering med tidsfiltrert kontekst, ikke en garanti for hva en modell tilgjengelig i 2024 ville prestert.

**Ferdigtrent BGE.** Modellkortet daterer utgivelsen av BGE v1.5 til 12. september 2023. Det er relevant støtte for at den opprinnelige modellen eksisterte før 2024. Koblingen mellom de lokale modellfilene og akkurat de opprinnelige vektene er ikke verifisert i denne kontrollen, og modellens treningsmateriale er ikke revidert. Valideringsår før utgivelsen må uansett skilles fra en strengt historisk tilgjengelig modell.

**Informasjonstidspunkt.** Historiske møtedatoer med femdagersmargin brukes som tilnærming til tilgjengelighet. Eksakte publiseringstidspunkter og eventuelle senere rettelser i stemmedataene er ikke dokumentert. Tilsvarende er tilgjengeligheten av hvert rått felt i historiske sakslister ikke uavhengig kontrollert.

**Gjentakelser.** 150 av 164 selskaper i 2024 forekommer i treningen. Gjentatte forslag fra tidligere år er relevant historikk, men målingen sier primært noe om senere møter i kjente selskaper. Det finnes dessuten 26 rader i 2024 fordelt på 13 grupper med identisk selskap, dato, forslagstekst, styreanbefaling og forslagsstiller. 20 av disse radene gjelder to ZTO-møte-ID-er samme dag. De øvrige gjentas innen møter. Ingen av de 26 er faktiske avvik. Dette krysser ikke treningsgrensen og gir ikke samme-dags fasit i søket, men kan påvirke vektingen. Kildeopprinnelsen må avklares før noen rader eventuelt fjernes; like tekster er ikke alene bevis på feilregistrering.

## Videre evaluering

Bruk 2024 som utviklings- og valideringsgrunnlag, med tydelig merking. Lås kode, modell, prompt, søkeinnstillinger og terskel før en ny evaluering på møter som ikke har påvirket utviklingen. Dokumenter faktisk tilgjengelighet med `published_at` eller tilsvarende der det finnes. Skill hovedmålingen for senere møter i kjente selskaper fra en eventuell separat prøve på helt ukjente selskaper. En ny tilfeldig deling av allerede brukte data gjør ikke historikken urørt.

## Kilder

- Lokal protokoll: [board_experiment.py](board_experiment.py), [vote_features.py](vote_features.py), [vote_learner.py](vote_learner.py).
- Claude-grunnlag: [claude_board_context.py](claude_board_context.py), [claude_board_experiment.py](claude_board_experiment.py), `data/local-rag/claude-board-v1/plan.json` og `bundles/`.
- Tidligere eksponering: [README-board.md](README-board.md) og begrensningene i [README.md](README.md).
- [scikit-learn: datalekkasje og forbehandling](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
- [Anthropic: Sonnet 5.5 og kunnskapsgrense](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).
- [BAAI: BGE v1.5-modellkort og utgivelseshistorikk](https://huggingface.co/BAAI/bge-small-en-v1.5).
