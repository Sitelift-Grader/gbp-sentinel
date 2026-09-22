import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbp_sentinel import investigator


def test_network_report_groups_shared_phone():
    targets = [{"name": "A", "website": "https://example.nl"}, {"name": "B", "website": "https://other.nl"}]
    locations = {
        "A": [{"name": "A1", "phone": "020 123 4567", "address": "A straat 1", "url": "https://maps.example/a"}],
        "B": [{"name": "B1", "phone": "+31 20 1234567", "address": "B straat 2", "url": "https://maps.example/b"}],
    }
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(investigator.db, "list_targets", return_value=targets), patch.object(investigator.db, "get_locations", side_effect=lambda name: locations[name]):
        path, report = investigator.build_network_report(output_dir=Path(temp_dir) / "report")
        assert path.exists()
        assert len(report["clusters"]) == 1
        assert report["clusters"][0]["profiles"] == 2


if __name__ == "__main__":
    test_network_report_groups_shared_phone()
    print("All investigator tests passed successfully!")
