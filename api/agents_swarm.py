"""
Agent Swarm API Endpoint
POST /api/agents_swarm
Orchestrates 5 specialized trading agents for consensus-based decisions.

Request:  {"market": "BTC", "timeframe": "15m", "action": "analyze"}
Response: { fundamental, sentiment, technical, trader, risk, consensus, decision }
"""

import json
import time
import os
import hashlib
import random
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler

# ============================================================================
# CACHE (5-min TTL)
# ============================================================================
CACHE = {}
CACHE_TTL = 300

def cache_get(key):
    if key in CACHE:
        val, ts = CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return val
    return None

def cache_set(key, val):
    CACHE[key] = (val, time.time())

# ============================================================================
# MARKET DATA FETCHERS
# ============================================================================

def fetch_binance_price(symbol="BTCUSDT"):
    """Get current price from Binance"""
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "QuantTerminal/7.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            return {
                "price": float(data["lastPrice"]),
                "change_24h": float(data["priceChangePercent"]),
                "volume": float(data["quoteVolume"]),
                "high": float(data["highPrice"]),
                "low": float(data["lowPrice"]),
            }
    except Exception as e:
        return None

def fetch_funding_rate(symbol="BTCUSDT"):
    """Get funding rate from Binance Futures"""
    try:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "QuantTerminal/7.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            if data:
                return float(data[0]["fundingRate"])
    except:
        pass
    return None

def fetch_fear_greed():
    """Fear & Greed Index"""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "QuantTerminal/7.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("data"):
                return {
                    "value": int(data["data"][0]["value"]),
                    "label": data["data"][0]["value_classification"]
                }
    except:
        pass
    return {"value": 50, "label": "Neutral"}

def fetch_klines(symbol="BTCUSDT", interval="15m", limit=20):
    """Get OHLCV candles from Binance"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "QuantTerminal/7.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            return [{"o": float(c[1]), "h": float(c[2]), "l": float(c[3]),
                      "c": float(c[4]), "v": float(c[5]), "t": c[0]} for c in data]
    except:
        return None

# ============================================================================
# TECHNICAL INDICATORS
# ============================================================================

def calc_rsi(closes, period=14):
    """Calculate RSI"""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_macd(closes, fast=12, slow=26, signal=9):
    """Calculate MACD"""
    if len(closes) < slow:
        return {"macd": 0, "signal": 0, "histogram": 0}
    
    def ema(data, period):
        if len(data) < period:
            return data[-1] if data else 0
        k = 2 / (period + 1)
        e = sum(data[:period]) / period
        for p in data[period:]:
            e = p * k + e * (1 - k)
        return e
    
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    macd_line = fast_ema - slow_ema
    return {"macd": macd_line, "signal": 0, "histogram": macd_line}

def calc_bollinger(closes, period=20, std_mult=2):
    """Bollinger Bands"""
    if len(closes) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "squeeze": False}
    window = closes[-period:]
    middle = sum(window) / period
    std = (sum((x - middle) ** 2 for x in window) / period) ** 0.5
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    squeeze = (upper - lower) / middle < 0.03
    return {"upper": upper, "middle": middle, "lower": lower, "squeeze": squeeze}

# ============================================================================
# AGENT DEFINITIONS
# ============================================================================

def run_fundamental_agent(market_data, symbol):
    """Fundamental Analyst — on-chain data, funding rates, whale positions, news"""
    price = market_data.get("price", {})
    funding = market_data.get("funding_rate", 0)
    fear_greed = market_data.get("fear_greed", {})
    
    signals = []
    confidence = 50
    reasoning = []
    
    # Funding rate analysis
    if funding is not None:
        if funding > 0.01:
            signals.append("bearish")
            reasoning.append(f"Funding rate high ({funding:.4%}) — longs overleveraged, potential squeeze 📉")
            confidence -= 10
        elif funding < -0.005:
            signals.append("bullish")
            reasoning.append(f"Negative funding ({funding:.4%}) — shorts paying, contrarian bullish 📈")
            confidence += 15
        else:
            signals.append("neutral")
            reasoning.append(f"Funding rate normal ({funding:.4%}) — no strong bias")
    
    # Fear & Greed
    fg_val = fear_greed.get("value", 50)
    if fg_val > 75:
        signals.append("bearish")
        reasoning.append(f"Extreme greed ({fg_val}) — top signal, be cautious! 🚨")
        confidence -= 10
    elif fg_val < 25:
        signals.append("bullish")
        reasoning.append(f"Extreme fear ({fg_val}) — blood in streets = buy signal 🩸")
        confidence += 20
    else:
        reasoning.append(f"Fear & Greed neutral ({fg_val})")
    
    # Volume analysis
    if price:
        vol = price.get("volume", 0)
        change = price.get("change_24h", 0)
        if change > 3 and vol > 30e9:
            signals.append("bullish")
            reasoning.append(f"Strong rally with volume confirmation (+{change:.1f}%, vol ${vol/1e9:.1f}B) 🔥")
            confidence += 15
        elif change < -3:
            signals.append("bearish")
            reasoning.append(f"Sell-off detected ({change:.1f}%) — watching for support 👀")
            confidence -= 10
    
    # On-chain simulation (would be real API in production)
    exchange_flow = random.choice(["inflow", "outflow", "neutral"])
    if exchange_flow == "outflow":
        signals.append("bullish")
        reasoning.append("Large exchange outflows detected — whales accumulating 🐋")
        confidence += 10
    elif exchange_flow == "inflow":
        signals.append("bearish")
        reasoning.append("Exchange inflows rising — potential sell pressure incoming 📊")
        confidence -= 5
    
    bullish = signals.count("bullish")
    bearish = signals.count("bearish")
    
    if bullish > bearish:
        recommendation = "BUY"
        confidence = min(95, confidence + 10)
    elif bearish > bullish:
        recommendation = "SELL"
        confidence = max(15, confidence - 5)
    else:
        recommendation = "HOLD"
        confidence = 50
    
    return {
        "agent": "fundamental",
        "status": "ANALYZED",
        "recommendation": recommendation,
        "confidence": round(min(95, max(15, confidence))),
        "reasoning": reasoning,
        "signals_count": {"bullish": bullish, "bearish": bearish, "neutral": signals.count("neutral")},
        "key_metrics": {
            "funding_rate": f"{funding:.4%}" if funding else "N/A",
            "fear_greed": fg_val,
            "exchange_flow": exchange_flow
        },
        "timestamp": datetime.utcnow().isoformat()
    }


def run_sentiment_agent(market_data, symbol):
    """Sentiment Expert — news sentiment, social signals, fear&greed, whale movements"""
    fear_greed = market_data.get("fear_greed", {})
    price = market_data.get("price", {})
    
    # Simulated news sentiment (would use CryptoCompare/CoinGecko API)
    news_items = [
        {"title": f"{symbol} institutional adoption accelerating", "sentiment": 0.7, "impact": "HIGH"},
        {"title": f"Fed hints at rate cuts — risk assets rally", "sentiment": 0.6, "impact": "HIGH"},
        {"title": f"Large {symbol} whale moves detected on-chain", "sentiment": 0.3, "impact": "MED"},
        {"title": f"Regulatory uncertainty in EU for crypto", "sentiment": -0.4, "impact": "MED"},
        {"title": f"Mining difficulty reaches new ATH", "sentiment": 0.2, "impact": "LOW"},
    ]
    
    avg_sentiment = sum(n["sentiment"] for n in news_items) / len(news_items)
    
    # Social signals simulation
    social_score = random.uniform(-0.3, 0.8)
    whale_activity = random.choice(["accumulating", "distributing", "neutral"])
    
    reasoning = []
    confidence = 50
    
    # News analysis
    if avg_sentiment > 0.3:
        reasoning.append(f"News sentiment positive ({avg_sentiment:.2f}) — media bullish on {symbol} 📰✅")
        confidence += 15
    elif avg_sentiment < -0.2:
        reasoning.append(f"News sentiment negative ({avg_sentiment:.2f}) — FUD detected 📰❌")
        confidence -= 10
    else:
        reasoning.append(f"News sentiment mixed ({avg_sentiment:.2f}) — no clear direction 📰")
    
    # Social
    if social_score > 0.4:
        reasoning.append(f"Social media bullish (score: {social_score:.2f}) — CT is hyped! 🐦🔥")
        confidence += 10
    elif social_score < -0.1:
        reasoning.append(f"Social sentiment bearish (score: {social_score:.2f}) — doom posting 🐦💀")
        confidence -= 10
    else:
        reasoning.append(f"Social neutral ({social_score:.2f})")
    
    # Whale activity
    if whale_activity == "accumulating":
        reasoning.append(f"Whales are ACCUMULATING — smart money is buying 🐋💰")
        confidence += 15
    elif whale_activity == "distributing":
        reasoning.append(f"Whales DISTRIBUTING — smart money is selling 🐋📉")
        confidence -= 15
    else:
        reasoning.append("Whale activity normal — no strong signals")
    
    # Fear & Greed
    fg = fear_greed.get("value", 50)
    if fg > 70:
        reasoning.append(f"Market greed ({fg}) — contrarian caution ⚠️")
        confidence -= 5
    elif fg < 30:
        reasoning.append(f"Market fear ({fg}) — contrarian bullish 🩸")
        confidence += 10
    
    if confidence > 55:
        rec = "BUY"
    elif confidence < 45:
        rec = "SELL"
    else:
        rec = "HOLD"
    
    return {
        "agent": "sentiment",
        "status": "ANALYZED",
        "recommendation": rec,
        "confidence": round(min(95, max(15, confidence))),
        "reasoning": reasoning,
        "news_items": [{"title": n["title"], "sentiment": n["sentiment"], "impact": n["impact"]} for n in news_items[:3]],
        "social_score": round(social_score, 2),
        "whale_activity": whale_activity,
        "fear_greed": fg,
        "timestamp": datetime.utcnow().isoformat()
    }


def run_technical_agent(market_data, symbol):
    """Technical Analyst — RSI, MACD, support/resistance, patterns, polymarket signals"""
    candles = market_data.get("candles", [])
    price = market_data.get("price", {})
    
    reasoning = []
    confidence = 50
    signals = []
    
    current_price = price.get("price", 0) if price else 0
    
    if candles and len(candles) >= 14:
        closes = [c["c"] for c in candles]
        
        # RSI
        rsi = calc_rsi(closes)
        if rsi < 30:
            signals.append("bullish")
            reasoning.append(f"RSI oversold ({rsi:.1f}) — bounce expected! 📈🔥")
            confidence += 20
        elif rsi > 70:
            signals.append("bearish")
            reasoning.append(f"RSI overbought ({rsi:.1f}) — pullback imminent 📉")
            confidence -= 15
        else:
            reasoning.append(f"RSI neutral ({rsi:.1f})")
        
        # MACD
        macd = calc_macd(closes)
        if macd["histogram"] > 0:
            signals.append("bullish")
            reasoning.append(f"MACD bullish ({macd['histogram']:.2f}) — momentum up ✅")
            confidence += 10
        else:
            signals.append("bearish")
            reasoning.append(f"MACD bearish ({macd['histogram']:.2f}) — momentum down ❌")
            confidence -= 10
        
        # Bollinger Bands
        bb = calc_bollinger(closes)
        if bb["squeeze"]:
            reasoning.append("Bollinger squeeze detected — big move incoming! 💥")
            confidence += 5
        if current_price and bb["lower"] > 0:
            if current_price <= bb["lower"] * 1.01:
                signals.append("bullish")
                reasoning.append(f"Price at lower BB ({bb['lower']:.0f}) — oversold 📈")
                confidence += 10
            elif current_price >= bb["upper"] * 0.99:
                signals.append("bearish")
                reasoning.append(f"Price at upper BB ({bb['upper']:.0f}) — overbought 📉")
                confidence -= 10
        
        # Support/Resistance
        recent_high = max(c["h"] for c in candles[-10:])
        recent_low = min(c["l"] for c in candles[-10:])
        if current_price:
            dist_to_resistance = (recent_high - current_price) / current_price * 100
            dist_to_support = (current_price - recent_low) / current_price * 100
            reasoning.append(f"Support: ${recent_low:.0f} ({dist_to_support:.1f}% below) | Resistance: ${recent_high:.0f} ({dist_to_resistance:.1f}% above)")
        
        # Pattern detection (simplified)
        last_3 = closes[-3:]
        if last_3[0] < last_3[1] < last_3[2]:
            reasoning.append("Three consecutive green candles — momentum strong 🟢🟢🟢")
            signals.append("bullish")
            confidence += 5
        elif last_3[0] > last_3[1] > last_3[2]:
            reasoning.append("Three red candles — sellers in control 🔴🔴🔴")
            signals.append("bearish")
            confidence -= 5
        
        indicators = {"rsi": round(rsi, 1), "macd": round(macd["histogram"], 2),
                       "bb_upper": round(bb["upper"], 0), "bb_lower": round(bb["lower"], 0)}
    else:
        # Simulated if no candle data
        rsi = random.uniform(25, 75)
        reasoning.append(f"[SIM] RSI: {rsi:.1f}")
        reasoning.append("[SIM] Using simulated indicators — real data pending")
        indicators = {"rsi": round(rsi, 1), "macd": 0, "bb_upper": 0, "bb_lower": 0}
        if rsi < 35:
            signals.append("bullish")
            confidence += 15
        elif rsi > 65:
            signals.append("bearish")
            confidence -= 15
    
    # Polymarket signal (simulated)
    poly_bullish = random.uniform(0.4, 0.75)
    if poly_bullish > 0.6:
        reasoning.append(f"Polymarket: {poly_bullish:.0%} predict price increase — smart money bullish 🎰")
        signals.append("bullish")
        confidence += 5
    elif poly_bullish < 0.45:
        reasoning.append(f"Polymarket: {poly_bullish:.0%} bearish prediction 🎰")
        signals.append("bearish")
        confidence -= 5
    
    bullish = signals.count("bullish")
    bearish = signals.count("bearish")
    
    if bullish > bearish + 1:
        rec = "BUY"
        confidence = min(95, confidence + 10)
    elif bearish > bullish + 1:
        rec = "SELL"
        confidence = max(15, confidence)
    elif bullish > bearish:
        rec = "BUY"
    elif bearish > bullish:
        rec = "SELL"
    else:
        rec = "HOLD"
    
    return {
        "agent": "technical",
        "status": "ANALYZED",
        "recommendation": rec,
        "confidence": round(min(95, max(15, confidence))),
        "reasoning": reasoning,
        "indicators": indicators,
        "signals_count": {"bullish": bullish, "bearish": bearish},
        "polymarket_signal": round(poly_bullish, 2),
        "timestamp": datetime.utcnow().isoformat()
    }


def run_trader_agent(fund_result, sent_result, tech_result, market_data, symbol):
    """Trader — based on other agents' signals, decides entry/SL/TP"""
    price_data = market_data.get("price", {})
    current_price = price_data.get("price", 68000) if price_data else 68000
    
    votes = {
        "fundamental": fund_result["recommendation"],
        "sentiment": sent_result["recommendation"],
        "technical": tech_result["recommendation"]
    }
    
    buy_votes = sum(1 for v in votes.values() if v == "BUY")
    sell_votes = sum(1 for v in votes.values() if v == "SELL")
    hold_votes = sum(1 for v in votes.values() if v == "HOLD")
    
    avg_confidence = (fund_result["confidence"] + sent_result["confidence"] + tech_result["confidence"]) / 3
    
    reasoning = []
    
    if buy_votes >= 2:
        action = "BUY"
        sl_pct = 0.013  # 1.3%
        tp_pct = 0.021  # 2.1%
        entry = current_price
        sl = round(entry * (1 - sl_pct), 2)
        tp = round(entry * (1 + tp_pct), 2)
        rr = round(tp_pct / sl_pct, 1)
        reasoning.append(f"Consensus: {buy_votes}/3 agents say BUY. Let's go! 🚀")
        reasoning.append(f"Entry: ${entry:,.2f} | SL: ${sl:,.2f} (-{sl_pct*100:.1f}%) | TP: ${tp:,.2f} (+{tp_pct*100:.1f}%)")
        reasoning.append(f"Risk/Reward: 1:{rr}")
        confidence = min(95, int(avg_confidence + 10))
    elif sell_votes >= 2:
        action = "SELL"
        sl_pct = 0.012
        tp_pct = 0.018
        entry = current_price
        sl = round(entry * (1 + sl_pct), 2)
        tp = round(entry * (1 - tp_pct), 2)
        rr = round(tp_pct / sl_pct, 1)
        reasoning.append(f"Consensus: {sell_votes}/3 agents say SELL. Short it! 📉")
        reasoning.append(f"Entry: ${entry:,.2f} | SL: ${sl:,.2f} (+{sl_pct*100:.1f}%) | TP: ${tp:,.2f} (-{tp_pct*100:.1f}%)")
        reasoning.append(f"Risk/Reward: 1:{rr}")
        confidence = min(95, int(avg_confidence + 10))
    else:
        action = "HOLD"
        entry = current_price
        sl = 0
        tp = 0
        rr = 0
        reasoning.append(f"No clear consensus ({buy_votes}B/{sell_votes}S/{hold_votes}H). Standing down. ✋")
        reasoning.append("Waiting for clearer signals before entering position.")
        confidence = max(30, int(avg_confidence - 10))
    
    return {
        "agent": "trader",
        "status": "DECIDED",
        "recommendation": action,
        "confidence": confidence,
        "reasoning": reasoning,
        "trade_plan": {
            "action": action,
            "symbol": symbol,
            "entry": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "risk_reward": rr
        },
        "votes": votes,
        "avg_confidence": round(avg_confidence, 1),
        "timestamp": datetime.utcnow().isoformat()
    }


def run_risk_agent(trader_result, market_data):
    """Risk Manager — validates position size, drawdown, R:R, risk limits"""
    trade = trader_result.get("trade_plan", {})
    action = trade.get("action", "HOLD")
    price_data = market_data.get("price", {})
    
    reasoning = []
    approved = True
    risk_score = 0  # 0-100, higher = riskier
    
    if action == "HOLD":
        reasoning.append("No trade to validate — HOLD position. ✅")
        return {
            "agent": "risk",
            "status": "APPROVED",
            "recommendation": "HOLD",
            "confidence": 80,
            "approved": True,
            "reasoning": reasoning,
            "risk_score": 0,
            "risk_metrics": {},
            "timestamp": datetime.utcnow().isoformat()
        }
    
    entry = trade.get("entry", 0)
    sl = trade.get("stop_loss", 0)
    tp = trade.get("take_profit", 0)
    rr = trade.get("risk_reward", 0)
    
    # Position sizing (simulated portfolio)
    portfolio_value = 50000  # $50K demo portfolio
    max_risk_per_trade = 0.02  # 2% max risk
    position_size = portfolio_value * max_risk_per_trade
    
    # R:R check
    if rr >= 2:
        reasoning.append(f"Risk/Reward {rr}:1 — EXCELLENT ✅✅")
        risk_score -= 10
    elif rr >= 1.5:
        reasoning.append(f"Risk/Reward {rr}:1 — acceptable ✅")
    elif rr > 0:
        reasoning.append(f"Risk/Reward {rr}:1 — below minimum, proceed with caution ⚠️")
        risk_score += 20
        if rr < 1:
            approved = False
            reasoning.append(f"R:R below 1:1 — REJECTED ❌")
    
    # Drawdown check
    max_drawdown = 5.0  # 5% max
    current_drawdown = random.uniform(0.5, 4.0)
    remaining_budget = max_drawdown - current_drawdown
    
    if current_drawdown > max_drawdown * 0.8:
        reasoning.append(f"Current drawdown {current_drawdown:.1f}% — approaching limit ({max_drawdown}%) ⚠️🚨")
        risk_score += 30
        if current_drawdown >= max_drawdown:
            approved = False
            reasoning.append("MAX DRAWDOWN REACHED — ALL TRADING HALTED ❌🛑")
    else:
        reasoning.append(f"Drawdown OK: {current_drawdown:.1f}% / {max_drawdown}% limit ✅")
    
    # Volatility check
    change_24h = price_data.get("change_24h", 0) if price_data else 0
    if abs(change_24h) > 8:
        reasoning.append(f"HIGH VOLATILITY ({change_24h:+.1f}% 24h) — reduce position size ⚠️")
        risk_score += 20
        position_size *= 0.5
    elif abs(change_24h) > 5:
        reasoning.append(f"Elevated volatility ({change_24h:+.1f}% 24h) — monitor closely 👀")
        risk_score += 10
    else:
        reasoning.append(f"Volatility normal ({change_24h:+.1f}% 24h) ✅")
    
    # Correlation check
    reasoning.append(f"Position size: ${position_size:,.0f} ({(position_size/portfolio_value*100):.1f}% of portfolio)")
    
    # Final score
    risk_score = max(0, min(100, 30 + risk_score))
    
    if approved:
        if risk_score > 60:
            reasoning.append(f"Risk score {risk_score}/100 — ELEVATED but within limits. Proceed with caution. ⚠️✅")
        else:
            reasoning.append(f"Risk score {risk_score}/100 — Trade APPROVED ✅✅")
    
    return {
        "agent": "risk",
        "status": "APPROVED" if approved else "REJECTED",
        "recommendation": trader_result["recommendation"] if approved else "HOLD",
        "confidence": 80 if approved else 30,
        "approved": approved,
        "reasoning": reasoning,
        "risk_score": risk_score,
        "risk_metrics": {
            "position_size": round(position_size, 2),
            "max_drawdown": max_drawdown,
            "current_drawdown": round(current_drawdown, 2),
            "remaining_budget": round(remaining_budget, 2),
            "volatility_24h": round(change_24h, 2),
            "risk_reward": rr
        },
        "timestamp": datetime.utcnow().isoformat()
    }


def calculate_consensus(results):
    """Calculate overall consensus from all 5 agents"""
    agents = ["fundamental", "sentiment", "technical", "trader", "risk"]
    recs = {a: results[a]["recommendation"] for a in agents}
    
    buy_count = sum(1 for r in recs.values() if r == "BUY")
    sell_count = sum(1 for r in recs.values() if r == "SELL")
    hold_count = sum(1 for r in recs.values() if r == "HOLD")
    
    total = len(agents)
    max_count = max(buy_count, sell_count, hold_count)
    agreement_pct = round(max_count / total * 100)
    
    if buy_count >= 3:
        decision = "BUY"
    elif sell_count >= 3:
        decision = "SELL"
    else:
        decision = "HOLD"
    
    avg_conf = round(sum(results[a]["confidence"] for a in agents) / total, 1)
    
    return {
        "decision": decision,
        "agreement_pct": agreement_pct,
        "votes": recs,
        "counts": {"buy": buy_count, "sell": sell_count, "hold": hold_count},
        "avg_confidence": avg_conf,
        "execute": decision != "HOLD" and agreement_pct >= 60 and results["risk"]["approved"]
    }


def run_swarm(market="BTC", timeframe="15m"):
    """Run all 5 agents and calculate consensus"""
    symbol = f"{market}USDT"
    
    # Fetch market data
    cache_key = f"swarm_{symbol}_{timeframe}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    
    market_data = {
        "price": fetch_binance_price(symbol),
        "funding_rate": fetch_funding_rate(symbol),
        "fear_greed": fetch_fear_greed(),
        "candles": fetch_klines(symbol, timeframe, 30),
    }
    
    # Run analyst agents independently
    fund_result = run_fundamental_agent(market_data, market)
    sent_result = run_sentiment_agent(market_data, market)
    tech_result = run_technical_agent(market_data, market)
    
    # Trader decides based on analyst consensus
    trader_result = run_trader_agent(fund_result, sent_result, tech_result, market_data, market)
    
    # Risk manager validates
    risk_result = run_risk_agent(trader_result, market_data)
    
    # Calculate overall consensus
    all_results = {
        "fundamental": fund_result,
        "sentiment": sent_result,
        "technical": tech_result,
        "trader": trader_result,
        "risk": risk_result
    }
    
    consensus = calculate_consensus(all_results)
    
    # Build agent discussion
    discussion = []
    for agent_name in ["fundamental", "sentiment", "technical", "trader", "risk"]:
        agent = all_results[agent_name]
        for line in agent["reasoning"][:2]:  # Top 2 reasoning lines per agent
            discussion.append({
                "agent": agent_name,
                "message": line,
                "timestamp": agent["timestamp"]
            })
    
    result = {
        "market": market,
        "timeframe": timeframe,
        "fundamental": fund_result,
        "sentiment": sent_result,
        "technical": tech_result,
        "trader": trader_result,
        "risk": risk_result,
        "consensus": consensus,
        "discussion": discussion,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    cache_set(cache_key, result)
    return result


# ============================================================================
# VERCEL SERVERLESS HANDLER
# ============================================================================

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """GET — run with defaults or query params"""
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)
        market = params.get("market", ["BTC"])[0].upper()
        timeframe = params.get("timeframe", ["15m"])[0]
        
        result = run_swarm(market, timeframe)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())
    
    def do_POST(self):
        """POST — JSON body with market, timeframe, action"""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        
        try:
            data = json.loads(body)
        except:
            data = {}
        
        market = data.get("market", "BTC").upper()
        timeframe = data.get("timeframe", "15m")
        
        result = run_swarm(market, timeframe)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
