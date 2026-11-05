# Kravrespons for case 1

Westcoast + 1 bygger en stemmegivningsassistent for en hel generalforsamling. Claude vurderer hvert forslag mot daterte retningslinjer. MCP-tjenesten returnerer regeltekst, versjon og kilde. API-kjøringen kontrollerer at sitatene finnes i de hentede reglene og i de oppgitte utdragene fra innkallingen. Ved manglende grunnlag får forslaget status manuell sjekk med en begrunnelse.

Pilotgrunnlaget har ett utviklingsmøte og ett senere testmøte. De har henholdsvis tre og fem stemmevalg. Referansene er NBIMs publiserte stemmeintensjoner. Evaluatoren måler MOT på selve forslaget, sammenligner med styrets dokumenterte anbefaling og viser anbefalingsdekning. Testreferansene ligger separat fra modellinput. Utvalget er lite og valgt for å kunne avstemme hele møter. En modellkjøring på dette utvalget kan vise arbeidsflyten, men gir et begrenset grunnlag for effektpåstander.

Lokale tester dekker validering, datakobling, søk, verktøykall, kostnadsgrenser og beregning av metrikker. [Leveransejournalen](features/claude-voting-assistant/delivery.md) skiller disse testene fra kjøringer som krever lagets tilgang. [README](../README.md) beskriver oppsettet og evalueringskommandoen.

Før demoen må laget kontrollere en full API-kjøring, en faktisk Claude-samtale med innkalling og MCP, og en kontrollert motstandstest. Før en større historisk evaluering må laget dokumentere de nøyaktige virkningsperiodene for retningslinjene og utvide testgrunnlaget.
