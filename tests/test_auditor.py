import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbp_sentinel.auditor import GbpAuditor

def test_virtual_office_detection():
    auditor = GbpAuditor()
    loc = {
        "name": "Dakdekker Rotterdam | Dak Advies Groep",
        "address": "Hofplein 20, 3032 AC Rotterdam",
        "snippet": "Dakdekker · 20 Hofplein | Spaces Hofplein"
    }
    res = auditor.audit_location(loc, target_hq="Naarderweg 16, Hilversum", target_kvk="93618166")
    assert res["is_fraud"] is True
    assert res["violation_category"] == "virtual_office"
    assert "Spaces" in res["actual_occupant"] or "Hofplein 20" in res["actual_occupant"]
    assert "93618166" in res["kvk_status"]

def test_parcel_dropoff_detection():
    auditor = GbpAuditor()
    loc = {
        "name": "PC Refresh Inleverpunt 's-Hertogenbosch (Primera)",
        "address": "Rijnstraat 493A, 5215 EJ 's-Hertogenbosch",
        "snippet": "Primera winkel en pakketpunt"
    }
    res = auditor.audit_location(loc, target_hq="Stephensonstraat 48, Den Haag", target_kvk="54482844")
    assert res["is_fraud"] is True
    assert res["violation_category"] == "parcel_dropoff"
    assert "Primera" in res["actual_occupant"]

def test_headquarters_is_clean():
    auditor = GbpAuditor()
    loc = {
        "name": "PC Refresh Den Haag (Hoofdvestiging)",
        "address": "Stephensonstraat 48, 2561 XW Den Haag",
        "snippet": "Computer reparatie Den Haag eigen werkplaats"
    }
    res = auditor.audit_location(loc, target_hq="Stephensonstraat 48, 2561 XW Den Haag", target_kvk="54482844")
    assert res["is_fraud"] is False
    assert res["violation_category"] == "headquarters"

if __name__ == "__main__":
    test_virtual_office_detection()
    test_parcel_dropoff_detection()
    test_headquarters_is_clean()
    print("All auditor tests passed successfully!")
