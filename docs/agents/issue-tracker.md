# GitHub Issues og prosjekt

Tracker er GitHub Issues i [henrikengd/fintech-hackathon-h2026-westcoast-plus-1](https://github.com/henrikengd/fintech-hackathon-h2026-westcoast-plus-1). Prosjektet er [westcoast + 1 · Stemmegivningsassistent](https://github.com/users/henrikengd/projects/3).

## Konvensjoner

- Hovedissue #1 er spesifikasjon og overordnet status. Den har enhancement og inngår ikke i arbeiderkøen.
- Barneissues har task. ready-for-agent betyr at oppgaven kan startes etter kontroll av faktiske blokkeringer. blocked angir avhengigheter eller ekstern tilgang.
- GitHubs native sub-issues og issue dependencies er den primære strukturen. Tekstlige avhengigheter og eksterne forutsetninger står også i hver issue.
- Prosjektstatus er Todo, In Progress og Done. Oppgaver lukkes etter integrert verifikasjon. Etiketter må oppdateres når blokkeringene løses.
- Bruk gh CLI for issue-operasjoner og strukturerte API-kall, eller --body-file for flersidig Markdown. Kontroller eksisterende issues før en gjenkjøring av publisering.
- Standardgrenen er main. Gjennomføringsvalg står i [spesifikasjonen](../features/claude-voting-assistant/spec.md).
- PR-er som automatisk kilde til nye oppgaver er deaktivert.

## Tilgang og etterprøvbarhet

Repoet var offentlig ved kontroll 5. november 2026. Prosjektet ble opprettet privat med repoet som standard. Alle åtte issues er lagt til.

CLI-tokenet har tilgang til issues, men mangler read:project/project. Prosjektet ble derfor opprettet og fylt gjennom den innloggede GitHub-nettleseren. Senere prosjektendringer krever tilsvarende nettlesertilgang eller en separat autorisert utvidelse av CLI-tilgangen.

[Publiseringsoversikten](../features/claude-voting-assistant/publication.json) inneholder stabile issue-ID-er og prosjektlenken. Kontroller trackerens faktiske tilstand før arbeid.
