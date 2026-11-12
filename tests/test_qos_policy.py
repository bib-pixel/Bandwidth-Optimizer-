import unittest
from app.services.qos_policy import QosPolicyService

class QosPolicyTests(unittest.TestCase):
    def setUp(self):
        self.service = QosPolicyService()

    def test_high_forecast_recommends_preparation_not_enforcement(self):
        result = self.service.recommend({"ready": True, "predicted_level": "High", "predicted_usage_percent": 91, "predicted_throughput_mbps": 91}, 100)
        self.assertEqual(result["status"], "recommendation_only")
        self.assertFalse(result["enforcement_enabled"])
        self.assertTrue(result["actions"])

    def test_unready_forecast_does_not_recommend_restriction(self):
        result = self.service.recommend({"ready": False, "predicted_level": "Collecting history"}, 100)
        self.assertIn("Continue collecting", result["actions"][0])

    def test_apply_refuses_when_disabled(self):
        result = self.service.apply_linux_htb("eth0", 100, enabled=False)
        self.assertFalse(result["applied"])
        self.assertEqual(result["status"], "disabled")

if __name__ == "__main__":
    unittest.main()
