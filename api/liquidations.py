"""
/api/liquidations — OI + L/S ratio from Binance, sync version
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler

BINANCE = "https://fapi.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT"]


def fetch_liq_data():
    result = {"open_interest": {}, "long_short_ratio": {}}

    for sym in SYMBOLS:
        try:
            req = urllib.request.Request(f"{BINANCE}/fapi/v1/openInterest?symbol={sym}",
                                         headers={"User-Agent": "CCC/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                result["open_interest"][sym] = float(data.get("openInterest", 0))
        except Exception:
            pass

        try:
            req = urllib.request.Request(
                f"{BINANCE}/futures/data/topLongShortPositionRatio?symbol={sym}&period=5m&limit=1",
                headers={"User-Agent": "CCC/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                if data and isinstance(data, list):
                    result["long_short_ratio"][sym] = {
                        "long": float(data[0].get("longAccount", 0)),
                        "short": float(data[0].get("shortAccount", 0)),
                        "ratio": float(data[0].get("longShortRatio", 1)),
                    }
        except Exception:
            pass

    return result


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = fetch_liq_data()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=5, stale-while-revalidate=10")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
