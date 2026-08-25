from datetime import datetime
import gspread
import pandas as pd
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials

# --- Page Configuration ---
st.set_page_config(
    page_title="SYComms Sales Command Center", page_icon="📊", layout="wide"
)

st.title("📊 SYComms Sales Command Center & Pipeline")


# --- Data Connection & Loading ---
@st.cache_data(ttl=30)
def load_data():
  scope = [
      "https://spreadsheets.google.com/feeds",
      "https://www.googleapis.com/auth/drive",
  ]
  creds_dict = dict(st.secrets["gcp_service_account"])
  creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
  client = gspread.authorize(creds)

  sheet = client.open("SYComms Sales Tracker Sheet").worksheet("Appointments")
  data = sheet.get_all_records()
  return pd.DataFrame(data)


try:
  df = load_data()
except Exception as e:
  st.error(
      f"Could not load data from Google Sheets. Check secrets/permissions:"
      f" {e}"
  )
  st.stop()

# --- Data Cleaning & Prep ---
if not df.empty:
  # Clean numerical values
  if "Potential Value (£)" in df.columns:
    df["Potential Value (£)"] = pd.to_numeric(
        df["Potential Value (£)"].astype(str).str.replace(r"[^\d.]", "", regex=True),
        errors="coerce",
    ).fillna(0)

  # Standardize date parsing (handles both YYYY-MM-DD and DD/MM/YYYY)
  if "Appointment Date" in df.columns:
    df["Parsed Date"] = pd.to_datetime(
        df["Appointment Date"], errors="coerce", dayfirst=True
    )
  else:
    df["Parsed Date"] = pd.NaT

# --- Sidebar Filters ---
st.sidebar.header("🔍 Filter Controls")
rep_options = ["All"] + list(df["Sales Rep"].unique()) if not df.empty else ["All"]
status_options = (
    ["All"] + list(df["Status"].unique()) if not df.empty else ["All"]
)

selected_rep = st.sidebar.selectbox("Filter by Consultant", rep_options)
selected_status = st.sidebar.selectbox("Filter by Status", status_options)

filtered_df = df.copy()
if selected_rep != "All":
  filtered_df = filtered_df[filtered_df["Sales Rep"] == selected_rep]
if selected_status != "All":
  filtered_df = filtered_df[filtered_df["Status"] == selected_status]

# --- Top-Line Financial KPIs ---
total_pipeline = filtered_df["Potential Value (£)"].sum()
sold_val = filtered_df[filtered_df["Status"].str.lower() == "sold"][
    "Potential Value (£)"
].sum()

# Catch variations like Sat, Not Sat, Booked, Lost
sat_val = filtered_df[filtered_df["Status"].str.contains("Sat", case=False, na=False)][
    "Potential Value (£)"
].sum()
lost_val = filtered_df[filtered_df["Status"].str.lower() == "lost"][
    "Potential Value (£)"
].sum()

# Calculate conversion rate if possible
total_closed = sold_val + lost_val
win_rate = (sold_val / total_closed * 100) if total_closed > 0 else 0.0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Pipeline", f"£{total_pipeline:,.0f}")
col2.metric("Revenue Won (Sold)", f"£{sold_val:,.0f}")
col3.metric("Attended / Sat", f"£{sat_val:,.0f}")
col4.metric("Lost Value", f"£{lost_val:,.0f}")
col5.metric("Win Rate", f"{win_rate:.1f}%")

st.divider()

# --- Main Dashboard Tabs ---
tab1, tab2, tab3 = st.tabs(
    ["📅 Pipeline Schedule", "🏆 Consultant Leaderboard", "📋 Master Data View"]
)

with tab1:
  st.subheader("Active Sales Pipeline & Appointments")
  if filtered_df.empty:
    st.info("No records found matching your filters.")
  else:
    # Sort by date
    display_df = filtered_df.sort_values(by="Parsed Date", ascending=True)

    # Style presentation columns
    st.dataframe(
        display_df[[
            "Appointment Date",
            "Client Name",
            "Sales Rep",
            "Potential Value (£)",
            "Status",
            "Notes",
        ]],
        use_container_width=True,
        hide_index=True,
    )

with tab2:
  st.subheader("Consultant Performance Breakdown")
  if not df.empty:
    # Group by Rep for leaderboards
    rep_summary = (
        df.groupby("Sales Rep")
        .agg(
            Total_Appointments=("Client Name", "count"),
            Pipeline_Value=("Potential Value (£)", "sum"),
            Won_Value=(
                "Potential Value (£)",
                lambda x: x[
                    df.loc[x.index, "Status"].str.lower() == "sold"
                ].sum(),
            ),
        )
        .reset_index()
    )

    st.dataframe(rep_summary, use_container_width=True, hide_index=True)
  else:
    st.info("Insufficient data for leaderboard metrics.")

with tab3:
  st.subheader("Raw Data Inspector")
  st.dataframe(df, use_container_width=True)
