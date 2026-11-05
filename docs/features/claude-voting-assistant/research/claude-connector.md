# Claude-connector som grunnlag for scope

Kontrollert 5. november 2026. Notatet gjelder en Claude.ai-connector som henter offentlige stemmeretningslinjer. Dokumentasjonen er undersøkt. Integrasjonen er ennå ikke prøvekjørt.

## Dokumenter og verktøyinput

Claude støtter PDF som vedlegg i en samtale. Dokumentasjonen beskriver analyse av både tekst og visuelle elementer for PDF-er på opptil 100 sider. For lengre PDF-er innenfor opplastingsgrensen behandles tekst. Dette er relevant dersom innkallingen inneholder skannede tabeller. [Filopplasting i Claude](https://support.claude.com/en/articles/8241126-upload-files-to-claude)

MCP-verktøy definerer forventede argumenter med et JSON-skjema. Klienten kaller verktøyet med verktøynavn og argumenter. Denne protokollbeskrivelsen gir ikke serveren automatisk tilgang til hele samtalen eller originalfilene som er lastet opp i klienten. [MCP-verktøy og kallformat](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

Dokumentasjonen som er kontrollert beskriver ingen generell overføring av et Claude-chatvedlegg til en vilkårlig MCP-server. Det er derfor en uavklart kapasitet dersom produktet skal behandle original-PDF-en på serveren. En enklere foreslått flyt er at Claude leser vedlegget og sender søk, møtedato og relevante fakta som eksplisitte verktøyargumenter. Dette er en arkitektonisk anbefaling som må prøves med én reell innkalling.

## Drift, transport og tilgang

En remote connector kjører på infrastruktur dere drifter. Anthropic anbefaler Streamable HTTP og støtter også eldre HTTP+SSE. Serveren kan bruke OAuth, en fast legitimasjon eller ingen autentisering. En custom connector kan legges til med URL uten katalogpublisering. [Bygge MCP-server for Claude](https://claude.com/docs/connectors/building)

Tilkoblingen kommer fra Anthropics skyinfrastruktur. Endepunktet må være tilgjengelig derfra. Team- og Enterprise-organisasjoner krever at en person med riktig administrativ rolle legger til connectoren før medlemmer bruker den. [Nettverk og organisasjonstilgang](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)

En liten tjeneste over HTTPS med Streamable HTTP og lesetilgang til offentlige regelavsnitt er dermed en mulig teknisk minsteversjon. Autentisering og hosting er produktvalg som fortsatt må avgjøres. Dokumentasjonen anbefaler testing mot den faktiske Claude-klienten og beskriver også tunnellering ved utvikling. [Bygging og testing](https://claude.com/docs/connectors/building)

## Evaluering og kontotilgang

Messages API har en MCP-connector som lar en API-kjøring bruke verktøy fra den samme remote serveren. Den krever HTTPS-adresse og støtter verktøykall, mens støtte for øvrige MCP-funksjoner er mer begrenset. Dette gir en dokumentert vei til et evalueringsskript med samme søkeverktøy. [MCP i Messages API](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector)

Claude-chat og Claude Console er separate produkter. Console gir API-nøkler og egen API-fakturering. Gjeldende dokumentasjon beskriver inkluderte API-kreditter for enkelte abonnementer, men Console-tilgang må fortsatt settes opp. Lagets tilgjengelige konto, nøkkel og budsjett er uavklart. [Claude-plan og API-tilgang](https://support.claude.com/en/articles/9876003-why-is-claude-api-usage-billed-separately-from-my-paid-claude-plan)

Min vurdering er at evalueringen bør lagre datasettversjon, regelversjon, modell-ID, vurderingsinstruksjon, verktøykall og svar. Chatdemo og API-evaluering må beskrives som to kjøremåter og kontrolleres hver for seg. En vellykket API-test dokumenterer ikke alene at opplasting og verktøybruk fungerer i Claude-chatten. Tidlige avklaringer er derfor en gjennomgående chattest, faktisk API-tilgang og valgt hosting. Dette er forslag til scopet, ikke verifisert implementering eller vedtatte produktvalg.
