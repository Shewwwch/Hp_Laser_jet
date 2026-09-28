import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import curated_search, live_search


class EngineTests(unittest.TestCase):
    def test_curated_source_and_scope(self):
        found = curated_search("финтех")
        self.assertEqual(len(found["results"]), 15)
        self.assertEqual(found["candidate_count"], 17)
        self.assertTrue(all(row["sources"] and row["area"] == "Финтех" for row in found["results"]))
        self.assertEqual(curated_search("астрогеология экзопланет")["results"], [])

    def test_live_grouping_and_history(self):
        titles = ["Tactile sensing for robotic manipulation", "Tactile sensing in robot hands for manipulation", "Robotic tactile sensing with flexible sensors", "Robotic tactile sensing for grasping"]
        recent = [{"id": f"w{i}", "title": title, "publication_date": "2026-06-01", "doi": f"https://doi.org/10.1000/{i}", "language": "en"} for i, title in enumerate(titles)]
        historical = [{"id": "old", "title": "Cloud computing for robotics", "publication_date": "2020-01-01"}]
        result = live_search("robotics", recent, historical)
        self.assertTrue(result["results"])
        self.assertEqual(result["results"][0]["title"], "tactile sensing")
        self.assertEqual(result["results"][0]["historic_count"], 0)
        self.assertEqual(result["results"][0]["first_observed"], 2026)
        self.assertEqual(result["source_count"], 5)


if __name__ == "__main__":
    unittest.main()
