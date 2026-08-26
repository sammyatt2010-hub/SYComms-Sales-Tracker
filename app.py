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
  for col in [
      "Lease Value (£)",
      "Services Value (£)",
      "Combined Value (£)",
  ]:
    if col in df.columns:
      df[col] = pd.to_numeric(
          df[col].astype(str).str.replace(r"[^\d.]", "", regex=True),
          errors="coerce",
      ).fillna(0)
    else:
      df[col] = 0.0

  # If Combined Value is empty/0 but Lease or Services have values, auto-calculate it
  df["Total Value (£)"] = df["Combined Value (£)"]
  mask = df["Total Value (£)"] == 0
  df.loc[mask, "Total Value (£)"] = (
      df.loc[mask, "Lease Value (£)"] + df.loc[mask, "Services Value (£)"]
  )

  # Standardize date parsing (handles DD/MM/YYYY)
  if "Appointment Date" in df.columns:
    df["Parsed Date"] = pd.to_datetime(
        df["Appointment Date"], errors="coerce", dayfirst=True
    )
  else:
    df["Parsed Date"] = pd.NaT

# --- Sidebar Controls & Filters ---
st.sidebar.header("🔍 Filters & Timeframes")

# 1. Timeframe Selector (Defaults to Current Month)
timeframe_options = [
    "Specific Month",
    "Month-to-Date (MTD)",
    "Quarterly",
    "Yearly",
    "All Time",
]
timeframe_option = st.sidebar.selectbox(
    "Select Timeframe View", timeframe_options, index=0
)

current_date = datetime.now()
time_filtered_df = df.copy()

if timeframe_option == "Month-to-Date (MTD)":
  time_filtered_df = time_filtered_df[
      (time_filtered_df["Parsed Date"].dt.year == current_date.year)
      & (time_filtered_df["Parsed Date"].dt.month == current_date.month)
      & (time_filtered_df["Parsed Date"] <= pd.Timestamp(current_date))
  ]
elif timeframe_option == "Specific Month":
  valid_dates = df["Parsed Date"].dropna()
  if not valid_dates.empty:
    available_months = (
        valid_dates.dt.to_period("M").drop_duplicates().sort_values(ascending=False)
    )
    month_str_options = [m.to_timestamp().strftime("%B %Y") for m in available_months]
  else:
    month_str_options = [current_date.strftime("%B %Y")]

  current_month_str = current_date.strftime("%B %Y")
  default_index = (
      month_str_options.index(current_month_str)
      if current_month_str in month_str_options
      else 0
  )

  selected_month_str = st.sidebar.selectbox(
      "Choose Month", month_str_options, index=default_index
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
total_pipeline = filtered_df["Total Value (£)"].sum()
total_lease = filtered_df["Lease Value (£)"].sum()
total_services = filtered_df["Services Value (£)"].sum()

sold_val = filtered_df[filtered_df["Status"].str.lower() == "sold"][
    "Total Value (£)"
].sum()
to_be_sat_val = filtered_df[
    filtered_df["Status"]
    .str.lower()
    .isin(["booked", "pending", "meeting booked", "not sat", ""])
]["Total Value (£)"].sum()
lost_val = filtered_df[
    filtered_df["Status"]
    .str.lower()
    .isin(["lost", "not sold", "closed lost", "unsold", "unsuccessful"])
]["Total Value (£)"].sum()

total_closed = sold_val + lost_val
win_rate = (sold_val / total_closed * 100) if total_closed > 0 else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Total Pipeline (Combined)", f"£{total_pipeline:,.2f}")
col2.metric("Total Lease Value", f"£{total_lease:,.2f}")
col3.metric("Total Services Value", f"£{total_services:,.2f}")

col4, col5, col6, col7 = st.columns(4)
col4.metric("Upcoming / Booked", f"£{to_be_sat_val:,.2f}")
col5.metric("Revenue Won (Sold)", f"£{sold_val:,.2f}")
col6.metric("Lost Value", f"£{lost_val:,.2f}")
col7.metric("Win Rate", f"{win_rate:.1f}%")

st.divider()

# --- Main Dashboard Tabs ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Pipeline Schedule",
    "🏆 Consultant Leaderboard",
    "🗓️ Calendar View",
    "📋 Master Data View",
])

with tab1:
  st.subheader(
      f"Active Sales Pipeline & Appointments ({timeframe_option})"
  )
  if filtered_df.empty:
    st.info("No records found matching your selected timeframe and filters.")
  else:
    display_df = filtered_df.sort_values(by="Parsed Date", ascending=True).copy()
    display_df["Lease Value (£)"] = display_df["Lease Value (£)"].apply(
        lambda x: f"£{x:,.2f}"
    )
    display_df["Services Value (£)"] = display_df["Services Value (£)"].apply(
        lambda x: f"£{x:,.2f}"
    )
    display_df["Combined Value (£)"] = display_df["Combined Value (£)"].apply(
        lambda x: f"£{x:,.2f}"
    )

    st.dataframe(
        display_df[[
            "Appointment Date",
            "Client Name",
            "Sales Rep",
            "Lease Value (£)",
            "Services Value (£)",
            "Combined Value (£)",
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
            Total_Deals=("Client Name", "count"),
            Lease_Total=("Lease Value (£)", "sum"),
            Services_Total=("Services Value (£)", "sum"),
            Combined_Pipeline=("Total Value (£)", "sum"),
            Won_Value=(
                "Total Value (£)",
                lambda x: x[
                    time_filtered_df.loc[x.index, "Status"].str.lower()
                    == "sold"
                ].sum(),
            ),
        )
        .reset_index()
    )
    rep_summary["Lease_Total"] = rep_summary["Lease_Total"].apply(
        lambda x: f"£{x:,.2f}"
    )
    rep_summary["Services_Total"] = rep_summary["Services_Total"].apply(
        lambda x: f"£{x:,.2f}"
    )
    rep_summary["Combined_Pipeline"] = rep_summary["Combined_Pipeline"].apply(
        lambda x: f"£{x:,.2f}"
    )
    rep_summary["Won_Value"] = rep_summary["Won_Value"].apply(
        lambda x: f"£{x:,.2f}"
    )

    st.dataframe(rep_summary, use_container_width=True, hide_index=True)
  else:
    st.info("Insufficient data for leaderboard metrics in this timeframe.")

with tab3:
  st.subheader("🗓️ Visual Team Diary")

  calendar_events = []
  status_colors = {
      "Sold": "#28a745",  # Green
      "Closed Won": "#28a745",  # Green
      "Sat": "#17a2b8",  # Teal
      "Booked": "#ffc107",  # Yellow/Orange
      "Meeting Booked": "#ffc107",  # Yellow/Orange
      "Not Sold": "#dc3545",  # Red
      "Closed Lost": "#dc3545",  # Red
      "Lost": "#dc3545",  # Red
  }

  for _, row in filtered_df.iterrows():
    if pd.notna(row["Parsed Date"]):
      status_str = str(row["Status"])
      color = status_colors.get(status_str, "#6c757d")
      val_formatted = f"£{row['Total Value (£)']:,.0f}"

      calendar_events.append({
          "title": f"{row['Client Name']} ({val_formatted}) - {status_str} [{row['Sales Rep']}]",
          "start": row["Parsed Date"].strftime("%Y-%m-%d"),
          "backgroundColor": color,
          "borderColor": color,
      })

  calendar_options = {
      "initialView": "dayGridMonth",
      "headerToolbar": {
          "left": "prev,next today",
          "center": "title",
          "right": "dayGridMonth,timeGridWeek,listMonth",
      },
      "editable": False,
      "selectable": True,
  }

  try:
    from streamlit_calendar import calendar

    calendar(events=calendar_events, options=calendar_events and calendar_options)
  except ImportError:
    st.warning("Please include `streamlit-calendar` in your requirements.txt.")

with tab4:
  st.subheader("Raw Data Inspector")
  raw_display = df.copy()
  for col in [
      "Lease Value (£)",
      "Services Value (£)",
      "Combined Value (£)",
      "Total Value (£)",
  ]:
    if col in raw_display.columns:
      raw_display[col] = raw_display[col].apply(lambda x: f"£{x:,.2f}")
  st.dataframe(raw_display, use_container_width=True)
