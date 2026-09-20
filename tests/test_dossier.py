import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbp_sentinel.dossier import export_dossier_csv, generate_explanation_text, REDRESSAL_COLUMNS
import csv

def test_explanation_under_1000_chars():
    text = generate_explanation_text(
        target_name="Test Bad Roofer B.V.",
        target_kvk="12345678",
        target_hq="Teststraat 1, Amsterdam",
        total_locations=45
    )
    assert len(text) <= 1000, f"Text length {len(text)} exceeds 1000 limit!"
    assert "Test Bad Roofer B.V." in text
    assert "12345678" in text

def test_csv_export_format(tmp_path=None):
    dummy_locations = [
        {
            "name": "Fake Branch 1",
            "url": "https://maps.google.com/?q=Test",
            "address": "Spaces Hofplein 20, Rotterdam",
            "actual_occupant": "Spaces Virtual Office",
            "kvk_status": "Not registered",
            "policy_violation_details": "Ineligible virtual office"
        }
    ]
    csv_file = export_dossier_csv("Test Corp", dummy_locations, filename="test_dossier.csv")
    assert csv_file.exists()

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == REDRESSAL_COLUMNS
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["business_name_on_profile"] == "Fake Branch 1"

if __name__ == "__main__":
    test_explanation_under_1000_chars()
    test_csv_export_format()
    print("All dossier tests passed successfully!")
