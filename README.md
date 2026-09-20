# GBP Sentinel: Geautomatiseerd anti-spam platform voor Google Bedrijfsprofielen

GBP Sentinel is een geautomatiseerd platform voor het opsporen, auditeren, exporteren en indienen van frauduleuze Google Bedrijfsprofielen (GBP) in Nederland. Het richt zich op netwerken met virtuele kantoren (Regus, Spaces), drop-off partners (supermarkten, tabakswinkels) en niet-toegestane woonadressen.

---

## 1. Functionaliteiten

- **Maps & sitemap scanner**: Doorzoekt Google Maps en bedrijfswebsites op alle filialen en satellietvermeldingen.
- **Fraude-audit**: Controleert locaties automatisch tegen een referentiedatabase van virtuele kantoren (`virtual_offices.json`), inleverpunten (`parcel_chains.json`) en adresafwijkingen ten opzichte van het officiële KvK-hoofdkantoor.
- **Google Redressal CSV-generator**: Maakt direct een CSV-bestand aan dat voldoet aan alle vereisten van Google Support (`business_name_on_profile, google_maps_url, physical_address, actual_occupant_and_business_type, commercial_register_kvk_status, policy_violation_details`).
- **Verklaringstekst generator**: Formuleert een beknopte, beleidsmatige Engelse toelichting die strikt onder de 1000 tekens blijft.
- **Geautomatiseerde Playwright-inzender**: Vult het officiële Google Redressal-formulier in, uploadt de CSV, klikt op verzenden, registreert het officiële Google Case ID (`[0-9]-[0-9]+`) en bewaart screenshots van voor en na de verzending.
- **Community forum escalatie**: Genereert een kant-en-klaar forumbericht voor de Google Business Profile Community en plaatst de tekst automatisch op het Windows-klembord via PowerShell.
- **SQLite database**: Bewaart alle onderzochte bedrijven, locaties, ingediende dossiers en ontvangen Case ID's in `data/cases.db`.

---

## 2. Installatie & Configuratie

Het project bevindt zich in:
```
C:\Users\danny\.gemini\antigravity\scratch\gbp-sentinel
```

### Configuratie (`config.json`)
Standaard ingesteld op:
```json
{
  "submitter_name": "Trade Compliance Desk",
  "submitter_email": "ddpzonly@gmail.com",
  "submitter_organization": "Local Trade Integrity & Consumer Protection Netherlands",
  "authuser": "1",
  "default_activity_type": "address",
  "headless": true,
  "browser_locale": "nl-NL"
}
```

---

## 3. Gebruik via de CLI

Navigeer naar de projectmap en voer de commando's uit:

### Overzicht van eerdere cases & Case ID's bekijken
```powershell
python -m gbp_sentinel list
```

### Stap 1: Locaties scannen van een verdacht bedrijf
```powershell
python -m gbp_sentinel scan --name "Voorbeeld Bedrijf B.V." --queries "Voorbeeld Bedrijf, Voorbeeld Bedrijf Amsterdam, Voorbeeld Bedrijf Rotterdam" --kvk "12345678" --hq "Hoofdstraat 1, 1000 AA Amsterdam"
```

### Stap 2: Locaties auditeren op Google-overtredingen
```powershell
python -m gbp_sentinel audit --target "Voorbeeld Bedrijf B.V."
```

### Stap 3: Dossier en verklaringstekst genereren
```powershell
python -m gbp_sentinel dossier --target "Voorbeeld Bedrijf B.V."
```

### Stap 4: Klacht automatisch indienen bij Google
```powershell
python -m gbp_sentinel submit --target "Voorbeeld Bedrijf B.V."
```
*Na indiening verschijnt het officiële Google Case ID in de terminal en staat de forumbeschrijving automatisch op je Windows-klembord.*

### Stap 5: Forumbericht genereren voor bestaande case
```powershell
python -m gbp_sentinel forum --target "Voorbeeld Bedrijf B.V." --case-id "2-9725000041046"
```

---

## 4. Reeds geregistreerde en ingediende dossiers

1. **PC Refresh**
   - KvK: `54482844`
   - Overtreding: 49 drop-off inleverpunten vermomd als computerreparatiewinkels
   - Google Case ID: `4-8919000041358`
2. **Dak Advies Groep B.V.**
   - KvK: `93618166` (secundair `97524336`)
   - Overtreding: 21 virtuele kantoren (Spaces, Regus) en onbemande satellietadressen
   - Google Case ID: `2-9725000041046`
