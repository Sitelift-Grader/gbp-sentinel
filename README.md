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
python -m gbp_sentinel submit --target "Voorbeeld Bedrijf B.V." --confirm
```
Zonder `--confirm` wordt niets ingediend. Een Case ID betekent alleen dat Google de klacht heeft ontvangen, niet dat de profielen zijn aangepast of verwijderd.

### Stap 5: Uitkomst opvolgen
```powershell
python -m gbp_sentinel update-case --case-id "2-9725000041046" --status actioned
python -m gbp_sentinel list
```
Gebruik `awaiting_google_review`, `follow_up_sent`, `actioned`, `no_action` of `closed` uitsluitend na handmatige controle van de Google-uitkomst.

De `autopilot` en dagelijkse watchdog verzamelen standaard alleen signalen. Alleen `python -m gbp_sentinel.autopilot --niche "..." --name "..." --submit --confirm` mag een gecontroleerde batch extern indienen.

### Stap 6: Forumbericht genereren voor bestaande case
```powershell
python -m gbp_sentinel forum --target "Voorbeeld Bedrijf B.V." --case-id "2-9725000041046"
```

### Campagnemodus voor syndicates
```powershell
python -m gbp_sentinel campaign --batch-size 20
```
Hiermee maakt GBP Sentinel per overtredingstype bewijsgebonden CSV-batches, een `manifest.json` en een verzendwachtrij in `dossiers/campaigns/`. Alleen locaties met status `ready_for_review` en meerdere sterke bewijssignalen worden meegenomen. De opdracht verstuurt zelf niets extern.

---

## 4. Het 3-traps escalatieprotocol (SOP)

Om te waarborgen dat elk dossier altijd in de juiste categorie en op de juiste Google- en forumlinks wordt geplaatst, hanteert het platform een vaste 3-traps routing:

1. **Trap 1: Google Business Redressal Formulier**
   - **URL**: `https://support.google.com/business/contact/business_redressal_form?hl=en`
   - **Doel**: Het officiële CSV-bewijsdossier indienen en een uniek Google Case ID genereren.

2. **Trap 2: Google Bedrijfsprofiel Helpforum (Google Community)**
   - **URL**: `https://support.google.com/business/thread/new?hl=en`
   - **Verplichte Categorie**: **`Policies and guidelines`** (Nederlands: *Beleid en richtlijnen*)
   - **Actief Hoofdtopic**: `https://support.google.com/business/thread/469151040` (Thread ID: `469151040`)
   - **Doel**: Het dossier vastleggen op Google's eigen platform. Alleen hier beschikken Google Product Experts (PEs) over de interne knop om een zaak door te zetten naar Google Trust en Safety Spam Engineering.

3. **Trap 3: Local Search Forum (Sterling Sky)**
   - **Sectie**: `Spam on Google` (`https://localsearchforum.com/forums/spam-on-google.109/`)
   - **Master Topic**: `https://localsearchforum.com/threads/massive-coordinated-google-maps-spam-syndicate-across-the-netherlands-918-listings-64-redressal-case-ids.63398/`
   - **Aan te spreken expert**: `@keyserholiday` (Jason Brown, Diamond Product Expert)
   - **Doel**: De Product Expert direct voorzien van de link en het Thread ID van Google Help, zodat de interne escalatie direct wordt geactiveerd.

---

## 5. Actuele status database (`data/cases.db`)

- **Totaal aantal officiële Google Redressal dossiers**: 73
- **Totaal aantal gedocumenteerde locaties**: 1.060
- **Master escalatiedossier**: `dossiers/STERLING_SKY_MASTER_DOSSIER.md`
