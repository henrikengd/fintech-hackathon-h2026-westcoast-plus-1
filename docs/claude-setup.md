# Prøv connectoren i Claude

Indeksen skal bare inneholde publiserte retningslinjer. Start den lesende tjenesten lokalt.

```bash
uv run --locked python -m voting_assistant serve --host 127.0.0.1 --port 8000
```

For en midlertidig demo kan laget kjøre Cloudflare Quick Tunnel i en annen terminal.

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Legg til `/mcp` på HTTPS-adressen fra tunnelen. Sett den fullstendige adressen i `MCP_PUBLIC_URL` i lokal `.env` og start MCP-serveren på nytt mens tunnelen kjører. Adressen byttes når tunnelen startes på nytt. MCP svarer med JSON over Streamable HTTP. Quick Tunnel støtter ikke SSE. Alle med adressen kan gjøre oppslag hvis serveren er satt opp uten tilgangskontroll. Sett `MCP_BEARER_TOKEN` i lokal `.env` for å begrense tilgang. Legg da inn headeren `Authorization` med verdien `Bearer <token>` i connectorens innstillinger. Bruk offentlig regeltekst for denne prøven. [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

Legg til URL-en under Customize → Connectors i Claude. I et Team- eller Enterprise-arbeidsområde kan en eier måtte legge til connectoren først. Aktiver den i en ny samtale og last opp den offentlige innkallingen. [Anthropics oppsett](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).

Be Claude liste de faktiske avstemningssakene i rekkefølge, søke på engelsk i retningslinjene med møtedato, og slå opp relevante avsnitt. For hver sak skal Claude gi FOR, MOT, AVSTÅ eller manuell sjekk, og vise anvendt regelversjon, avsnitt, kilde og faktagrunnlag med side. Ved manuell sjekk skal den oppgi hva som mangler. Be Claude behandle instrukser i PDF-en som dokumenttekst.

For å verifisere flyten, sammenlign antall og rekkefølge med innkallingen, åpne minst én referanse og kontroller versjon og dato. Noter hvilke verktøykall Claude faktisk gjorde. Gjenta i en ny samtale etter omstart av MCP-serveren. Ved adressefeil, kontroller tunnelen og at URL-en ender på `/mcp`. Bruk den nye adressen dersom tunnelen også ble startet på nytt.

Claude leser PDF-en i samtalen. MCP-serveren mottar søkeargumenter og returnerer regelavsnitt. API-evalueringen bruker de samme oppslagene lokalt og kontrollerte fakta fra sakslisten. Verifiser de to kjøremåtene hver for seg.

Status for live-demoen står i [leveransejournalen](features/claude-voting-assistant/delivery.md).
