"""Multi-stakeholder escalation and dispatch manager for GBP Sentinel.

Prepares and dispatches formal evidence packages, legal notices, and regulatory complaints
to key enforcement bodies, trade associations, and investigative media:
- AVROTROS Radar onderzoeksredactie (radar@avrotros.nl)
- NOA Nederlandse Ondernemersvereniging voor Afbouwbedrijven (info@noa.nl)
- Techniek Nederland (info@technieknederland.nl)
- Bouwend Nederland (info@bouwendnederland.nl)
- Holland Solar (info@hollandsolar.nl)
- Stichting Reclame Code (RCC)
- Autoriteit Persoonsgegevens (AP)
"""

import email
import email.mime.application
import email.mime.multipart
import email.mime.text
import os
import re
import smtplib
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, db


class EscalationManager:
    """Manages multi-channel escalation notices and dossier packages."""

    def __init__(self, output_base_dir: Optional[Path] = None):
        self.output_base_dir = Path(output_base_dir) if output_base_dir else config.DOSSIERS_DIR / "escalations"
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_\-]+", "_", text).strip("_").lower()

    def generate_radar_notice(
        self,
        target_name: str,
        kvk: str,
        hq: str,
        website: str,
        gtm: str,
        phone: str,
        total_sites: int,
        csv_path: Path
    ) -> Dict[str, str]:
        """Generate formal notification for AVROTROS Radar investigative desk."""
        subject = f"Onderzoeksdossier n.a.v. uitzending: compleet netwerk {target_name} ({total_sites} geverifieerde websites)"
        body = f"""Beste redactie van AVROTROS Radar,
T.a.v. Giva en het onderzoeksteam,

Naar aanleiding van jullie recente uitzending 'De wereld van de leads en de valse beloftes' (YouTube-referentie: WfKFeZ0d4GI) over leadgeneratie en de betrokkenheid van BesteLeads / Compleet Vloeren, hebben wij een diepgaand technisch en netwerkonderzoek uitgevoerd naar de organisatie achter deze websites.

Tijdens het kantoorbezoek in Apeldoorn gaf directeur Marco Zweekhorst (Kies Je Leverancier B.V.) aan dat het slechts zou gaan om enkele verouderde pagina's en dat er gewerkt werd aan aanpassingen op hun websites.

Uit onze geautomatiseerde footprint-scan en DNS-analyse blijkt echter dat het niet gaat om een incident, maar om een actief gecoördineerd netwerk van minstens {total_sites} websites die nog altijd live staan:

Kerngegevens van het netwerk:
- Entiteit: Kies Je Leverancier B.V.
- KvK: {kvk}
- Vestigingsadres: {hq}
- Hoofdplatform: {website} (en VrijblijvendeOfferte.nl)
- Gedeelde tracking footprint: Google Tag Manager container {gtm} op alle sites
- Centrale telefonie: {phone}

Belangrijkste bevindingen:
1. Schaal: Er zijn inmiddels {total_sites} afzonderlijke klussites en actiedomeinen geverifieerd (waaronder vloerverwarmingactie.nl, warmtepompactie.nl, bestewarmtepomp.nl, dakdekkeractie.nl, bestegietvloer.nl en vele anderen).
2. Voortdurende misleiding: Op vrijwel al deze websites wordt nog altijd beweerd dat de werkzaamheden worden uitgevoerd door 'eigen betrouwbare monteurs', met 'eigen bussen' en 'zonder externe partijen'.
3. Consumentenschade: Dit netwerk fungeert structureel als trechter om consumentenleads door te spelen aan tussenpersonen en onderaannemers met provisies tot 3.000 euro bovenop de reële marktprijs.

In de bijlage treft u het complete CSV-dossier aan met alle {total_sites} domeinen, URL's en specificaties. Wij hopen dat dit dossier bijdraagt aan jullie vervolgonderzoek en mogelijke vervolguitzending.

Met vriendelijke groet,

{config.SUBMITTER_NAME}
{config.SUBMITTER_ORG}
Contact: {config.SUBMITTER_EMAIL}
"""
        return {
            "recipient": "radar@avrotros.nl",
            "subject": subject,
            "body": body,
            "category": "media"
        }

    def generate_branch_notice(
        self,
        org_code: str,
        target_name: str,
        kvk: str,
        hq: str,
        website: str,
        gtm: str,
        phone: str,
        total_sites: int,
        csv_path: Path
    ) -> Dict[str, str]:
        """Generate formal notice for trade associations (NOA, Techniek Nederland, etc.)."""
        org_map = {
            "noa": {
                "name": "NOA (Nederlandse Ondernemersvereniging voor Afbouwbedrijven)",
                "email": "info@noa.nl",
                "sector": "afbouw-, vloeren- en gietvloerensector"
            },
            "technieknederland": {
                "name": "Techniek Nederland",
                "email": "info@technieknederland.nl",
                "sector": "installatiebranche (warmtepompen, cv-ketels, vloerverwarming en klimaattechniek)"
            },
            "bouwendnederland": {
                "name": "Bouwend Nederland",
                "email": "info@bouwendnederland.nl",
                "sector": "bouw- en aannemerssector"
            },
            "hollandsolar": {
                "name": "Holland Solar",
                "email": "info@hollandsolar.nl",
                "sector": "zonne-energie en thuisbatterijensector"
            }
        }

        meta = org_map.get(org_code.lower(), {
            "name": "Brancheorganisatie",
            "email": "info@brancheorganisatie.nl",
            "sector": "ambachtelijke en technische sector"
        })

        subject = f"Melding oneerlijke concurrentie en leadmisleiding: {target_name} ({total_sites} websites)"
        body = f"""Geacht bestuur en juridische afdeling van {meta['name']},

Hierbij brengen wij een omvangrijk dossier onder uw aandacht over structurele oneerlijke concurrentie en misleidende handelspraktijken die de {meta['sector']} ernstig schaden.

Het betreft het georganiseerde leadgeneratienetwerk rondom Kies Je Leverancier B.V. (KvK {kvk}, {hq}), handelend onder BesteLeads.nl en VrijblijvendeOfferte.nl.

Samenvatting van de schendingen:
1. Misleidende identiteit: Dit netwerk exploiteert minstens {total_sites} websites die zich voordoen als uitvoerend vakbedrijf met 'eigen monteurs' en 'eigen bussen'.
2. Schade aan erkende vakbedrijven: Bonafide bedrijven die aangesloten zijn bij uw brancheorganisatie worden in de zoekresultaten weggedrukt door deze misleidende leadportalen.
3. Doorverkoop aan dubieuze partijen: Zoals recent onthuld door AVROTROS Radar, worden consumentenleads geveild en doorgeschoven naar niet-gekwalificeerde partijen en tussenpersonen die torenhoge provisies rekenen.
4. Gedeelde infrastructuur: Alle {total_sites} domeinen zijn technisch gecentraliseerd onder Google Tag Manager container {gtm} en telefoonnummer {phone}.

Wij verzoeken uw organisatie om dit dossier te toetsen op oneerlijke handelspraktijken en te onderzoeken of collectieve juridische stappen of een gezamenlijk handhavingsverzoek bij de ACM opportuun zijn.

Het volledige overzicht met alle {total_sites} geverifieerde domeinen is als CSV bijgevoegd.

Met collegiale groet,

{config.SUBMITTER_NAME}
{config.SUBMITTER_ORG}
Contact: {config.SUBMITTER_EMAIL}
"""
        return {
            "recipient": meta["email"],
            "subject": subject,
            "body": body,
            "category": "trade_association"
        }

    def generate_rcc_complaint(
        self,
        target_name: str,
        kvk: str,
        hq: str,
        website: str,
        total_sites: int,
        csv_path: Path
    ) -> Dict[str, str]:
        """Generate complaint payload for Stichting Reclame Code (RCC)."""
        subject = f"Formele klacht wegens misleidende reclame: {target_name} (art. 7 en 8 NRC)"
        body = f"""Aan de Reclame Code Commissie (Stichting Reclame Code),

Hierbij dienen wij een formele klacht in tegen Kies Je Leverancier B.V. (KvK {kvk}, gevestigd aan {hq}), handelend onder BesteLeads.nl en VrijblijvendeOfferte.nl.

Grondslag van de klacht:
Overtreding van artikel 7 en artikel 8 van de Nederlandse Reclame Code (NRC) betreffende misleidende reclame en misleidende omissies.

Omschrijving van de misleiding:
Verweerder exploiteert een netwerk van ruim 100 commerciële websites (waaronder vloerverwarmingactie.nl, warmtepompactie.nl, bestewarmtepomp.nl, dakdekkeractie.nl). Op deze websites worden expliciet de volgende claims gedaan:
- 'Vakkundig geïnstalleerd door eigen betrouwbare monteurs'
- 'Wij werken niet met externe partijen of zzp'ers; we hebben onze eigen bussen en eigen mensen'

In werkelijkheid voert verweerder zelf geen enkele installatie of vakwerkzaamheid uit en heeft zij geen monteurs of bussen in dienst. Verweerder fungeert uitsluitend als leadbroker die consumentengegevens doorverkoopt aan derden.

Er is sprake van essentiële misleiding over:
1. De hoedanigheid en bekwaamheid van de adverteerder (art. 8.2 sub b NRC).
2. De identiteit van de uitvoerende partij (art. 8.2 sub e NRC).

Verzoek aan de Commissie:
De uitingen op het netwerk van verweerder in strijd met de NRC te verklaren en een openbare aanbeveling te doen. Bijgevoegd vindt u het CSV-overzicht van het netwerk.

Indiener:
{config.SUBMITTER_NAME} ({config.SUBMITTER_ORG})
E-mail: {config.SUBMITTER_EMAIL}
"""
        return {
            "recipient": "klacht@reclamecode.nl",
            "subject": subject,
            "body": body,
            "category": "advertising_standards"
        }

    def generate_ap_notice(
        self,
        target_name: str,
        kvk: str,
        hq: str,
        website: str,
        gtm: str,
        total_sites: int,
        csv_path: Path
    ) -> Dict[str, str]:
        """Generate privacy / GDPR enforcement complaint for Autoriteit Persoonsgegevens."""
        subject = f"Handhavingsverzoek AVG / GDPR: grootschalige onrechtmatige handel in persoonsgegevens door {target_name}"
        body = f"""Aan de Autoriteit Persoonsgegevens (AP),
Afdeling Toezicht en Handhaving,

Betreft: Handhavingsverzoek wegens structurele overtreding van de Algemene Verordening Gegevensbescherming (AVG).

Beklaagde rechtspersoon:
Kies Je Leverancier B.V. (KvK {kvk})
Boogschutterstraat 1, 7324 AE Apeldoorn
Directie: Marco Zweekhorst

Feiten en schendingen AVG:
1. Onrechtmatige verwerking zonder geldige rechtsgrond (art. 6 lid 1 AVG):
Beklaagde verzamelt persoonsgegevens (naam, adres, telefoonnummer, woninggegevens) via minstens {total_sites} misleidende landingspagina's onder het voorwendsel een offerte van het getoonde vakbedrijf uit te brengen. Vervolgens worden deze persoonsgegevens geveild en doorverkocht aan externe tussenpersonen en derden.

2. Ontbreken van specifieke en geïnformeerde toestemming (art. 7 AVG):
Er is geen sprake van geldige, vrije, specifieke en ondubbelzinnige toestemming van de betrokkene voor doorgifte aan de specifieke afnemers. Betrokkenen weten niet wie hun gegevens ontvangt.

3. Misleidende verwerkingsdoeleinden (art. 5 lid 1 sub a en b AVG):
Het beginsel van behoorlijkheid en transparantie wordt geschonden doordat beklaagde haar rol als datahandelaar verhult achter claims over 'eigen monteurs'.

Gezien de schaal ({total_sites} actieve websites) en de aantoonbare consumentenschade verzoeken wij de Autoriteit Persoonsgegevens om handhavend op te treden.

Indiener:
{config.SUBMITTER_NAME} ({config.SUBMITTER_ORG})
E-mail: {config.SUBMITTER_EMAIL}
"""
        return {
            "recipient": "info@autoriteitpersoonsgegevens.nl",
            "subject": subject,
            "body": body,
            "category": "privacy_regulator"
        }

    def generate_afm_complaint(
        self,
        target_name: str,
        kvk: str,
        hq: str,
        website: str,
        total_sites: int,
        csv_path: Path
    ) -> Dict[str, str]:
        """Generate financial conduct complaint for Autoriteit Financiele Markten (AFM)."""
        subject = f"Handhavingsverzoek Wft en oneerlijke handelspraktijken: Finance Prospects B.V. (vergunning 12019228 / KvK 08196184)"
        body = f"""Aan de Autoriteit Financiele Markten (AFM),
Afdeling Toezicht Financiele Dienstverlening,

Betreft: Signaal oneerlijke handelspraktijken en schending van informatieplichten door vergunninghouder Finance Prospects B.V.

Gegevens van de onder toezicht staande entiteit:
- Bedrijfsnaam: Finance Prospects B.V. (handelend onder o.a. Nationaal Bespaarcentrum, Duurzaam Lenen, Hypotheek Connect)
- AFM-vergunningnummer: 12019228
- KvK-nummer: 08196184
- Vestigingsadres: Boogschutterstraat 1, 7324 AE Apeldoorn (verzamelgebouw Toren Noord)

Omschrijving van de overtredingen en gedragingen:
1. Misleidende benaming en autoriteitssuggestie (art. 4:19 Wft):
Onder de handelsnaam 'Nationaal Bespaarcentrum' (nationaalbespaarcentrum.nl) wordt bij consumenten de indruk gewekt dat het om een onafhankelijk, door de overheid ingesteld of gesubsidieerd nationaal bespaarinstituut gaat. In werkelijkheid betreft het een commerciele leadgenerator die aanvragen voor hypotheken en verduurzamingsleningen doorverkoopt aan aangesloten provisiebetalende hypotheekkantoren.

2. Ontbreken van transparantie over leadverkoop en verdienmodel:
Consumenten die rekenmodules en bespaarchecks invullen op platforms zoals nationaalbespaarcentrum.nl en duurzaamlenen.nl, worden onvoldoende en misleidend geinformeerd dat hun gegevens worden geveild als commerciele lead. De bezoeker denkt een onafhankelijke berekening uit te voeren, maar wordt vervolgens gebeld door externe commerciele adviseurs.

3. Cluster van satelliet-leadgen portals:
Vergunninghouder exploiteert vanuit hetzelfde adres (Boogschutterstraat 1 te Apeldoorn) ruim 20 satellietdomeinen (waaronder hypotheek-berekenen.nl, hypotheek-check.nu, overwaardeverzilveren.nl, verduurzaam-hypotheek.nl, watispayroll.nl) die uitsluitend fungeren als leadtrechter.

4. Samenloop op hetzelfde verzameladres:
Op ditzelfde kantooradres (Boogschutterstraat 1 Apeldoorn) opereert tevens het beruchte leadgenbedrijf Kies Je Leverancier B.V. (104+ websites, recent ontmaskerd door AVROTROS Radar wegens grootschalige consumentenmisleiding en doorverkoop van klusleads).

Verzoek aan de AFM:
Wij verzoeken de AFM te toetsen of Finance Prospects B.V. handelt conform de integriteits- en zorgplichtnormen van de Wft en passende handhavingsmaatregelen te treffen.

Bijlage: CSV-dossier van het netwerk op Boogschutterstraat 1 Apeldoorn.

Melder:
{config.SUBMITTER_NAME} ({config.SUBMITTER_ORG})
E-mail: {config.SUBMITTER_EMAIL}
"""
        return {
            "recipient": "ondernemersloket@afm.nl",
            "subject": subject,
            "body": body,
            "category": "financial_regulator"
        }

    def generate_acm_formal_report(
        self,
        target_name: str,
        kvk: str,
        hq: str,
        website: str,
        total_sites: int,
        csv_path: Path
    ) -> Dict[str, str]:
        """Generate comprehensive enforcement dossier for Autoriteit Consument en Markt (ACM)."""
        subject = f"Handhavingsverzoek wet oneerlijke handelspraktijken: leadgeneratie-hub Boogschutterstraat 1 Apeldoorn ({total_sites} websites)"
        body = f"""Aan de Autoriteit Consument en Markt (ACM),
Directie Consumenten en Handhaving,

Betreft: Handhavingsverzoek wegens structurele overtreding van de Wet oneerlijke handelspraktijken (art. 6:193a e.v. BW) door leadgeneratiebedrijven gevestigd aan Boogschutterstraat 1, 7324 AE Apeldoorn (Toren Noord).

Betrokken entiteiten:
1. Kies Je Leverancier B.V. (KvK 57722102) / BesteLeads.nl / VrijblijvendeOfferte.nl
2. Finance Prospects B.V. (KvK 08196184, AFM 12019228) / Nationaal Bespaarcentrum / Duurzaam Lenen

Feiten en schendingen:
1. Misleidende consumentenclaims (art. 6:193c BW):
Kies Je Leverancier B.V. exploiteert 104+ websites (zoals vloerverwarmingactie.nl, warmtepompactie.nl, debestedakdekker.nl) waarop expliciet wordt gegarandeerd dat het werk wordt uitgevoerd door 'eigen monteurs' met 'eigen bussen'. In werkelijkheid heeft het bedrijf geen monteurs en worden aanvragen als lead geveild aan tussenpersonen met enorme opslagen. Deze praktijk is nationaal ontmaskerd in AVROTROS Radar (september 2026, YouTube WfKFeZ0d4GI).

2. Misleidende autoriteit en schijnonafhankelijkheid:
Finance Prospects B.V. opereert onder namen zoals 'Nationaal Bespaarcentrum' om de schijn van een onafhankelijke instantie te wekken, waarna financiele en hypotheekaanvragen worden doorverkocht.

3. Schaal en maatschappelijke impact:
Het cluster op Boogschutterstraat 1 telt in totaal {total_sites} geverifieerde websites die landelijk adverteren en consumenten systematisch misleiden over de identiteit van de dienstverlener en de totstandkoming van de prijs.

Wij verzoeken de ACM om ambtshalve een onderzoek in te stellen en handhavend op te treden met een last onder dwangsom en/of bestuurlijke boete.

Bijgevoegd: Volledig CSV-dossier met alle {total_sites} domeinen en overtredingen.

Indiener:
{config.SUBMITTER_NAME} ({config.SUBMITTER_ORG})
E-mail: {config.SUBMITTER_EMAIL}
"""
        return {
            "recipient": "handhaving@acm.nl",
            "subject": subject,
            "body": body,
            "category": "market_regulator"
        }

    def create_eml_file(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        attachment_path: Path,
        output_dir: Path
    ) -> Path:
        """Create a standard RFC-822 .eml file with plain text body and attached CSV."""
        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = f"{config.SUBMITTER_NAME} <{config.SUBMITTER_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain="gbp-sentinel.local")

        # Attach text body
        text_part = email.mime.text.MIMEText(body_text, "plain", "utf-8")
        msg.attach(text_part)

        # Attach CSV file if exists
        attachment_path = Path(attachment_path)
        if attachment_path.exists():
            with open(attachment_path, "rb") as f:
                csv_data = f.read()
            app_part = email.mime.application.MIMEApplication(csv_data, _subtype="csv")
            app_part.add_header("Content-Disposition", "attachment", filename=attachment_path.name)
            msg.attach(app_part)

        safe_filename = self._slugify(to_email + "_" + subject[:30]) + ".eml"
        eml_path = output_dir / safe_filename
        with open(eml_path, "wb") as f:
            f.write(msg.as_bytes())

        return eml_path

    def dispatch_all(
        self,
        target_name: str,
        kvk: str,
        hq: str,
        website: str,
        gtm: str,
        phone: str,
        csv_path: Path
    ) -> Dict[str, Any]:
        """Generate and package formal escalation dossiers for all stakeholders."""
        csv_path = Path(csv_path).resolve()
        target_slug = self._slugify(target_name)
        target_dir = self.output_base_dir / target_slug
        target_dir.mkdir(parents=True, exist_ok=True)

        # Count total sites from CSV
        total_sites = 0
        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8") as f:
                total_sites = max(0, sum(1 for _ in f) - 1)

        # Build notices
        notices = [
            self.generate_radar_notice(target_name, kvk, hq, website, gtm, phone, total_sites, csv_path),
            self.generate_branch_notice("noa", target_name, kvk, hq, website, gtm, phone, total_sites, csv_path),
            self.generate_branch_notice("technieknederland", target_name, kvk, hq, website, gtm, phone, total_sites, csv_path),
            self.generate_branch_notice("bouwendnederland", target_name, kvk, hq, website, gtm, phone, total_sites, csv_path),
            self.generate_branch_notice("hollandsolar", target_name, kvk, hq, website, gtm, phone, total_sites, csv_path),
            self.generate_rcc_complaint(target_name, kvk, hq, website, total_sites, csv_path),
            self.generate_ap_notice(target_name, kvk, hq, website, gtm, total_sites, csv_path),
        ]

        results = []
        smtp_host = os.environ.get("SMTP_HOST")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASS")

        for item in notices:
            eml_path = self.create_eml_file(
                to_email=item["recipient"],
                subject=item["subject"],
                body_text=item["body"],
                attachment_path=csv_path,
                output_dir=target_dir
            )

            dispatch_status = "packaged_as_eml"
            error_msg = ""

            # Attempt SMTP if environment is configured
            if smtp_host and smtp_user and smtp_pass:
                try:
                    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        # Read raw eml bytes
                        with open(eml_path, "rb") as f:
                            raw_msg = f.read()
                        server.sendmail(config.SUBMITTER_EMAIL, [item["recipient"]], raw_msg)
                    dispatch_status = "sent_via_smtp"
                except Exception as e:
                    dispatch_status = "smtp_failed"
                    error_msg = str(e)

            results.append({
                "recipient": item["recipient"],
                "subject": item["subject"],
                "category": item["category"],
                "eml_file": str(eml_path),
                "status": dispatch_status,
                "error": error_msg
            })

        return {
            "target_name": target_name,
            "total_sites": total_sites,
            "output_directory": str(target_dir),
            "dispatches": results
        }
