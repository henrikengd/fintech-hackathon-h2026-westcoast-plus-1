# Stemmegivningsassistent: status og videre arbeid

Oppdatert 5. november 2026 etter livepiloten. [Spesifikasjon revisjon 2](spec.md) er gjeldende plan. [Pilotgjennomgangen](pilot-review.md) skiller faktiske modellresultater fra tidligere programtester. [Leveransejournalen](delivery.md) bevarer historikken.

PR #10 er merget. Prosjekt/kontrakter og regelindeks/MCP er levert gjennom #3 og #4. Anthropic-nøkkelen virker. Siste pilotforsøk har fem stemmevalg, to anbefalinger, tre manuelle saker og status partial. MOT-presisjon og recall er 1/1 med 40 prosent anbefalingsdekning. Dette er en teknisk pilot med foreløpig historisk regelavgrensning.

## Neste arbeid

| Oppgave | Neste leveranse | Status ved Prepare |
|---|---|---|
| [#2](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/2) | Nye senere møter, kildekoblinger og historiske regler | Klar til dataarbeid |
| [#5](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/5) | Rett kildene og håndgå Sprinklr-piloten | Klar til implementering ved Deliver |
| [#6](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/6) | Faktisk Claude-demo og chatens motstandstest | Trenger lagets Claude-konto |
| [#7](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/7) | Frossen API-evaluering og motstandstest | Venter på #2 og #5 |
| [#8](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/8) | Ren reproduksjon og innleveringspakke | Venter på #6 og #7 |

CCC og Sprinklr brukes videre til utvikling. Nytt holdout fryses før sluttkjøring. NBIM-API er valgfritt når referansen kan avstemmes offentlig. N-PX-filen holdes utenfor hovedmålingen. Ingen ny database eller modellbenchmark er planlagt.

Bruk [hovedissue #1](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1/issues/1) eller `$deliver` for gjennomføring. [Prosjekt 3](https://github.com/users/henrikengd/projects/3) gjenbrukes. Prepare endrer dokumentasjon og oppgaveplan, ikke applikasjonskode.
