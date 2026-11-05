# NBIM-regler og MCP

Installer Poppler for å bygge en indeks fra PDF. Manifestet identifiserer originalen med URL og SHA-256. Filen legges lokalt sammen med andre rådata. [NBIM Global voting guidelines 2025](https://www.nbim.no/contentassets/cbee6983c7d044a6a6d2f286ed5fa3df/global-voting-guildeines_2025.pdf).

```sh
mkdir -p data/raw
curl -fL 'https://www.nbim.no/contentassets/cbee6983c7d044a6a6d2f286ed5fa3df/global-voting-guildeines_2025.pdf' -o data/raw/nbim-2025-linked.pdf
uv run --no-sync python -m voting_assistant index --manifest data/policies/nbim-2025.json
uv run --no-sync python -m voting_assistant serve
```

Indeksen dekker 18 regelavsnitt på side 5–21. Manifestet fastsetter avsnittsgrenser og beskjærer PDF-ens margen og bunntekst. Der et avsnitt fortsetter på neste side, viser kildehenvisningen til avsnittets startside. Indeksen er versjonert etter innhold, regelmetadata og vektorer. Vektorene teller ord i faste hash-bøtter, med ekstra vekt på avsnittsnavn. Cosinuslikhet rangerer treff som har minst ett ord til felles etter normalisering.

Manifestet bruker 13. mai 2025 som tidligste dekningsdato fordi den lenkede PDF-en har denne datoen i dokumentmetadata. Indeksen dekker ut 2025. Avgrensningen gjelder denne versjonen av datagrunnlaget. En møtedato utenfor perioden gir `no_valid_version`. En annen regelversjon krever en egen kilde, kontrollsum og dokumentert periode.

MCP-endepunktet er `http://127.0.0.1:8000/mcp` lokalt. De to verktøyene har lesetilgang til regelindeksen. Angi `MCP_PUBLIC_URL` med den faktiske HTTPS-adressen for å godta videresendte kall til et offentlig vertsnavn. `MCP_BEARER_TOKEN` er valgfritt og krever at klienten kan sende en Bearer-header. Sett bare opp en tilgjengelig HTTPS-adresse når du har avklart hvordan den skal brukes.

Bruk `corpus_kind: synthetic` for syntetiske testkilder. Da godtar indekseringen UTF-8-tekst med sideskift markert som form feed. Alle tekstkilder krever SHA-256 og eksplisitte avsnittsgrenser. Et NBIM-manifest krever PDF med en offisiell lenke fra nbim.no. Hold stemmeutfall og etterfølgende saksbegrunnelser utenfor regelmanifestet.

## Lokal kontroll

Med møtedato 1. juni 2025 ga søk etter direktørvalg med ukjent kandidat, opptjening av lederlønn og revisors honorarer forventet avsnitt som første treff på henholdsvis side 9, 12 og 16. SDK-klienten hentet fulltekst for de samme avsnittene gjennom lokal Streamable HTTP. Den fikk egne statuser for tomt treff, møtedato utenfor perioden og ukjent regelversjon. Testene kan kjøres fra README uten å hente PDF-en.
