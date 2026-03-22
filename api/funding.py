"""
/api/funding — funding rates from Binance + Bybit, sync version
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler


def fetch_funding():
    all_rates = {}
    arbs = []

    # Binance funding
    try:
        req = urllib.request.Request("https://fapi.binance.com/fapi/v1/premiumIndex",
                                     headers={"User-Agent": "CCC/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                for item in data:
                    sym = item.get("symbol", "")
                    rate = float(item.get("lastFundingRate", 0))
                    if sym not in all_rates:
                        all_rates[sym] = {}
                    all_rates[sym]["Binance"] = rate
    except Exception:
        pass

    # Bybit funding
    try:
        req = urllib.request.Request("https://api.bybit.com/v5/market/tickers?category=linear",
                                     headers={"User-Agent": "CCC/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            for item in data.get("result", {}).get("list", []):
                sym = item.get("symbol", "")
                rate = float(item.get("fundingRate", 0) or 0)
                if sym not in all_rates:
                    all_rates[sym] = {}
                all_rates[sym]["Bybit"] = rate
    except Exception:
        pass

    # Find arbs
    for sym, exchanges in all_rates.items():
        if len(exchanges) < 2:
            continue
        ex_list = list(exchanges.items())
        for i in range(len(ex_list)):
            for j in range(i + 1, len(ex_list)):
                name1, rate1 = ex_list[i]
                name2, rate2 = ex_list[j]
                spread = abs(rate1 - rate2)
                annual = spread * 3 * 365 * 100
                if annual < 10:
                    continue
                if rate1 > rate2:
                    short_ex, long_ex = name1, name2
                else:
                    short_ex, long_ex = name2, name1
                arbs.append({
                    "symbol": sym.replace("USDT", ""),
                    "annual_pct": round(annual, 2),
                    "daily_pct": round(spread * 3 * 100, 4),
                    "short_exchange": short_ex,
                    "long_exchange": long_ex,
                    "spread": spread,
                })

    arbs.sort(key=lambda x: x["annual_pct"], reverse=True)
    return arbs[:30]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        arbs = fetch_funding()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=30, stale-while-revalidate=60")
        self.end_headers()
        self.wfile.write(json.dumps(arbs).encode())
