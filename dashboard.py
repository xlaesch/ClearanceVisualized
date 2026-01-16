import streamlit as st
import pandas as pd
import plotly.express as px
import os

import glob

# Set page configuration
st.set_page_config(page_title="DOHA ISCR Hearing Decisions Visualization", layout="wide")

st.title("DOHA ISCR Hearing Decisions Visualization")

# Find available data files
csv_files = glob.glob("classified_cases*.csv")
if not csv_files:
    st.error("No classification files found (classified_cases*.csv). Please run main.py first.")
    st.stop()

# Let user select file if multiple
selected_file = st.sidebar.selectbox("Select Dataset", csv_files, index=0)
DATA_FILE = selected_file

@st.cache_data
def load_data(file_path, last_updated):
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_csv(file_path, on_bad_lines='skip')
    except Exception as e:
        st.warning(f"Error reading CSV (might be writing in progress): {e}")
        return pd.DataFrame()
    
    # Ensure columns exist
    required_cols = ["category_level_1", "category_level_2", "case_id", "notes", "confidence"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = "" # Fill missing columns if any
    
    # Fill NAs for visualization
    df["category_level_1"] = df["category_level_1"].fillna("Unknown")
    df["category_level_2"] = df["category_level_2"].fillna("Unknown")
    df["notes"] = df["notes"].fillna("")
    return df

if os.path.exists(DATA_FILE):
    last_updated = os.path.getmtime(DATA_FILE)
else:
    last_updated = 0

df = load_data(DATA_FILE, last_updated)
if df is None:
    st.error(f"File `{DATA_FILE}` not found. Please run the classification script first.")
    st.stop()

if df.empty:
    st.warning("The dataset is empty.")
    st.stop()

# --- Visualization Section ---
st.subheader("Taxonomy Distribution (Sunburst)")
st.markdown("Click on a **Category Level 1** slice to expand and see **Category Level 2** breakdown. Click the center to go back up.")

# Prepare data for Sunburst
# We calculate counts for the chart
sunburst_data = df.groupby(["category_level_1", "category_level_2"]).size().reset_index(name="count")

fig = px.sunburst(
    sunburst_data,
    path=["category_level_1", "category_level_2"],
    values="count",
    color="category_level_1",
    height=700,
)
st.plotly_chart(fig, use_container_width=True)


# --- Explorer Section ---
st.divider()
st.subheader("Cases")

# Filters
col1, col2 = st.columns(2)

with col1:
    cat1_options = ["All"] + sorted(df["category_level_1"].unique().tolist())
    selected_cat1 = st.selectbox("Filter by Level 1:", cat1_options)

with col2:
    if selected_cat1 == "All":
        cat2_options = ["All"] + sorted(df["category_level_2"].unique().tolist())
    else:
        filtered_for_cat2 = df[df["category_level_1"] == selected_cat1]
        cat2_options = ["All"] + sorted(filtered_for_cat2["category_level_2"].unique().tolist())
    
    selected_cat2 = st.selectbox("Filter by Level 2:", cat2_options)

# Filter Logic
filtered_df = df.copy()
if selected_cat1 != "All":
    filtered_df = filtered_df[filtered_df["category_level_1"] == selected_cat1]
if selected_cat2 != "All":
    filtered_df = filtered_df[filtered_df["category_level_2"] == selected_cat2]

st.markdown(f"**Showing {len(filtered_df)} cases**")

# Display as interactive table
st.dataframe(
    filtered_df[["case_id", "category_level_1", "category_level_2", "confidence", "notes"]],
    use_container_width=True,
    column_config={
        "case_id": "Case ID",
        "category_level_1": "Category",
        "category_level_2": "Sub-Category",
        "confidence": st.column_config.NumberColumn("Confidence", format="%.2f"),
        "notes": "Notes",
    },
    hide_index=True
)
