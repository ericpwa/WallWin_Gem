import unittest

from fastapi.testclient import TestClient

from api_app import app
from tests.test_v3_api_layer import synthetic_intraday, synthetic_ohlcv


class FastApiLayerTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "OK")

    def test_swing_endpoint(self):
        response = self.client.post("/analyze/swing", json={"symbol": "2206.TW", "ohlcv": synthetic_ohlcv()})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "OK")
        self.assertEqual(body["endpoint"], "/analyze/swing")

    def test_daytrade_endpoint(self):
        response = self.client.post(
            "/analyze/daytrade",
            json={"symbol": "2206.TW", "ohlcv": synthetic_ohlcv(), "intraday_ohlcv": synthetic_intraday()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["result"]["daytrade"]["available"])

    def test_risk_endpoint(self):
        response = self.client.post(
            "/risk/position-size",
            json={"entry": 60, "stop": 55, "account_size": 1_000_000, "risk_pct": 1, "max_position_pct": 20},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["quantity"], 2000)


if __name__ == "__main__":
    unittest.main()
