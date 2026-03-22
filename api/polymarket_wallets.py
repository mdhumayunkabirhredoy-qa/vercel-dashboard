"""
/api/polymarket_wallets — Top whale wallets + predictions from Polymarket
"""
import json
import random
import urllib.request
from http.server import BaseHTTPRequestHandler


def fetch_polymarket_wallets():
    result = {"markets": [], "whale_wallets": [], "predictions": []}
    
    # Fetch top markets
    try:
        url = "https://gamma-api.polymarket.com/markets?limit=20&active=true&closed=false&order=volume&ascending=false"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "QuantDash/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                for item in data[:15]:
                    try:
                        question = item.get("question", "")[:80]
                        yes_price = 0.5
                        no_price = 0.5
                        tokens = item.get("tokens", [])
                        if tokens and len(tokens) >= 2:
                            yes_price = float(tokens[0].get("price", 0.5))
                            no_price = float(tokens[1].get("price", 0.5))
                        elif item.get("outcomePrices"):
                            try:
                                prices = json.loads(item["outcomePrices"])
                                if len(prices) >= 2:
                                    yes_price = float(prices[0])
                                    no_price = float(prices[1])
                            except Exception:
                                pass
                        volume = float(item.get("volume", 0) or 0)
                        liquidity = float(item.get("liquidity", 0) or 0)
                        slug = item.get("slug", "")
                        cond_id = item.get("conditionId", "")
                        
                        # Generate prediction based on prices
                        if yes_price > 0.75:
                            pred = "STRONG YES"
                            pred_color = "green"
                        elif yes_price > 0.6:
                            pred = "LEAN YES"
                            pred_color = "green"
                        elif no_price > 0.75:
                            pred = "STRONG NO"
                            pred_color = "red"
                        elif no_price > 0.6:
                            pred = "LEAN NO"
                            pred_color = "red"
                        else:
                            pred = "NEUTRAL"
                            pred_color = "yellow"
                        
                        market = {
                            "question": question,
                            "yes_price": yes_price,
                            "no_price": no_price,
                            "volume": volume,
                            "liquidity": liquidity,
                            "url": f"https://polymarket.com/event/{slug}",
                            "condition_id": cond_id,
                            "prediction": pred,
                            "pred_color": pred_color,
                        }
                        result["markets"].append(market)
                        
                    except Exception:
                        continue
    except Exception as e:
        result["markets_error"] = str(e)

    # Try to fetch whale positions from CLOB API
    # (May fail without auth — fallback to simulated data)
    whale_fetched = False
    if result["markets"]:
        for mkt in result["markets"][:5]:
            cid = mkt.get("condition_id", "")
            if not cid:
                continue
            try:
                url = f"https://clob.polymarket.com/book?token_id={cid}&limit=5"
                req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "QuantDash/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    book = json.loads(resp.read().decode())
                    for bid in book.get("bids", [])[:3]:
                        size = float(bid.get("size", 0))
                        if size > 50000:
                            result["whale_wallets"].append({
                                "addr": bid.get("owner", "0x???")[:10] + "...",
                                "market": mkt["question"][:40],
                                "side": "YES",
                                "size": size,
                            })
                            whale_fetched = True
                    for ask in book.get("asks", [])[:3]:
                        size = float(ask.get("size", 0))
                        if size > 50000:
                            result["whale_wallets"].append({
                                "addr": ask.get("owner", "0x???")[:10] + "...",
                                "market": mkt["question"][:40],
                                "side": "NO",
                                "size": size,
                            })
                            whale_fetched = True
            except Exception:
                continue
    
    # Fallback: simulate whale data if CLOB didn't work
    if not whale_fetched and result["markets"]:
        addrs = ["0x7a2d38...", "0xb4c91e...", "0x1f3e7d...", "0x9c82fa...", "0xe5d04b...", "0x3a8f6c..."]
        for i, mkt in enumerate(result["markets"][:6]):
            side = "YES" if mkt["yes_price"] > 0.5 else "NO"
            size = random.randint(55000, 350000)
            result["whale_wallets"].append({
                "addr": addrs[i % len(addrs)],
                "market": mkt["question"][:40],
                "side": side,
                "size": size,
                "simulated": True,
            })
    
    # Sort whales by size
    result["whale_wallets"].sort(key=lambda x: x.get("size", 0), reverse=True)
    
    return result


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = fetch_polymarket_wallets()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=120, stale-while-revalidate=300")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
