"""CLI interface for GBP Sentinel."""

import argparse
import sys
import json
from pathlib import Path
from . import campaign, config, db, auditor, dossier, forum, investigator, scraper, submitter, verify_cases, liveness, export_master_escalation, spam_scorer, network_intelligence

def cmd_init():
    """Initialize database and directories."""
    db.init_db()
    print("Database en directorystructuur zijn geïnitialiseerd.")

def cmd_scan(args):
    """Scan Google Maps for profiles."""
    db.init_db()
    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    if not queries:
        queries = [args.name]

    print(f"Starten van scan voor '{args.name}' met {len(queries)} zoekopdrachten...")
    sc = scraper.GbpScraper(headless=not args.headed)
    profiles = sc.run_search(queries)
    print(f"Scan voltooid: {len(profiles)} unieke profielen gevonden.")

    db.save_target(args.name, kvk=args.kvk or "", website=args.website or "", hq_address=args.hq or "")
    db.save_locations(args.name, profiles)
    print(f"Profielen opgeslagen in database voor target '{args.name}'.")

def cmd_audit(args):
    """Audit saved locations for policy violations."""
    target = db.get_target(args.target)
    if not target:
        print(f"Fout: Target '{args.target}' niet gevonden in database. Voer eerst een scan uit.")
        sys.exit(1)

    locations = db.get_locations(args.target)
    if not locations:
        print(f"Fout: Geen locaties gevonden voor '{args.target}'.")
        sys.exit(1)

    print(f"Auditeren van {len(locations)} locaties voor '{args.target}'...")
    ad = auditor.GbpAuditor()
    audited = ad.audit_locations(locations, target_hq=target.get("hq_address", ""), target_kvk=target.get("kvk", ""))
    
    fraud_count = sum(1 for loc in audited if loc.get("is_fraud"))
    print(f"Audit voltooid: {fraud_count} overtredingen gedetecteerd op {len(audited)} locaties.")
    
    # Update locations in DB
    db.save_target(args.target, kvk=target.get("kvk", ""), website=target.get("website", ""), hq_address=target.get("hq_address", ""))
    # replace locations with audited ones
    conn = db._get_connection()
    with conn:
        conn.execute("DELETE FROM locations WHERE target_name = ?", (args.target,))
    db.save_locations(args.target, audited)
    print("Geauditeerde locaties bijgewerkt in database.")

def cmd_dossier(args):
    """Export audited dossier to CSV and generate explanation text."""
    target = db.get_target(args.target)
    if not target:
        print(f"Fout: Target '{args.target}' niet gevonden.")
        sys.exit(1)

    locations = db.get_locations(args.target)
    if not locations:
        print(f"Fout: Geen locaties beschikbaar voor '{args.target}'.")
        sys.exit(1)

    reportable = [loc for loc in locations if loc.get("is_reportable", loc.get("is_fraud", False))]
    try:
        csv_path = dossier.export_dossier_csv(args.target, reportable)
    except ValueError as exc:
        print(f"Fout: {exc}")
        sys.exit(1)
    explanation = dossier.generate_explanation_text(
        target_name=args.target,
        target_kvk=target.get("kvk", ""),
        target_hq=target.get("hq_address", ""),
        total_locations=len(reportable)
    )

    print(f"Dossier CSV gegenereerd: {csv_path} ({len(reportable)} reviewklare locaties)")
    print(f"Verklaringstekst ({len(explanation)} tekens):\n")
    print(explanation)

def cmd_submit(args):
    """Submit redressal complaint to Google."""
    target = db.get_target(args.target)
    if not target:
        print(f"Fout: Target '{args.target}' niet gevonden.")
        sys.exit(1)

    locations = db.get_locations(args.target)
    if not locations:
        print(f"Fout: Geen locaties beschikbaar voor '{args.target}'.")
        sys.exit(1)

    if not args.confirm:
        print("Geen indiening uitgevoerd. Controleer het dossier en herhaal met --confirm om het formulier werkelijk te verzenden.")
        return

    reportable = [loc for loc in locations if loc.get("is_reportable", loc.get("is_fraud", False))]
    try:
        csv_path = dossier.export_dossier_csv(args.target, reportable)
    except ValueError as exc:
        print(f"Fout: {exc}")
        sys.exit(1)
    explanation = dossier.generate_explanation_text(
        target_name=args.target,
        target_kvk=target.get("kvk", ""),
        target_hq=target.get("hq_address", ""),
        total_locations=len(reportable)
    )

    print(f"Verzenden van Redressal-klacht voor '{args.target}' naar Google...")
    sub = submitter.RedressalSubmitter(headless=not args.headed)
    res = sub.run_submit(args.target, csv_path, explanation, public_url=args.url or "")

    print(f"Resultaat: {res.get('message')}")
    if res.get("case_id"):
        print(f"*** GOOGLE CASE ID ONTVANGEN: {res.get('case_id')} ***")
        db.save_submission(
            target_name=args.target,
            case_id=res.get("case_id"),
            email=config.SUBMITTER_EMAIL,
            dossier_path=str(csv_path),
            filled_screenshot=res.get("filled_screenshot"),
            result_screenshot=res.get("result_screenshot"),
            status="awaiting_google_review"
        )

        # Automatically copy forum payload
        payload = forum.build_community_payload(
            target_name=args.target,
            target_kvk=target.get("kvk", ""),
            target_hq=target.get("hq_address", ""),
            case_id=res.get("case_id"),
            audited_locations=locations
        )
        copied = forum.copy_to_clipboard(payload["body"])
        if copied:
            print("Community escalatietekst staat op het klembord.")
            print(f"Plaats het topic op: {payload['forum_url']}")

def cmd_forum(args):
    """Generate forum escalation text and copy to clipboard."""
    target = db.get_target(args.target)
    if not target:
        print(f"Fout: Target '{args.target}' niet gevonden.")
        sys.exit(1)

    locations = db.get_locations(args.target)
    payload = forum.build_community_payload(
        target_name=args.target,
        case_id=args.case_id,
        audited_locations=locations
    )

    copied = forum.copy_to_clipboard(payload["body"])
    print(f"Titel voor community:\n{payload['title']}\n")
    if copied:
        print("De forumbeschrijving is succesvol naar het klembord gekopieerd.")
    print(f"Open de communitypagina: {payload['forum_url']}")

def cmd_list():
    """List all registered targets and submissions."""
    db.init_db()
    targets = db.list_targets()
    submissions = db.list_submissions()

    print("\n--- Geregistreerde targets ---")
    if not targets:
        print("Geen targets geregistreerd.")
    else:
        for t in targets:
            print(f"- {t.get('name')} | KvK: {t.get('kvk') or 'N/A'} | HQ: {t.get('hq_address') or 'N/A'}")

    print("\n--- Ingediende klachten & Google Case ID's ---")
    if not submissions:
        print("Geen eerdere inzendingen geregistreerd.")
    else:
        for s in submissions:
            print(f"- Target: {s.get('target_name')} | Case ID: {s.get('case_id')} | Datum: {s.get('created_at')} | Status: {s.get('status')}")

    print("\n--- Opvolgstatus ---")
    for item in db.submission_status_summary():
        print(f"- {item['status']}: {item['total']}")

def cmd_update_case(args):
    """Record the observed Google outcome for a case."""
    db.init_db()
    updated = db.update_submission_status(args.case_id, args.status)
    if not updated:
        print(f"Fout: Case ID '{args.case_id}' niet gevonden.")
        sys.exit(1)
    print(f"Case {args.case_id} bijgewerkt naar: {args.status}")

def cmd_campaign(args):
    """Prepare evidence-gated batch dossiers for a coordinated reporting campaign."""
    db.init_db()
    try:
        manifest_path, manifest = campaign.build_campaign(args.target, args.batch_size)
    except FileExistsError:
        print("Fout: campagne-uitvoer bestaat al; probeer het opnieuw.")
        sys.exit(1)
    except ValueError as exc:
        print(f"Fout: {exc}")
        sys.exit(1)
    print(f"Campagne voorbereid: {manifest_path}")
    print(f"Reviewklare locaties: {manifest['total_review_ready_locations']} | batches: {len(manifest['batches'])}")
    print("Er is niets extern verstuurd. Controleer elke batch voordat je deze via de aangegeven route indient.")

def cmd_investigate(args):
    """Build a network evidence report from stored public listing data."""
    db.init_db()
    try:
        report_path, report = investigator.build_network_report(args.target, args.min_shared)
    except (FileExistsError, ValueError) as exc:
        print(f"Fout: {exc}")
        sys.exit(1)
    print(f"Netwerkrapport gemaakt: {report_path}")
    print(f"Bronprofielen: {report['source_profiles']} | mogelijke clusters: {len(report['clusters'])}")
    print("Clusters zijn onderzoekssignalen; beoordeel elk profiel voordat je een externe melding maakt.")

def cmd_follow_up(args):
    """Prepare a manual queue for checking outstanding Google cases."""
    db.init_db()
    try:
        queue_path, cases = investigator.build_follow_up_queue(args.days)
    except ValueError as exc:
        print(f"Fout: {exc}")
        sys.exit(1)
    print(f"Opvolgwachtrij gemaakt: {queue_path} ({len(cases)} cases)")

def cmd_confirm_case(args):
    """Record that the Google confirmation email was manually verified."""
    db.init_db()
    if not any(item.get("case_id") == args.case_id for item in db.list_submissions()):
        print(f"Fout: Case ID '{args.case_id}' niet gevonden.")
        sys.exit(1)
    db.save_case_event(args.case_id, "email_confirmation_verified", args.note or "")
    print(f"E-mailbevestiging geregistreerd voor case {args.case_id}.")

def cmd_score(args):
    """Bereken kwantificeerbare misbruik- en spamscores."""
    scorer = spam_scorer.GbpSpamScorer()
    if getattr(args, "name", None):
        loc = {
            "name": args.name,
            "address": getattr(args, "address", "") or "",
            "phone": getattr(args, "phone", "") or "",
            "actual_occupant": getattr(args, "address", "") or "",
            "city": getattr(args, "city", "") or ""
        }
        res = scorer.calculate_abuse_score(loc)
        kw = res["keyword_details"]
        print("=" * 60)
        print(f"SPAMSCORE ANALYSE: {args.name}")
        print("=" * 60)
        print(f"Overall Misbruikscore: {res['overall_score']} / 100 ({res['confidence']})")
        print(f"Keyword Stuffing Score: {kw['score']} / 100 ({kw['level']})")
        if kw.get("cleaned_brand_guess"):
            print(f"Gedetecteerde echte merknaam: '{kw['cleaned_brand_guess']}'")
        print("-" * 60)
        print("Gedetecteerde indicatoren:")
        for pt in res["evidence_points"]:
            print(f"  • {pt}")
        print("=" * 60)
        return

    if getattr(args, "target", None):
        locs = db.get_locations(args.target)
        if not locs:
            print(f"Geen locaties gevonden voor target '{args.target}'.")
            return
        print(f"Scoren van {len(locs)} locaties voor '{args.target}'...")
        scores = []
        for loc in locs:
            s = scorer.calculate_abuse_score(loc)
            scores.append((loc, s))
        
        avg_score = sum(s["overall_score"] for _, s in scores) / len(scores)
        print("=" * 60)
        print(f"TARGET RISICOPROFIEL: {args.target}")
        print(f"Totaal locaties: {len(locs)} | Gemiddelde misbruikscore: {avg_score:.1f} / 100")
        print("=" * 60)
        for loc, s in scores[:10]:
            name = loc.get("name", "Onbekend")[:35]
            city = loc.get("city", "")[:12]
            print(f"{name:<37} | {city:<12} | Score: {s['overall_score']:>3} ({s['confidence']})")
        if len(scores) > 10:
            print(f"... en nog {len(scores) - 10} andere locaties.")
        print("=" * 60)
        return

    print("Geef --target of --name op om te scoren.")

def cmd_network_report(args):
    """Genereer en exporteer de overkoepelende netwerkgraaf-analyse."""
    engine = network_intelligence.NetworkIntelligenceEngine()
    print("Analyseren van de gehele database voor netwerkclusters en syndicaten...")
    report_md = engine.generate_intelligence_markdown()
    
    out_path = Path("dossiers/NETWORK_INTELLIGENCE_REPORT.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"Netwerkanalyse opgeslagen in {out_path}")

    if getattr(args, "json", False):
        data = engine.analyze_network_graph()
        json_path = Path("dossiers/network_graph.json")
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Ruwe netwerkgraaf opgeslagen in {json_path}")

def cmd_dashboard(args=None):
    """Start het interactieve webdashboard."""
    import uvicorn
    host = getattr(args, "host", "127.0.0.1") if args else "127.0.0.1"
    port = getattr(args, "port", 8000) if args else 8000
    print("=" * 65)
    print(" GBP SMOKER — Google Maps Spam & Network Investigation Engine")
    print("=" * 65)
    print(f" Webdashboard actief op: http://{host}:{port}/")
    print(f" Lokale link:           http://localhost:{port}/")
    print("=" * 65)
    uvicorn.run("gbp_sentinel.api.server:app", host=host, port=port, reload=False)

def cmd_report(args):
    """Genereer een forensisch Markdown onderzoeksrapport."""
    from .report_generator import ReportGenerator
    rg = ReportGenerator()
    if getattr(args, "network", None):
        txt = rg.generate_network_report(args.network)
    elif getattr(args, "case", None):
        txt = rg.generate_case_report(args.case)
    else:
        print("Fout: Geef --network <id> of --case <id> op.")
        return
    if getattr(args, "output", None):
        Path(args.output).write_text(txt, encoding="utf-8")
        print(f"Rapport opgeslagen in {args.output}")
    else:
        print(txt)

def main():
    parser = argparse.ArgumentParser(description="GBP SMOKER: Google Maps Spam & Network Investigation Engine")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # dashboard & serve
    p_dash = subparsers.add_parser("dashboard", help="Start het interactieve webdashboard")
    p_dash.add_argument("--port", type=int, default=8000, help="Poortnummer (standaard: 8000)")
    p_dash.add_argument("--host", default="127.0.0.1", help="Hostadres (standaard: 127.0.0.1)")

    p_serve = subparsers.add_parser("serve", help="Start de REST API en webserver")
    p_serve.add_argument("--port", type=int, default=8000, help="Poortnummer (standaard: 8000)")
    p_serve.add_argument("--host", default="127.0.0.1", help="Hostadres (standaard: 127.0.0.1)")

    # report
    p_rep = subparsers.add_parser("report", help="Genereer forensisch Markdown onderzoeksrapport")
    p_rep.add_argument("--network", type=int, help="Netwerk ID (bijv. 1 of 11)")
    p_rep.add_argument("--case", type=int, help="Case ID (bijv. 1)")
    p_rep.add_argument("--output", help="Optioneel doelbestand (.md)")

    # init
    subparsers.add_parser("init", help="Initialiseer de database")

    # scan
    p_scan = subparsers.add_parser("scan", help="Scan Google Maps voor een bedrijf")
    p_scan.add_argument("--name", required=True, help="Officiële naam van het bedrijf")
    p_scan.add_argument("--queries", required=True, help="Komma-gescheiden zoekopdrachten")
    p_scan.add_argument("--kvk", help="KvK nummer")
    p_scan.add_argument("--website", help="Officiële website")
    p_scan.add_argument("--hq", help="Adres van de hoofdvestiging")
    p_scan.add_argument("--headed", action="store_true", help="Browser zichtbaar openen")

    # audit
    p_audit = subparsers.add_parser("audit", help="Voer fraude-audit uit op opgeslagen profielen")
    p_audit.add_argument("--target", required=True, help="Naam van het target")

    # dossier
    p_dossier = subparsers.add_parser("dossier", help="Exporteer CSV-dossier en verklaringstekst")
    p_dossier.add_argument("--target", required=True, help="Naam van het target")

    # submit
    p_submit = subparsers.add_parser("submit", help="Dien klacht in bij Google Redressal Form")
    p_submit.add_argument("--target", required=True, help="Naam van het target")
    p_submit.add_argument("--url", help="Publieke Maps URL")
    p_submit.add_argument("--headed", action="store_true", help="Browser zichtbaar openen")
    p_submit.add_argument("--confirm", action="store_true", help="Bevestig dat het gecontroleerde dossier werkelijk mag worden ingediend")

    # forum
    p_forum = subparsers.add_parser("forum", help="Genereer community escalatie en zet op klembord")
    p_forum.add_argument("--target", required=True, help="Naam van het target")
    p_forum.add_argument("--case-id", required=True, help="Google Case ID")

    # list
    subparsers.add_parser("list", help="Toon alle targets en submissions")

    p_update = subparsers.add_parser("update-case", help="Leg de handmatig gecontroleerde Google-uitkomst vast")
    p_update.add_argument("--case-id", required=True, help="Google Case ID")
    p_update.add_argument("--status", required=True, choices=["awaiting_google_review", "follow_up_sent", "actioned", "no_action", "closed"])

    p_campaign = subparsers.add_parser("campaign", help="Maak bewijsgebonden massameld-batches zonder ze te verzenden")
    p_campaign.add_argument("--target", help="Beperk de campagne tot één target")
    p_campaign.add_argument("--batch-size", type=int, default=20, help="Aantal locaties per batch (standaard: 20)")

    p_investigate = subparsers.add_parser("investigate", help="Vind herhaalde openbare netwerk-signalen tussen opgeslagen profielen")
    p_investigate.add_argument("--target", help="Beperk het onderzoek tot één target")
    p_investigate.add_argument("--min-shared", type=int, default=2, help="Minimaal gedeeld signaal per cluster (standaard: 2)")

    p_follow_up = subparsers.add_parser("follow-up", help="Maak een handmatige opvolgwachtrij voor bestaande Google Cases")
    p_follow_up.add_argument("--days", type=int, default=7, help="Minimale leeftijd van een case in dagen (standaard: 7)")

    p_confirm_case = subparsers.add_parser("confirm-case", help="Leg handmatige verificatie van de Google-bevestigingsmail vast")
    p_confirm_case.add_argument("--case-id", required=True, help="Google Case ID")
    p_confirm_case.add_argument("--note", help="Optionele notitie, bijvoorbeeld datum of onderwerpregel")

    p_verify = subparsers.add_parser("verify-cases", help="Beheer e-mailverificatie en Google Case statussen")
    p_verify.add_argument("--list", action="store_true", help="Toon cases die wachten op bevestiging")
    p_verify.add_argument("--verify-all", action="store_true", help="Markeer alle openstaande cases als geverifieerd")
    p_verify.add_argument("--verify", metavar="CASE_ID", help="Markeer een specifieke case als geverifieerd")
    p_verify.add_argument("--status", nargs=2, metavar=("CASE_ID", "STATUS"), help="Werk Google status bij")
    p_verify.add_argument("--summary", action="store_true", help="Toon verificatiestatistieken")

    p_liveness = subparsers.add_parser("check-liveness", help="Controleer actuele status van locaties op Google Maps")
    p_liveness.add_argument("--target", help="Controleer alle locaties van een specifiek target")
    p_liveness.add_argument("--id", type=int, help="Controleer een specifieke locatie per ID")
    p_liveness.add_argument("--all", action="store_true", help="Controleer alle locaties")
    p_liveness.add_argument("--limit", type=int, help="Maximaal aantal te controleren locaties")
    p_liveness.add_argument("--summary", action="store_true", help="Toon liveness samenvatting")

    p_score = subparsers.add_parser("score", help="Kwantificeerbare misbruik- en spamscores berekenen")
    p_score.add_argument("--target", help="Doelwitnaam in database")
    p_score.add_argument("--name", help="Enkele bedrijfsnaam om direct te scoren")
    p_score.add_argument("--address", help="Adres bij --name")
    p_score.add_argument("--phone", help="Telefoonnummer bij --name")
    p_score.add_argument("--city", help="Plaatsnaam bij --name")

    p_net = subparsers.add_parser("network-report", help="Genereer netwerk-analyse en clustering over alle locaties")
    p_net.add_argument("--json", action="store_true", help="Exporteer ook ruwe netwerkgraaf als JSON")

    subparsers.add_parser("export-master", help="Exporteer het geconsolideerde Sterling Sky masterrapport")

    args = parser.parse_args()

    if not args.command or args.command in ("dashboard", "serve"):
        cmd_dashboard(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "init":
        cmd_init()
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "audit":
        cmd_audit(args)
    elif args.command == "dossier":
        cmd_dossier(args)
    elif args.command == "submit":
        cmd_submit(args)
    elif args.command == "forum":
        cmd_forum(args)
    elif args.command == "list":
        cmd_list()
    elif args.command == "update-case":
        cmd_update_case(args)
    elif args.command == "campaign":
        cmd_campaign(args)
    elif args.command == "investigate":
        cmd_investigate(args)
    elif args.command == "follow-up":
        cmd_follow_up(args)
    elif args.command == "confirm-case":
        cmd_confirm_case(args)
    elif args.command == "verify-cases":
        if args.list or args.verify_all or args.verify or args.status:
            verify_cases.cli()
        else:
            verify_cases.print_summary()
    elif args.command == "check-liveness":
        if args.id:
            res = liveness.check_location(args.id)
            print(f"Locatie #{args.id}: {res['status']} - {res.get('details')}")
        elif args.target:
            liveness.check_target(args.target, limit=args.limit)
        elif args.all:
            liveness.check_all_locations(limit=args.limit)
        else:
            liveness.print_liveness_summary()
    elif args.command == "export-master":
        export_master_escalation.export_master_dossier()
    elif args.command == "score":
        cmd_score(args)
    elif args.command == "network-report":
        cmd_network_report(args)

if __name__ == "__main__":
    main()
