import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbp_sentinel import campaign


def test_campaign_uses_only_review_ready_locations():
    locations = [
        {"name": "Strong", "is_reportable": True, "review_status": "ready_for_review", "violation_category": "virtual_office", "url": "https://maps.example/1", "evidence_signals": ["known_virtual_office"]},
        {"name": "Weak", "is_reportable": False, "review_status": "needs_evidence", "violation_category": "keyword_stuffing"},
    ]
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(campaign.db, "list_targets", return_value=[{"name": "Network"}]), patch.object(campaign.db, "get_locations", return_value=locations):
        manifest_path, manifest = campaign.build_campaign(batch_size=20, output_dir=Path(temp_dir) / "campaign")
        assert manifest_path.exists()
        assert manifest["total_review_ready_locations"] == 1
        assert manifest["batches"][0]["route"] == "google_redressal"


if __name__ == "__main__":
    test_campaign_uses_only_review_ready_locations()
    print("All campaign tests passed successfully!")
