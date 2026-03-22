"""
/api/predictions — Polymarket + Kalshi, sync version
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler


def fetch_predictions():
    result = {"polymarket": [], "kalshi": []}

    # Polymarket
    try:
        url = "https://gamma-api.polymarket.com/markets?limit=30&active=true&order=volume&ascending=false&closed=false"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "CCC/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                for item in data:
                    try:
                        question = item.get("question", "")
                        yes_price = 0.5
                        tokens = item.get("tokens", [])
                        if tokens and len(tokens) >= 2:
                            yes_price = float(tokens[0].get("price", 0.5))
                        elif item.get("outcomePrices"):
                            try:
                                prices = json.loads(item["outcomePrices"])
                                if len(prices) >= 2:
                                    yes_price = float(prices[0])
                            except Exception:
                                pass
                        volume = float(item.get("volume", 0) or 0)
                        tags = [t.get("label", "") for t in item.get("tags", [])]
                        category = tags[0] if tags else "Other"
                        result["polymarket"].append({
                            "question": question,
                            "yes_price": yes_price,
                            "volume": volume,
                            "category": category,
                            "url": f"https://polymarket.com/event/{item.get('slug', '')}",
                        })
                    except Exception:
                        continue
    except Exception as e:
        result["polymarket_error"] = str(e)

    # Kalshi public
    try:
        req = urllib.request.Request("https://api.elections.kalshi.com/v1/cached/events/",
                                     headers={"Accept": "application/json", "User-Agent": "CCC/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                for event in data.get("events", [])[:20]:
                    for mkt in event.get("markets", []):
                        yes_price = float(mkt.get("yes_ask", 50)) / 100
                        result["kalshi"].append({
                            "question": mkt.get("title", ""),
                            "yes_price": yes_price,
                            "volume": float(mkt.get("volume", 0)),
                            "category": event.get("category", ""),
                            "url": f"https://kalshi.com/markets/{mkt.get('ticker', '')}",
                        })
    except Exception as e:
        result["kalshi_error"] = str(e)

    return result


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = fetch_predictions()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=120, stale-while-revalidate=300")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
