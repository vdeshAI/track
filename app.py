
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Stakeholder Outreach Intelligence", page_icon="🗂️", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
XLSX_PATH = BASE_DIR / "stakeholder_outreach_intelligence_system.xlsx"

@st.cache_data
def load_data():
    master = pd.read_excel(XLSX_PATH, sheet_name="Journalist_Master")
    pipeline = pd.read_excel(XLSX_PATH, sheet_name="Pipeline")
    templates = pd.read_excel(XLSX_PATH, sheet_name="Messaging_Templates")
    narratives = pd.read_excel(XLSX_PATH, sheet_name="Narrative_Map")
    strategy = pd.read_excel(XLSX_PATH, sheet_name="Strategy_Playbook")
    for df in [master, pipeline, templates, narratives, strategy]:
        df.columns = [str(c).strip() for c in df.columns]
    return master, pipeline, templates, narratives, strategy

def normalize_master(master: pd.DataFrame) -> pd.DataFrame:
    master = master.copy()
    for col in ["Public Email", "Public Phone", "Alt/Public Contact", "X Handle"]:
        master[col] = master[col].fillna("").astype(str)
    for col in ["Influence Score"]:
        master[col] = pd.to_numeric(master[col], errors="coerce").fillna(0)
    # Recompute formula columns for Streamlit use
    master["Contact Route"] = master.apply(
        lambda r: "Email" if r["Public Email"] else ("X / social" if r["X Handle"] else "Research"), axis=1
    )
    master["Contact Coverage"] = (
        (master["Public Email"] != "").astype(int)
        + (master["Public Phone"] != "").astype(int)
        + (master["Alt/Public Contact"] != "").astype(int)
        + (master["X Handle"] != "").astype(int)
    )
    conf_bonus = master["Contact Confidence"].map({"High": 2, "Medium": 1, "Low": 0}).fillna(0)
    risk_penalty = master["Relationship Risk"].map({"High": 1, "Medium": 0, "Low": 0}).fillna(0)
    master["Priority Score"] = (master["Influence Score"] * 2 + conf_bonus + (master["Public Email"] != "").astype(int) * 2 + (master["X Handle"] != "").astype(int) - risk_penalty).round().astype(int)
    return master

if not XLSX_PATH.exists():
    st.error(f"Workbook not found: {XLSX_PATH}")
    st.stop()

master, pipeline, templates, narratives, strategy = load_data()
master = normalize_master(master)

# Normalize pipeline and backfill key fields from master
pipeline = pipeline.copy()
pipeline["ID"] = pd.to_numeric(pipeline["ID"], errors="coerce").astype("Int64")
pipeline["Priority Score"] = pd.to_numeric(pipeline["Priority Score"], errors="coerce")
id_map = master.set_index("ID")[["Name","Publication","Priority Score"]]
for field in ["Name","Publication","Priority Score"]:
    if field in pipeline.columns:
        pipeline[field] = pipeline.apply(lambda r: id_map.loc[r["ID"], field] if pd.notna(r["ID"]) and r["ID"] in id_map.index else r[field], axis=1)

st.title("Stakeholder + Outreach Intelligence System")
st.caption("Public-contact directory, outreach pipeline, templates, and narrative prep in one dashboard.")

with st.sidebar:
    st.header("Filters")
    pubs = st.multiselect("Publication", sorted(master["Publication"].dropna().unique().tolist()), default=sorted(master["Publication"].dropna().unique().tolist()))
    geos = st.multiselect("Geography", sorted(master["Geography"].dropna().unique().tolist()))
    confidence = st.multiselect("Contact confidence", sorted(master["Contact Confidence"].dropna().unique().tolist()), default=sorted(master["Contact Confidence"].dropna().unique().tolist()))
    min_influence = st.slider("Minimum influence score", 1, 5, 3)
    route = st.multiselect("Contact route", sorted(master["Contact Route"].dropna().unique().tolist()))
    search = st.text_input("Search name / role / angle")

filtered = master[master["Publication"].isin(pubs) & (master["Influence Score"] >= min_influence) & (master["Contact Confidence"].isin(confidence))]
if geos:
    filtered = filtered[filtered["Geography"].isin(geos)]
if route:
    filtered = filtered[filtered["Contact Route"].isin(route)]
if search:
    q = search.lower()
    mask = (
        filtered["Name"].fillna("").str.lower().str.contains(q) |
        filtered["Role / Title"].fillna("").str.lower().str.contains(q) |
        filtered["Likely Angle"].fillna("").str.lower().str.contains(q) |
        filtered["Coverage Focus"].fillna("").str.lower().str.contains(q)
    )
    filtered = filtered[mask]

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Dashboard", "Directory", "Pipeline", "Templates", "Strategy"])

with tab1:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Stakeholders", len(filtered))
    c2.metric("Public emails", int(filtered["Public Email"].str.len().gt(0).sum()))
    c3.metric("X handles", int(filtered["X Handle"].str.startswith("@").sum()))
    c4.metric("Avg influence", round(filtered["Influence Score"].mean(), 1) if len(filtered) else 0)
    c5.metric("Avg priority", round(filtered["Priority Score"].mean(), 1) if len(filtered) else 0)

    left, right = st.columns(2)
    if len(filtered):
        pub_counts = filtered.groupby("Publication", dropna=False).size().reset_index(name="Count")
        fig = px.bar(pub_counts, x="Publication", y="Count", title="Filtered stakeholders by publication")
        left.plotly_chart(fig, use_container_width=True)

        route_counts = filtered.groupby("Contact Route", dropna=False).size().reset_index(name="Count")
        fig2 = px.pie(route_counts, names="Contact Route", values="Count", title="Contact route mix")
        right.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No rows match the current filters.")

    st.subheader("Narrative themes to prepare")
    st.dataframe(narratives, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Stakeholder directory")
    display_cols = [
        "Name","Publication","Role / Title","Coverage Focus","Location","Public Email","Public Phone",
        "Alt/Public Contact","X Handle","Contact Confidence","Influence Score","Relationship Risk",
        "Contact Route","Priority Score","Likely Angle","Notes"
    ]
    st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)
    st.download_button(
        "Download filtered CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="filtered_stakeholders.csv",
        mime="text/csv"
    )

    st.subheader("Profile viewer")
    if len(filtered):
        selected = st.selectbox("Select a stakeholder", filtered["Name"].tolist())
        row = filtered[filtered["Name"] == selected].iloc[0]
        a, b = st.columns([1,1])
        with a:
            st.markdown(f"**Publication:** {row['Publication']}")
            st.markdown(f"**Role:** {row['Role / Title']}")
            st.markdown(f"**Coverage:** {row['Coverage Focus']}")
            st.markdown(f"**Geography:** {row['Geography']}")
            st.markdown(f"**Location:** {row['Location']}")
            st.markdown(f"**Likely angle:** {row['Likely Angle']}")
        with b:
            st.markdown(f"**Email:** {row['Public Email'] or '—'}")
            st.markdown(f"**Phone:** {row['Public Phone'] or '—'}")
            st.markdown(f"**Alt contact:** {row['Alt/Public Contact'] or '—'}")
            st.markdown(f"**X:** {row['X Handle'] or '—'}")
            st.markdown(f"**Contact confidence:** {row['Contact Confidence']}")
            st.markdown(f"**Priority score:** {row['Priority Score']}")
        st.markdown(f"**Notes:** {row['Notes']}")
        if pd.notna(row.get("Profile URL")) and row["Profile URL"]:
            st.markdown(f"[Profile URL]({row['Profile URL']})")
        if pd.notna(row.get("Contact Evidence URL")) and row["Contact Evidence URL"]:
            st.markdown(f"[Contact evidence URL]({row['Contact Evidence URL']})")

with tab3:
    st.subheader("Pipeline tracker")
    st.dataframe(pipeline, use_container_width=True, hide_index=True)
    stage_counts = pipeline.groupby("Stage", dropna=False).size().reset_index(name="Count")
    fig3 = px.bar(stage_counts, x="Stage", y="Count", title="Pipeline stage counts")
    st.plotly_chart(fig3, use_container_width=True)

with tab4:
    st.subheader("Reusable outreach templates")
    template_id = st.selectbox("Choose a template", templates["Template ID"].tolist())
    trow = templates[templates["Template ID"] == template_id].iloc[0]
    st.markdown(f"**Use case:** {trow['Use Case']}")
    st.markdown(f"**Subject:** {trow['Subject Line']}")
    st.text_area("Body", trow["Body"], height=240)

with tab5:
    st.subheader("Strategy playbook")
    st.dataframe(strategy, use_container_width=True, hide_index=True)
    st.info("Tip: use public contact details responsibly and keep every pitch narrow, factual, and source-backed.")
