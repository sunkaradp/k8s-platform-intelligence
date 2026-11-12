import unittest

from app.main import confidence_from_ttf, linear_slope, tier_from_conf


class PredictionLogicTests(unittest.TestCase):
    def test_linear_slope_returns_bytes_per_second(self):
        self.assertAlmostEqual(linear_slope([0, 10, 20], [100, 80, 60]), -2.0)

    def test_linear_slope_handles_insufficient_samples(self):
        self.assertEqual(linear_slope([1], [10]), 0.0)

    def test_linear_slope_handles_identical_timestamps(self):
        self.assertEqual(linear_slope([1, 1], [10, 5]), 0.0)

    def test_confidence_is_one_at_or_below_zero_hours(self):
        self.assertEqual(confidence_from_ttf(0, 4), 1.0)
        self.assertEqual(confidence_from_ttf(-1, 4), 1.0)

    def test_confidence_is_zero_at_warning_horizon(self):
        self.assertEqual(confidence_from_ttf(4, 4), 0.0)
        self.assertEqual(confidence_from_ttf(5, 4), 0.0)

    def test_confidence_is_linear_inside_horizon(self):
        self.assertEqual(confidence_from_ttf(2, 4), 0.5)

    def test_non_positive_warning_horizon_has_zero_confidence(self):
        self.assertEqual(confidence_from_ttf(1, 0), 0.0)

    def test_prediction_tier_never_authorizes_remediation(self):
        for confidence in (0.0, 0.7, 0.9, 1.0):
            tier, recommendation = tier_from_conf(confidence)
            self.assertEqual(tier, "OBSERVE")
            self.assertIn("Observe only", recommendation)
            self.assertNotIn("cordon", recommendation.lower())
            self.assertNotIn("drain", recommendation.lower())


if __name__ == "__main__":
    unittest.main()
