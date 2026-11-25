"""Product import, scoring, review analysis, and verdict helpers."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FILE = ROOT / "data" / "sample_products.json"

SPEC_LABELS = {
    "processor": "Processor", "ram_gb": "RAM (GB)", "storage_gb": "Storage (GB)",
    "battery_mah": "Battery (mAh)", "battery_wh": "Battery (Wh)",
    "display_inches": "Display (in)", "refresh_rate_hz": "Refresh rate (Hz)",
    "camera_mp": "Main camera (MP)", "weight_g": "Weight (g)",
    "water_resistance": "Water resistance", "screen_resolution": "Resolution",
}
NUMERIC_SPECS = {"ram_gb", "storage_gb", "battery_mah", "battery_wh", "display_inches", "refresh_rate_hz", "camera_mp", "weight_g"}

def load_samples() -> list[dict[str, Any]]:
    return json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))

def _number(text: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group()) if match else None

def extract_specs(text: str, category: str = "Smartphone") -> dict[str, Any]:
    """Extract common electronics specs from pasted listing text."""
    patterns = {
        "ram_gb": r"(\d+(?:\.\d+)?)\s*GB\s*RAM",
        "storage_gb": r"(\d+(?:\.\d+)?)\s*GB\s*(?:storage|ROM|SSD)",
        "battery_mah": r"(\d{3,5})\s*mAh",
        "battery_wh": r"(\d+(?:\.\d+)?)\s*Wh",
        "display_inches": r"(\d+(?:\.\d+)?)\s*(?:inch|inches|\")",
        "refresh_rate_hz": r"(\d{2,3})\s*Hz",
        "camera_mp": r"(\d{2,3})\s*MP",
        "weight_g": r"(\d{3,4})\s*g(?:\s|$)",
    }
    specs: dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            specs[key] = float(match.group(1))
    proc = re.search(r"(?:Snapdragon\s*[\w+]+|Dimensity\s*\d+[\w]*|Tensor\s*[\w]+|Apple\s*A\d+|Intel\s*Core\s*(?:Ultra\s*)?[\w -]+|Ryzen\s*\d\s*[\w-]*)", text, re.I)
    if proc:
        specs["processor"] = proc.group().strip()
    resolution = re.search(r"(\d{3,4}\s*[x×]\s*\d{3,4}\s*(?:OLED|IPS|AMOLED)?)", text, re.I)
    if resolution:
        specs["screen_resolution"] = resolution.group(1).strip()
    water = re.search(r"IP\s*\d{2}", text, re.I)
    if water:
        specs["water_resistance"] = water.group().upper().replace(" ", "")
    return specs

def parse_product_text(text: str, name: str, price: float, category: str = "Smartphone", brand: str = "Unknown") -> dict[str, Any]:
    return {"name": name.strip(), "brand": brand.strip() or "Unknown", "category": category, "price": float(price), "currency": "INR", "source_url": "Manual entry", "specs": extract_specs(text, category), "reviews": []}

def import_url(url: str, timeout: int = 12) -> dict[str, Any]:
    """Fetch public product pages where allowed; extraction is best effort."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid http or https product URL.")
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "CompareXAI/1.0 (product comparison demo)"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    title_tag = soup.find("meta", property="og:title") or soup.find("title")
    name = (title_tag.get("content") if title_tag and title_tag.name == "meta" else title_tag.get_text(" ", strip=True) if title_tag else parsed.netloc)
    description_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    text = " ".join(filter(None, [name, description_tag.get("content") if description_tag else "", soup.get_text(" ", strip=True)[:20000]]))
    price_meta = soup.find("meta", property="product:price:amount") or soup.find("meta", attrs={"itemprop": "price"})
    price = _number(price_meta.get("content", "") if price_meta else text)
    return {"name": name[:180], "brand": "Imported listing", "category": "Electronics", "price": price or 0, "currency": "INR", "source_url": url, "specs": extract_specs(text), "reviews": [], "import_note": "Page extraction is best effort. Verify imported details before comparing."}

def score_products(products: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    """Return products with 0-100 weighted scores; all active dimensions are normalized."""
    active = {k: max(0.0, float(v)) for k, v in weights.items() if float(v) > 0}
    if not active:
        active = {"price": 1.0}
    total = sum(active.values())
    out = []
    for product in products:
        components = []
        for key, weight in active.items():
            value = product.get("price") if key == "price" else product.get("specs", {}).get(key)
            candidates = [p.get("price") if key == "price" else p.get("specs", {}).get(key) for p in products]
            nums = [_number(str(v)) for v in candidates if v is not None]
            current = _number(str(value)) if value is not None else None
            if current is None or not nums:
                continue
            lo, hi = min(nums), max(nums)
            norm = 1.0 if hi == lo else (current - lo) / (hi - lo)
            # Price and weight are lower-is-better, other numeric specs higher-is-better.
            if key == "price" or key == "weight_g":
                norm = 1 - norm
            components.append((norm, weight))
        score = (sum(x*w for x, w in components) / sum(w for _, w in components) * 100) if components else 0
        out.append({**product, "score": round(score, 1)})
    return sorted(out, key=lambda p: p["score"], reverse=True)

THEMES = {"battery": ["battery", "charge", "charging", "lasts"], "camera": ["camera", "photo", "video", "picture"], "display": ["display", "screen", "oled", "bright"], "performance": ["fast", "speed", "performance", "gaming", "smooth"], "value": ["price", "expensive", "value", "cost"], "build & comfort": ["heavy", "lightweight", "comfortable", "build", "keyboard"]}
POSITIVE = {"excellent", "great", "good", "love", "fast", "bright", "smooth", "comfortable", "superb", "reliable", "excellent", "gorgeous", "useful", "sturdy"}
NEGATIVE = {"poor", "bad", "slow", "expensive", "dated", "limited", "average", "heavy", "audible", "fills", "warm", "could", "but"}

def analyze_reviews(reviews: list[str]) -> dict[str, Any]:
    if not reviews:
        return {"sentiment": "No reviews", "positive_pct": 0, "themes": {}}
    scores = []
    counts = Counter()
    for review in reviews:
        words = set(re.findall(r"[a-z]+", review.lower()))
        scores.append(len(words & POSITIVE) - len(words & NEGATIVE))
        for theme, terms in THEMES.items():
            if any(term in review.lower() for term in terms):
                counts[theme] += 1
    positive_pct = round(sum(s > 0 for s in scores) / len(scores) * 100)
    avg = sum(scores) / len(scores)
    return {"sentiment": "Positive" if avg > .25 else "Mixed" if avg >= -.25 else "Critical", "positive_pct": positive_pct, "themes": dict(counts), "review_count": len(reviews)}

def build_verdict(products: list[dict[str, Any]], scores: list[dict[str, Any]], weights: dict[str, float], reviews_by_name: dict[str, dict[str, Any]]) -> str:
    if not scores:
        return "Add at least two products to generate a comparison."
    ranked = ", ".join(f"{p['name']} ({p['score']:.0f}/100)" for p in scores)
    best = scores[0]
    price_values = [f"{p['name']}: ₹{p.get('price', 0):,.0f}" for p in products]
    return (f"**Weighted result:** {best['name']} ranks highest at {best['score']:.0f}/100 using your selected priorities. Ranking: {ranked}. "
            f"**Price evidence:** {'; '.join(price_values)}. "
            f"**Review evidence:** " + "; ".join(f"{name}: {summary['sentiment'].lower()} sentiment across {summary.get('review_count', 0)} reviews" for name, summary in reviews_by_name.items()) + ". "
            "Scores are relative to the products shown; confirm specifications and prices with the retailer before purchase.")

def groq_verdict(products: list[dict[str, Any]], scoring: list[dict[str, Any]], review_summaries: dict[str, Any], api_key: str, model: str) -> str:
    from groq import Groq
    evidence = [{"name": p["name"], "price": p.get("price"), "specs": p.get("specs", {}), "score": next((s["score"] for s in scoring if s["name"] == p["name"]), None), "reviews": review_summaries.get(p["name"])} for p in products]
    response = Groq(api_key=api_key).chat.completions.create(model=model, temperature=0.2, messages=[{"role":"system","content":"Write a concise product comparison verdict using only supplied evidence. Mention tradeoffs, identify evidence vs unknowns, and do not invent facts."},{"role":"user","content":json.dumps(evidence)}])
    return response.choices[0].message.content or "No verdict returned."
