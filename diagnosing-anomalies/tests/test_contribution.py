import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "contribution.py"


class ContributionCliTest(unittest.TestCase):
    def run_cli(self, method, payload):
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as f:
            json.dump(payload, f, ensure_ascii=False)
            input_path = Path(f.name)

        try:
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), method, str(input_path)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            return json.loads(completed.stdout)
        finally:
            input_path.unlink(missing_ok=True)

    def test_additive_outputs_contribution_share_and_relative_contribution(self):
        payload = {
            "baseline_total": 100,
            "current_total": 130,
            "items": [
                {"name": "自然流量", "baseline": 40, "current": 70},
                {"name": "广告投放", "baseline": 50, "current": 55},
                {"name": "社交裂变", "baseline": 10, "current": 5},
            ],
        }

        result = self.run_cli("add", payload)

        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["summary"]["delta"], 30)
        self.assertAlmostEqual(result["summary"]["relative_change"], 0.3)
        rows = {row["name"]: row for row in result["rows"]}
        self.assertAlmostEqual(rows["自然流量"]["contribution_value"], 30)
        self.assertAlmostEqual(rows["自然流量"]["contribution_share"], 1.0)
        self.assertAlmostEqual(rows["自然流量"]["relative_contribution"], 0.3)
        self.assertAlmostEqual(rows["社交裂变"]["contribution_share"], -1 / 6)
        self.assertAlmostEqual(result["checks"]["residual"], 0)

    def test_multiplicative_log_decomposition_returns_factor_contributions(self):
        payload = {
            "factors": [
                {"name": "UV", "baseline": 1000, "current": 900},
                {"name": "CVR", "baseline": 0.1, "current": 0.12},
                {"name": "AOV", "baseline": 100, "current": 125},
            ]
        }

        result = self.run_cli("multiply", payload)

        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["summary"]["baseline_total"], 10000)
        self.assertAlmostEqual(result["summary"]["current_total"], 13500)
        rows = {row["name"]: row for row in result["rows"]}
        expected_uv_share = math.log(900 / 1000) / math.log(13500 / 10000)
        self.assertAlmostEqual(rows["UV"]["log_contribution_share"], expected_uv_share)
        self.assertLess(rows["UV"]["contribution_value"], 0)
        self.assertGreater(rows["AOV"]["contribution_share"], 0)
        self.assertAlmostEqual(result["checks"]["residual"], 0, places=9)

    def test_ratio_between_within_decomposition_quantifies_mix_and_rate_effects(self):
        payload = {
            "groups": [
                {"name": "男性", "baseline_numerator": 800, "baseline_denominator": 3000, "current_numerator": 950, "current_denominator": 3500},
                {"name": "女性", "baseline_numerator": 300, "baseline_denominator": 2000, "current_numerator": 400, "current_denominator": 2500},
            ]
        }

        result = self.run_cli("ratio", payload)

        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["summary"]["baseline_total"], 0.22)
        self.assertAlmostEqual(result["summary"]["current_total"], 0.225)
        rows = {row["name"]: row for row in result["rows"]}
        self.assertGreater(rows["女性"]["within_contribution"], 0)
        self.assertLess(rows["女性"]["mix_contribution"], 0)
        total_row_contribution = sum(row["contribution_value"] for row in result["rows"])
        self.assertAlmostEqual(total_row_contribution, result["summary"]["delta"])
        self.assertAlmostEqual(result["checks"]["residual"], 0, places=9)


if __name__ == "__main__":
    unittest.main()
