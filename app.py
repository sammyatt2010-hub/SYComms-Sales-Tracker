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

  # Standardize date parsing (handles DD/MM/YYYY)
  if "Appointment Date" in df.columns:
    df["Parsed Date"] = pd.to_datetime(
        df["Appointment Date"], errors="coerce", dayfirst=True
    )
  else:
    df["Parsed Date"] = pd.NaT

# --- Sidebar Controls & Filters ---
st.sidebar.header("🔍 Filters & Timeframes")

# 1. Timeframe Selector
timeframe_option = st.sidebar.selectbox(
    "Select Timeframe View",
    ["All Time", "Month-to-Date (MTD)", "Specific Month", "Quarterly", "Yearly"],
)

# Dynamic time filters based on selection
current_date = datetime.now()
time_filtered_df = df.copy()

if timeframe_option == "Month-to-Date (MTD)":
  time_filtered_df = time_filtered_df[
      (time_filtered_df["Parsed Date"].dt.year == current_date.year)
      & (time_filtered_df["Parsed Date"].dt.month == current_date.month)
      & (time_filtered_df["Parsed Date"] <= pd.Timestamp(current_date))
  ]
elif timeframe_option == "Specific Month":
  # Generate a list of available years/months from data or current year
  available_months = (
      df["Parsed Date"]
      .dropna()
      .dt.to_period("M")
      .unique()
      .sort_values(ascending=False)
  )
  month_str_options = [m.strftime("%B %Y") for m in available_months]
  if not month_str_options:
    month_str_options = [current_date.strftime("%B %Y")]

  selected_month_str = st.sidebar.selectbox(
      "Choose Month", month_str_options
  )
  chosen_period = pd.to_datetime(selected_month_str, format="%B %Y")

  time_filtered_df = time_filtered_df[
      (time_filtered_df["Parsed Date"].dt.year == chosen_period.year)
      & (time_filtered_df["Parsed Date"].dt.month == chosen_period.month)
  ]
elif timeframe_option == "Quarterly":
  current_quarter = (current_date.month - 1) // 3 + 1
  selected_q = st.sidebar.selectbox(
      "Select Quarter", [1, 2, 3, 4], index=current_quarter - 1
  )
  selected_year = st.sidebar.selectbox(
      "Select Year",
      [current_date.year, current_date.year - 1, current_date.year - 2],
  )
  time_filtered_df = time_filtered_df[
      (time_filtered_df["Parsed Date"].dt.year == selected_year)
      & (time_filtered_df["Parsed Date"].dt.quarter == selected_q)
  ]
elif timeframe_option == "Yearly":
  selected_year = st.sidebar.selectbox(
      "Select Year",
      [current_date.year, current_date.year - 1, current_date.year - 2],
  )
  time_filtered_df = time_filtered_df[
      time_filtered_df["Parsed Date"].dt.year == selected_year
  ]

st.sidebar.divider()

# 2. Consultant & Status Dropdown Filters
rep_options = (
    ["All"] + list(time_filtered_df["Sales Rep"].unique())
    if not time_filtered_df.empty
    else ["All"]
)
status_options = (
    ["All"] + list(time_filtered_df["Status"].unique())
    if not time_filtered_df.empty
    else ["All"]
)

selected_rep = st.sidebar.selectbox("Filter by Consultant", rep_options)
selected_status = st.sidebar.selectbox("Filter by Status", status_options)

filtered_df = time_filtered_df.copy()
if selected_rep != "All":
  filtered_df = filtered_df[filtered_df["Sales Rep"] == selected_rep]
if selected_status != "All":
  filtered_df = filtered_df[filtered_df["Status"] == selected_status]

# --- Top-Line Financial KPIs ---
total_pipeline = filtered_df["Potential Value (£)"].sum()
sold_val = filtered_df[filtered_df["Status"].str.lower() == "sold"][
    "Potential Value (£)"
].sum()
sat_val = filtered_df[filtered_df["Status"].str.contains("Sat", case=False, na=False)][
    "Potential Value (£)"
].sum()

# Catch both "Lost" and "Not Sold" variations for the lost value metric
lost_val = filtered_df[
    filtered_df["Status"]
    .str.lower()
    .isin(["lost", "not sold", "unsold", "unsuccessful"])
]["Potential Value (£)"].sum()

total_closed = sold_val + lost_val
win_rate = (sold_val / total_closed * 100) if total_closed > 0 else 0.0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Filtered Pipeline", f"£{total_pipeline:,.0f}")
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
  st.subheader(
      f"Active Sales Pipeline & Appointments ({timeframe_option})"
  )
  if filtered_df.empty:
    st.info("No records found matching your selected timeframe and filters.")
  else:
    display_df = filtered_df.sort_values(by="Parsed Date", ascending=True)
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
  st.subheader(f"Consultant Performance Breakdown ({timeframe_option})")
  if not time_filtered_df.empty:
    rep_summary = (
        time_filtered_df.groupby("Sales Rep")
        .agg(
            Total_Appointments=("Client Name", "count"),
            Pipeline_Value=("Potential Value (£)", "sum"),
            Won_Value=(
                "Potential Value (£)",
                lambda x: x[
                    time_filtered_df.loc[x.index, "Status"].str.lower()
                    == "sold"
                ].sum(),
            ),
        )
        .reset_index()
    )
    st.dataframe(rep_summary, use_container_width=True, hide_index=True)
  else:
    st.info("Insufficient data for leaderboard metrics in this timeframe.")

with tab3:
  st.subheader("Raw Data Inspector")
  st.dataframe(df, use_container_width=True)
