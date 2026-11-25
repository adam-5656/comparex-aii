from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from comparex.core import SPEC_LABELS, analyze_reviews, build_verdict, groq_verdict, import_url, load_samples, parse_product_text, score_products
from comparex.report import make_pdf
from comparex.storage import recent_comparisons, save_comparison

load_dotenv()
DB_PATH = Path(__file__).parent / "comparex_history.sqlite3"
st.set_page_config(page_title="CompareX AI", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
:root { color-scheme: light; }
html, body, [class*="css"] {font-family:Arial,Helvetica,sans-serif; color:#1f2937}
.stApp {background:#f5f7f8; color:#1f2937}
[data-testid="stHeader"] {background:rgba(245,247,248,.96)}
[data-testid="stSidebar"] {background:#eaf0f2; border-right:1px solid #d7e0e4}
[data-testid="stSidebar"] * {color:#24343d}
h1,h2,h3,h4 {color:#172b36; letter-spacing:-.025em}
.hero {padding:1.45rem 1.65rem; border-radius:14px; background:#173b4d; color:#fff; margin-bottom:1.1rem}
.hero h1, .hero p {color:#fff !important}
.hero p {color:#e4edf1 !important; margin-bottom:.1rem}
.eyebrow {text-transform:uppercase; letter-spacing:.12em; font-weight:700; font-size:.72rem; color:#a8d8cd !important}
[data-testid="stMetric"] {background:#fff; color:#1f2937; border:1px solid #dce4e8; padding:14px 16px; border-radius:10px}
[data-testid="stMetric"] label, [data-testid="stMetricLabel"], [data-testid="stMetricValue"], [data-testid="stMetricDelta"] {color:#263943 !important}
[data-testid="stAlert"] {background:#fff; color:#253640; border:1px solid #dce4e8}
[data-testid="stAlert"] p, [data-testid="stAlert"] div {color:#253640}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stTextArea"] textarea {background:#fff !important; color:#1f2937 !important; border:1px solid #aebdc5 !important}
[data-testid="stTextInput"] input::placeholder, [data-testid="stTextArea"] textarea::placeholder {color:#657782 !important; opacity:1}
[data-baseweb="select"] > div {background:#fff; color:#1f2937; border-color:#aebdc5}
[data-baseweb="select"] *, [data-baseweb="popover"] * {color:#1f2937}
[data-testid="stExpander"] {background:#fff; border:1px solid #dce4e8; border-radius:10px}
[data-testid="stExpander"] summary, [data-testid="stExpander"] p {color:#253640}
[data-testid="stDataFrame"] {background:#fff; border:1px solid #dce4e8; border-radius:8px}
.stMarkdown, .stCaption, [data-testid="stCaptionContainer"] {color:#344650}
a {color:#12665f !important}
.stButton button {background:#fff; color:#24343d; border:1px solid #aebdc5; border-radius:8px}
.stButton button:hover {background:#eef4f3; color:#173b4d; border-color:#547d78}
.stButton button[kind="primary"], .stDownloadButton button {background:#176b63; color:#fff; border-color:#176b63}
.stButton button[kind="primary"] *, .stDownloadButton button * {color:#fff !important}
.stButton button[kind="primary"]:hover, .stDownloadButton button:hover {background:#12564f; color:#fff; border-color:#12564f}
[data-testid="stSlider"] [role="slider"] {background:#176b63; border-color:#176b63}
hr {border-color:#d7e0e4}
</style>""", unsafe_allow_html=True)

if "products" not in st.session_state:
    st.session_state.products = []
if "loaded_demo" not in st.session_state:
    st.session_state.loaded_demo = False

with st.sidebar:
    st.markdown("## ⚖️ CompareX AI")
    st.caption("Evidence-led electronics comparisons")
    page = st.radio("Workspace", ["Compare", "History", "How it works"], label_visibility="collapsed")
    st.divider()
    st.markdown("### Your priorities")
    st.caption("Tune how the relative score balances value and specs.")
    weights = {"price": st.slider("Price value", 0, 10, 7), "ram_gb": st.slider("Memory", 0, 10, 4), "storage_gb": st.slider("Storage", 0, 10, 3), "battery_mah": st.slider("Battery", 0, 10, 5), "display_inches": st.slider("Display size", 0, 10, 3), "refresh_rate_hz": st.slider("Refresh rate", 0, 10, 2), "camera_mp": st.slider("Camera", 0, 10, 4), "weight_g": st.slider("Lightweight", 0, 10, 2)}
    st.caption("Scores are relative across the products currently selected.")

if page == "Compare":
    st.markdown('<div class="hero"><div class="eyebrow">Smarter choices start here</div><h1 style="margin:.35rem 0;color:white">Compare what matters.</h1><p>Bring specs, pricing, and real customer feedback into one clear decision.</p></div>', unsafe_allow_html=True)
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.subheader("Your comparison")
        sample_names = [p["name"] for p in load_samples()]
        selected = st.multiselect("Add products from the demo library", sample_names, default=["Aster One Pro", "PixelNova 9", "iPhone 16"] if not st.session_state.loaded_demo else [])
        if selected:
            lookup = {p["name"]: p for p in load_samples()}
            # Keep imported and manually entered products; refresh selected demo entries from sample records.
            custom = [p for p in st.session_state.products if p.get("source_url") not in {"Demo dataset"}]
            st.session_state.products = [lookup[n] for n in selected] + custom
            st.session_state.loaded_demo = True
        with st.expander("Add a product manually or paste listing details", expanded=not bool(st.session_state.products)):
            with st.form("manual_product", clear_on_submit=True):
                c1,c2 = st.columns(2)
                name = c1.text_input("Product name", placeholder="e.g. Galaxy S25")
                brand = c2.text_input("Brand", placeholder="e.g. Samsung")
                category = c1.selectbox("Category", ["Smartphone", "Laptop", "Headphones", "Tablet", "Other electronics"])
                price = c2.number_input("Price (INR)", min_value=0.0, step=1000.0)
                details = st.text_area("Specs or listing text", placeholder="Snapdragon 8 Elite, 12 GB RAM, 256 GB storage, 5000 mAh, 6.7 inch AMOLED, 120 Hz, 50 MP, IP68")
                reviews_text = st.text_area("Customer reviews (one per line)", placeholder="Excellent display and battery lasts all day")
                add = st.form_submit_button("Add product", type="primary", use_container_width=True)
                if add:
                    if not name or not price:
                        st.error("Enter a product name and a price above zero.")
                    else:
                        product = parse_product_text(details, name, price, category, brand)
                        product["reviews"] = [r.strip() for r in reviews_text.splitlines() if r.strip()]
                        st.session_state.products.append(product)
                        st.rerun()
        with st.expander("Import from a public product URL"):
            url = st.text_input("Product page URL", placeholder="https://…", key="product_url")
            if st.button("Try importing page", key="url_import"):
                try:
                    imported = import_url(url)
                    st.session_state.products.append(imported)
                    if imported.get("import_note"):
                        st.warning(imported["import_note"])
                    st.success(f"Added {imported['name']}. Review the imported name, price, and specs before comparing.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not import this page: {exc}. You can still enter its details manually.")
        if st.session_state.products:
            st.markdown("**Products in this comparison**")
            for i, product in enumerate(st.session_state.products):
                c1,c2 = st.columns([5,1])
                c1.write(f"**{product['name']}** · ₹{product.get('price',0):,.0f} · {len(product.get('specs',{}))} specs")
                if c2.button("Remove", key=f"remove_{i}"):
                    st.session_state.products.pop(i)
                    st.rerun()
        else:
            st.info("Choose demo products above, or add your own. No account or API key needed.")
    with right:
        st.subheader("Your priorities")
        st.write("Adjust the sliders in the sidebar. Higher weights give that factor more influence in the score.")
        st.markdown("**Scoring method**")
        st.caption("For each available numeric spec, values are scaled across your selected products. Lower price and weight score higher; higher values for other specs score higher. Missing values are excluded from that product’s calculation.")
        st.markdown("**AI verdict**")
        st.caption("The built-in verdict cites the scores, prices and review summaries. Add GROQ_API_KEY in .env to enable an optional LLM-written narrative.")

    products = st.session_state.products
    if len(products) >= 2:
        st.divider()
        summaries = {p["name"]: analyze_reviews(p.get("reviews", [])) for p in products}
        ranked = score_products(products, weights)
        verdict = build_verdict(products, ranked, weights, summaries)
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        with st.spinner("Preparing evidence-based verdict…"):
            if api_key:
                try:
                    verdict = groq_verdict(products, ranked, summaries, api_key, os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
                    st.caption("Verdict generated with Groq and constrained to the comparison data shown.")
                except Exception as exc:
                    st.warning(f"Groq was unavailable; showing the built-in verdict instead. ({exc})")
        st.subheader("At a glance")
        cols = st.columns(len(ranked))
        for col, product in zip(cols, ranked):
            col.metric(product["name"], f"{product['score']:.0f} / 100", f"₹{product.get('price',0):,.0f}")
        st.markdown("### Comparison verdict")
        st.info(verdict)
        chart_l, chart_r = st.columns([1.1, 1])
        with chart_l:
            st.markdown("#### Weighted scores")
            fig = px.bar(pd.DataFrame(ranked), x="name", y="score", color="score", color_continuous_scale=["#a9c5d8", "#0f766e"], range_y=[0,100], labels={"name":"Product","score":"Score / 100"})
            fig.update_layout(showlegend=False, coloraxis_showscale=False, margin=dict(l=0,r=0,t=12,b=0), plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        with chart_r:
            st.markdown("#### Review themes")
            theme_rows = [{"Product": name, "Theme": theme.title(), "Mentions": count} for name,s in summaries.items() for theme,count in s.get("themes",{}).items()]
            if theme_rows:
                fig2 = px.bar(pd.DataFrame(theme_rows), x="Theme", y="Mentions", color="Product", barmode="group", color_discrete_sequence=["#0f766e","#4f72a2","#db985c","#8869a7"])
                fig2.update_layout(margin=dict(l=0,r=0,t=12,b=0), plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.caption("Add reviews to see common themes.")
        st.markdown("### Specification comparison")
        spec_keys = list(dict.fromkeys(k for p in products for k in p.get("specs", {})))
        rows = [{"Specification": SPEC_LABELS.get(k, k.replace("_", " ").title()), **{p["name"]: p.get("specs",{}).get(k,"—") for p in products}} for k in spec_keys]
        if rows:
            st.dataframe(pd.DataFrame(rows).set_index("Specification"), use_container_width=True)
        st.markdown("### Review insights")
        review_cols = st.columns(len(products))
        for col, product in zip(review_cols, products):
            summary = summaries[product["name"]]
            col.markdown(f"**{product['name']}**")
            col.metric("Review sentiment", summary["sentiment"], f"{summary.get('positive_pct',0)}% positive · {summary.get('review_count',0)} reviews")
            col.caption("Themes: " + (", ".join(f"{k.title()} ({v})" for k,v in summary.get("themes",{}).items()) or "No review themes yet"))
        st.divider()
        b1,b2 = st.columns([1,5])
        if b1.button("Save to history", type="primary"):
            save_comparison(DB_PATH, products, verdict)
            st.success("Comparison saved on this device.")
        b2.download_button("Download PDF report", make_pdf(products, ranked, summaries, verdict), file_name="comparex-comparison.pdf", mime="application/pdf")
    elif products:
        st.warning("Add one more product to see your comparison.")

elif page == "History":
    st.markdown('<div class="hero"><div class="eyebrow">Your saved decisions</div><h1 style="margin:.35rem 0;color:white">Comparison history</h1><p>Saved locally on this device.</p></div>', unsafe_allow_html=True)
    history = recent_comparisons(DB_PATH)
    if not history:
        st.info("Your saved comparisons will appear here.")
    for item in history:
        names = " vs ".join(p["name"] for p in item["products"])
        with st.expander(f"{names} · {item['created_at'][:16].replace('T',' ')} UTC"):
            st.markdown(item["verdict"])
            st.dataframe(pd.DataFrame([{"Product":p["name"],"Price (INR)":p.get("price"),"Specs":", ".join(f"{k}: {v}" for k,v in p.get("specs",{}).items())} for p in item["products"]]), use_container_width=True, hide_index=True)

else:
    st.markdown('<div class="hero"><div class="eyebrow">Transparent by design</div><h1 style="margin:.35rem 0;color:white">How CompareX works</h1><p>Understand what the score means and where the evidence comes from.</p></div>', unsafe_allow_html=True)
    st.markdown("""
### 1. Bring products together
Use the included electronics demo set, enter details by hand, paste listing text for specification extraction, or try importing a public product page. Retailers may block automated requests, so imported details should always be checked.

### 2. Compare specifications fairly
Numeric values are scaled against the products currently shown. Your sidebar weights determine their influence. Price and weight reward lower values; other numeric specifications reward higher values. Missing fields do not count. These scores are relative decision aids, not objective quality ratings.

### 3. Read review themes
The local review analyzer identifies common themes such as battery, camera, display, performance, value, and comfort. Its sentiment is a lightweight keyword estimate, not a validated machine-learning classifier.

### 4. Generate a grounded verdict
The built-in narrative uses the visible prices, scores, and review summaries. If you configure Groq, its optional LLM helps phrase a verdict from the same data. No API key is required to use the core application.

### 5. Save and share
Save comparisons to a local SQLite history and export a PDF summary. Sample data is illustrative and not live retailer information.
""")
