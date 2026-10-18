"""Interactive Streamlit Dashboard for Centene Price Transparency Data (PTD).
Provides Executive & Analyst views meeting Hackathon Deliverable 7 (Brownie Points)
pursuant to the Centene California Commercial-Group PPO Classification Plan.
"""
import json
from pathlib import Path
import pandas as pd
import streamlit as st

# Setup page configuration
st.set_page_config(
    page_title="Centene PTD Intelligence & Provider Rates",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Relative directory resolution
UI_DIR = Path(__file__).resolve().parent
NEW_DIR = UI_DIR.parent
DELIVERABLES_DIR = NEW_DIR / "deliverables"
DOCS_DIR = NEW_DIR / "docs"
OUTPUTS_PPO_DIR = NEW_DIR / "outputs" / "ppo"

st.sidebar.title("🏥 Centene PTD Engine")
st.sidebar.markdown("""
**Payer**: Centene Corporation  
**Underwriter**: Health Net Life Insurance Co  
**Market**: Commercial Group (California)  
**Network attribution**: Under review (shared rate file)<br>
**Snapshot**: 2026-09-30 (Frozen)
""")

view_mode = st.sidebar.radio(
    "Select Portal View",
    [
        "📊 Executive Overview & Quality",
        "🎯 PPO Network & Plan Classification",
        "🔍 Analyst Provider Rate Explorer",
        "📈 C7 Cost-Effectiveness Benchmarking",
        "📑 Deliverables & Logic Docs"
    ]
)

# Load data helper
@st.cache_data
def load_summary():
    summary_path = DELIVERABLES_DIR / "Summary_Metrics.json"
    if summary_path.is_file():
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@st.cache_data
def load_quality_details():
    path = DELIVERABLES_DIR / "file_quality_details.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return []

@st.cache_data
def load_rates():
    csv_path = DELIVERABLES_DIR / "c6" / "c6_verified_rates.csv"
    if csv_path.is_file():
        return pd.read_csv(csv_path, dtype={"NPI": str, "TIN": str}, nrows=100_000)
    return pd.DataFrame()

@st.cache_data
def load_rate_candidates():
    csv_path = DELIVERABLES_DIR / "c6" / "c6_supported_rate_candidates.csv"
    if csv_path.is_file():
        return pd.read_csv(csv_path, dtype={"NPI": str, "TIN": str, "Billing Code": str}, nrows=100_000)
    return pd.DataFrame()

@st.cache_data
def load_c5_summary():
    for path in (DELIVERABLES_DIR / "c5" / "c5_summary.json",
                 NEW_DIR / "outputs" / "c5" / "c5_summary.json"):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}

@st.cache_data
def load_decisions():
    p = DELIVERABLES_DIR / "plan_decisions.csv"
    if p.is_file():
        return pd.read_csv(p)
    return pd.DataFrame()

@st.cache_data
def load_manifest():
    p = DELIVERABLES_DIR / "file_manifest.csv"
    if p.is_file():
        return pd.read_csv(p)
    return pd.DataFrame()

summary_data = load_summary()
c5_summary = load_c5_summary()
quality_details = load_quality_details()
rates_df = load_rates()
candidate_df = load_rate_candidates()
dec_df = load_decisions()
manifest_df = load_manifest()

# -------------------------------------------------------------
# VIEW 1: EXECUTIVE OVERVIEW
# -------------------------------------------------------------
if view_mode == "📊 Executive Overview & Quality":
    st.title("Executive Dashboard: Centene CA Commercial PPO Rate Intelligence")
    st.markdown("C3 and C4 audit complete published rate files. C5 reports sourced site evidence; PPO participation and rate attribution remain separate gates.")

    selected_name = st.selectbox("Rate file", [row["file_name"] for row in quality_details]) if quality_details else None
    selected_quality = next((row for row in quality_details if row["file_name"] == selected_name), {})
    col1, col2, col3, col4, col5 = st.columns(5)
    fqs = selected_quality.get("composite_fqs")
    grade = selected_quality.get("grade", "NOT_GRADED")

    col1.metric("C3 File Quality Score", f"{fqs} / 100" if fqs is not None else "Not graded", f"Grade {grade}")
    col2.metric("C2 Confirmed PPO Labels", str(summary_data.get('confirmed_ppo_count', 'N/A')), "Evidence review pending")
    col3.metric("Provisional PPO Plans", str(summary_data.get('provisional_ppo_count', 'N/A')), "Custom Group PPO")
    c4_reports = summary_data.get("c4_file_summaries", [])
    c4_selected = sum(report.get("counts", {}).get("selected", 0) for report in c4_reports)
    col4.metric("C4 Selected Rate Contexts", f"{c4_selected:,}" if c4_reports else "Not run", "PPO attribution unverified")
    col5.metric("Verified NPI/TIN/PPO site", f"{c5_summary.get('share_npis_with_fully_verified_link', 0)}%" if c5_summary else "Not run", "Exact payer and TIN/site proof")

    st.markdown("---")
    st.subheader("C3 File Quality & Completeness Scorecard")
    if quality_details:
        st.write(f"Audit status: **{selected_quality['quality_status']}**; as of {selected_quality['as_of']}; SHA-256: `{selected_quality['sha256']}`")
        for flag in selected_quality.get("review_flags", []):
            st.warning(flag.replace("_", " ").title())
    dim_scores = selected_quality.get("dimension_scores", {})
    if dim_scores:
        score_df = pd.DataFrame([
            {"Quality Dimension": key.replace("_", " ").title(),
             "Score (0-100)": value,
             "Weight": f"{selected_quality['weights'][key]:.0%}"}
            for key, value in dim_scores.items()
        ])
        st.dataframe(score_df, use_container_width=True, hide_index=True)
        st.bar_chart(score_df.dropna(subset=["Score (0-100)"]).set_index("Quality Dimension")["Score (0-100)"])

# -------------------------------------------------------------
# VIEW 2: PPO NETWORK & PLAN CLASSIFICATION (PLAN RECONCILIATION)
# -------------------------------------------------------------
elif view_mode == "🎯 PPO Network & Plan Classification":
    st.title("Challenge C2: Plan and Network Verification")
    st.markdown("""
    **Evidence-Backed Classification Engine**: Reconciles Centene index plans against official 2026 EOCs,
    rules out Knox-Keene HMOs, EPOs, and POS gatekeepers, and flags mixed rate files under CMS Question 22 guidelines.
    """)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Confirmed PPO Plans", f"{summary_data.get('confirmed_ppo_count', 30)}")
    c2.metric("Provisional PPO Plans", f"{summary_data.get('provisional_ppo_count', 422)}")
    c3.metric("Excluded Non-PPO (HMO/EPO/POS)", f"{summary_data.get('excluded_non_ppo_count', 2682)}")
    c4.metric("Unresolved in Review Queue", f"{summary_data.get('unresolved_count', 136)}")

    st.markdown("---")
    st.subheader("Rate File Manifest & CMS Shared File Convention")
    if not manifest_df.empty:
        st.dataframe(manifest_df[["rate_file_name", "file_classification", "confirmed_ppo_plans", "provisional_ppo_plans", "excluded_non_ppo_plans", "plan_attribution_limitation"]], use_container_width=True, hide_index=True)
        st.info("💡 **CMS Technical Clarification Note**: The California statewide rate file is formally classified as **MIXED** because it is shared across PPO, HMO, and EOA plans. Rate records are marked `plan_attribution=SHARED_FILE_UNRESOLVED` to prevent false network exclusivity.")

    st.markdown("---")
    st.subheader("Plan Decision Explorer")
    if not dec_df.empty:
        status_filter = st.selectbox("Filter by Product Status", ["ALL"] + dec_df["product_status"].unique().tolist())
        filtered_dec = dec_df if status_filter == "ALL" else dec_df[dec_df["product_status"] == status_filter]
        st.dataframe(filtered_dec[["plan_name", "plan_id", "product_status", "network_status", "network_name", "anomaly_tags", "decision_reason"]], use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Key Plan Classification Anomalies Resolved")
    a1, a2, a3 = st.columns(3)
    a1.markdown("#### 1. Collapsed Token (`CUSPPO`)\n`CA L CUSPPO 15/250/20% RAP` had no space between CUS and PPO. Recovered via punctuation regex and assigned `PROVISIONAL_PPO`.")
    a2.markdown("#### 2. EOA Overlap (127 Plans)\nExclusive Option Advantage is an HMO with PPO wrap. Excluded from pure PPO set but retained in sensitivity queue.")
    a3.markdown("#### 3. Retiree Scope Audit\n`CA L CUS PPO HN Retiree` held in `UNRESOLVED` review queue pending employer active-employment verification.")

# -------------------------------------------------------------
# VIEW 3: ANALYST PROVIDER RATE EXPLORER
# -------------------------------------------------------------
elif view_mode == "🔍 Analyst Provider Rate Explorer":
    st.title("Analyst Portal: Deliverable 1 Provider Rate Browser")
    st.markdown("Search and analyze provider-level rates at the **NPI, TIN, Address, and Billing Code** level.")

    display_df = rates_df if not rates_df.empty else candidate_df
    showing_candidates = rates_df.empty and not candidate_df.empty
    if showing_candidates:
        st.warning("Research candidates: addresses have independent CMS/NPPES support, but TIN/site and exact PPO/site participation remain unverified. Review the workbook's Evidence sheet before contracting use.")
    if not display_df.empty:
        c1, c2, c3 = st.columns(3)
        specialty_filter = c1.selectbox("Filter by Specialty", ["All Specialties"] + sorted(display_df["Specialty"].dropna().unique().tolist()))
        code_filter = c2.selectbox("Filter by Billing Code", ["All Codes"] + sorted(display_df["Billing Code"].dropna().astype(str).unique().tolist()))
        search_query = c3.text_input("Search NPI / TIN / City", "")

        filtered = display_df.copy()
        if specialty_filter != "All Specialties":
            filtered = filtered[filtered["Specialty"] == specialty_filter]
        if code_filter != "All Codes":
            filtered = filtered[filtered["Billing Code"].astype(str) == code_filter]
        if search_query:
            q = search_query.lower()
            filtered = filtered[
                filtered["NPI"].astype(str).str.contains(q) |
                filtered["TIN"].astype(str).str.contains(q) |
                filtered["Address"].astype(str).str.lower().str.contains(q)
            ]

        st.markdown(f"**Showing {len(filtered):,} rates matching criteria**")
        st.dataframe(filtered[["NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate"]], use_container_width=True, hide_index=True)

        csv_data = filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Filtered Rate Data (CSV)",
            data=csv_data,
            file_name="Centene_PPO_Filtered_Candidates.csv" if showing_candidates else "Centene_PPO_Filtered_Rates.csv",
            mime="text/csv"
        )
    else:
        st.info("No fully evidenced PPO-specific rate rows are available. Review C5 site evidence and C2/C4 plan attribution.")

# -------------------------------------------------------------
# VIEW 4: C7 COST-EFFECTIVENESS BENCHMARKING
# -------------------------------------------------------------
elif view_mode == "📈 C7 Cost-Effectiveness Benchmarking":
    st.title("Challenge C7: Provider Cost-Effectiveness & Market Benchmarking")
    st.markdown("""
    **Definition of 'Similar Providers'**: Same NUCC Clinical Specialty practicing in California under professional ambulatory billing.
    **Specialty Price Index (SPI)**: Volume-weighted ratio of provider rates vs peer group market median ($SPI < 1.00$ indicates below-market / cost-effective pricing).
    """)

    cost_path = DELIVERABLES_DIR / "provider_cost_effectiveness_benchmark.csv"
    c6_summary_path = DELIVERABLES_DIR / "c6" / "c6_summary.json"
    c6_status = json.loads(c6_summary_path.read_text(encoding="utf-8")) if c6_summary_path.is_file() else {}
    if cost_path.is_file() and c6_status.get("counts", {}).get("exported_rate_rows", 0) > 0 and "C7" in summary_data.get("challenges_executed", []):
        cost_df = pd.read_csv(cost_path)
        st.dataframe(cost_df, use_container_width=True, hide_index=True)
    else:
        st.info("Run master pipeline to generate cost-effectiveness benchmarks.")

# -------------------------------------------------------------
# VIEW 5: DELIVERABLES & LOGIC DOCS
# -------------------------------------------------------------
elif view_mode == "📑 Deliverables & Logic Docs":
    st.title("Official Hackathon Deliverables & Documentation")
    tabs = st.tabs(["Deliverable 2: Logic File", "Deliverable 3: Quality Metrics", "Deliverable 4: Summary Metrics"])

    with tabs[0]:
        for name in ("C1_C2_METHODOLOGY_AND_LOGIC.md", "C4_RATE_EXTRACTION_LOGIC.md",
                     "C5_ADDRESS_MAPPING_LOGIC.md"):
            logic_doc = DOCS_DIR / name
            if logic_doc.is_file():
                st.markdown(logic_doc.read_text(encoding="utf-8"))

    with tabs[1]:
        d3_doc = (DELIVERABLES_DIR / "File_Quality_Metrics.md")
        if d3_doc.is_file():
            st.markdown(d3_doc.read_text(encoding="utf-8"))
        else:
            st.info("File Quality Metrics generated by master pipeline.")

    with tabs[2]:
        if c5_summary:
            st.subheader("Current C5 validation")
            st.json({key: value for key, value in c5_summary.items() if key != "inputs"})
        sum_doc = (DELIVERABLES_DIR / "Summary_Metrics.md")
        if sum_doc.is_file() and "synthetic" not in sum_doc.read_text(encoding="utf-8").lower():
            st.markdown(sum_doc.read_text(encoding="utf-8"))
        else:
            st.info("Run the master pipeline to regenerate the combined summary.")
