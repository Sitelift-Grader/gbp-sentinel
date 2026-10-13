import json
import csv
from pathlib import Path
from collections import defaultdict

def main():
    json_path = Path("dossiers/financieel_fit/master_audit_90_vestigingen.json")
    if not json_path.exists():
        print("Master audit JSON niet gevonden!")
        return

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # Identificeer gedeelde adressen
    by_addr = defaultdict(list)
    for d in data:
        addr = d.get("address", "").strip().lower()
        if addr and len(addr) > 5 and "apeldoorn, apeldoorn" not in addr:
            by_addr[addr].append(d)

    multi_address_slugs = {}
    for addr, locs in by_addr.items():
        if len(locs) > 1:
            for l in locs:
                multi_address_slugs[l["slug"]] = {
                    "total_on_addr": len(locs),
                    "shared_with": [x["slug"] for x in locs if x["slug"] != l["slug"]],
                    "raw_addr": addr
                }

    redressal_rows = []
    for d in data:
        slug = d["slug"]
        city = d["city"]
        h1 = d["h1"]
        url = d["url"]
        addr = d["address"]
        tel = d["telephone"]
        schema = d.get("schema_name", "")

        violations = []
        action = "RENAME"

        if slug in multi_address_slugs:
            info = multi_address_slugs[slug]
            violations.append(f"Multi-profiel duplicaat ({info['total_on_addr']} vestigingen op exact hetzelfde adres)")
            addr_lower = addr.lower()
            if city.lower() not in addr_lower and slug not in ["financieel-fit-servicecenter"]:
                violations.append(f"Spooklocatie / Doorway profile (Claimt {city}, maar gevestigd in {addr})")
                action = "REMOVE_OR_MERGE"
            else:
                action = "MERGE_DUPLICATE"
        else:
            violations.append("Systematische Title Keyword Stuffing")

        correct_name = h1 if h1 else f"Financieel Fit | {city}"

        redressal_rows.append({
            "slug": slug,
            "stad": city,
            "officiële_naam_h1": correct_name,
            "schema_handelsnaam": schema,
            "aanbevolen_handhaving": action,
            "overtredingen": " | ".join(violations),
            "fysiek_adres": addr,
            "telefoonnummer": tel,
            "landingspagina_url": url,
            "bewijslast_h1": f"Website H1 bewijst: '{h1}'"
        })

    out_csv = Path("dossiers/financieel_fit/master_redressal_dossier.csv")
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(redressal_rows[0].keys()))
        writer.writeheader()
        writer.writerows(redressal_rows)

    # Genereer tevens het officiële dossier Markdown document
    dossier_md = Path("dossiers/financieel_fit/GOOGLE_REDRESSAL_COMPLAINT_FINANCIEEL_FIT.md")
    
    md_content = f"""# Google Business Profile Redressal Complaint: Financieel Fit Network

**Datum:** {Path(".").resolve()}  
**Doelwit:** Financieel Fit B.V. / Yellow Hive B.V.  
**Hoofdkantoor:** Van Dedemstraat 198, 4611 BE Bergen op Zoom  
**Website:** https://www.financieelfit.nl  
**Totaal geanalyseerde locaties:** {len(redressal_rows)}  

---

## 1. Samenvatting van Beleidsschendingen

Financieel Fit maakt zich op landelijke schaal schuldig aan drie ernstige schendingen van de Google Bedrijfsprofiel richtlijnen:

### Schending A: Systematische Title Keyword Stuffing (Representing your business on Google)
Op hun officiële website (`financieelfit.nl`) en in hun Schema.org (`FinancialService`) is de handelsnaam van elke vestiging consistent vastgelegd als:
* `Financieel Fit | [Plaats]` (bv. `Financieel Fit | Weert`)

Op Google Maps voegen franchisenemers en adviseurs landelijk echter ongeoorloofde diensten en persoonsnamen toe:
* *Voorbeeld Weert:* `Financieel Fit Weert I Marc op 't Roodt - Hypotheken, Verzekeringen & Financieel Advies`
* *Voorbeeld Almere:* `Financieel Fit – Hypotheken, Verzekeringen & Financieel Advies in Almere`
* *Voorbeeld Capelle:* `Financieel Fit | Capelle aan den IJssel - Hypotheken, Verzekeringen & Financieel Advies in Capelle aan den IJssel`

### Schending B: Spooklocaties / Doorway Profiles (Misleidende geografische claims)
Profielen worden geclaimd in grote steden waar de entiteit geen fysiek kantoor heeft:
* **Zwolle:** Geclaimd als Zwolle, maar het fysieke adres staat in **Hoogeveen** (*De Vos van Steenwijklaan 75*).
* **Groningen:** Geclaimd als Groningen, maar gevestigd in **Zuidbroek** (*Vledders 7*).
* **Amersfoort Centrum:** Geclaimd in Amersfoort, maar het fysieke adres is in **Soest** (*1e Heezerlaantje 3*).
* **Amstelveen:** Geclaimd in Amstelveen, maar gevestigd op hetzelfde kantoor als **Amsterdam West** (*Hillegomstraat 44, Amsterdam*).

### Schending C: Co-located Multi-Profile Spam (Meerdere profielen op 1 adres)
* **Markt 14, Asten (4 profielen!):**
  1. `Financieel Fit | Asten`
  2. `Financieel Fit | Frank Coolen`
  3. `Financieel Fit | Johan Schriks`
  4. `Financieel Fit | Pieter van Leenders`
* **Berkstraat 100, Oldenzaal (3 profielen!):**
  1. `Financieel Fit | Ellen Postma`
  2. `Financieel Fit | Postma`
  3. `Financieel Fit | Richard Kunst`
* **Hoofdstraat 160-162, Hillegom:**
  1. `Financieel Fit | Hillegom | ’t Spectrum`
  2. `De Hypotheekadviseur Hillegom - Financieel Spectrum`
  3. `Financieel Adviesbureau Adamse`

---

## 2. Gevraagde Handhaving door Google Trust & Safety

1. **Naamsanering (RENAME):** Alle profielen verplichten de naam terug te zetten naar de officiële handelsnaam op de website (`Financieel Fit | [Plaats]`), conform bijgevoegde spreadsheet.
2. **Duplicaten Verwijderen/Samenvoegen (MERGE / REMOVE):** De multi-profielen op Markt 14 te Asten, Berkstraat 100 te Oldenzaal en Hoofdstraat te Hillegom reduceren tot maximaal 1 geverifieerd profiel.
3. **Spooklocaties opschorten (SUSPEND):** Profielen waarvan de geclaimde stad afwijkt van het fysieke adres (Zwolle vanuit Hoogeveen, Groningen vanuit Zuidbroek) verwijderen wegens misleiding van consumenten.

---

## 3. Spreadsheet Bijlage
Zie het volledige tabellarische overzicht met alle 90 locaties:  
`dossiers/financieel_fit/master_redressal_dossier.csv`
"""
    dossier_md.write_text(md_content, encoding="utf-8")

    print(f"Master redressal CSV opgeslagen: {out_csv} ({len(redressal_rows)} locaties)")
    print(f"Master redressal Dossier opgeslagen: {dossier_md}")

if __name__ == "__main__":
    main()
