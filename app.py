import gspread
import pandas as pd
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_calendar import calendar

# --- Page Configuration ---
st.set_page_config(
    page_title="Sales Live Tracker", page_icon="📊", layout="wide"
)

st.title("📊 Sales Team Live Appointment & Value Tracker")


# --- Data Connection & Loading ---
@st.cache_data(ttl=30)  # Refreshes data automatically every 30 seconds
def load_data():
  scope = [
      "https://spreadsheets.google.com/feeds",
      "https://www.googleapis.com/auth/drive",
  ]

  # Pulls credentials securely from your .streamlit/secrets.toml (or Streamlit Cloud secrets)
  creds_dict = dict(st.secrets["gcp_service_account"])
  creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
  client = gspread.authorize(creds)

  # Open your Google Sheet by its exact title name (update if you named it differently)
  sheet = client.open("SYComms Sales Tracker Sheet").worksheet("Appointments")

  data = sheet.get_all_records()
  df = pd.DataFrame(data)
  return df


# Load the data safely, with a friendly fallback if the sheet is empty or columns are missing
try:
  df = load_data()
  # Ensure numeric values for calculations
  if "Potential Value (£)" in df.columns:
    df["Potential Value (£)"] = pd.to_numeric(
        df["Potential Value (£)"], errors="coerce"
    ).fillna(0)
except Exception as e:
  st.error(
      f"Could not load data from Google Sheets. Check your secrets and sheet"
      f" permissions. Error: {e}"
  )
  st.stop()

# --- Check if DataFrame has required columns ---
required_cols = [
    "Client Name",
    "Sales Rep",
    "Appointment Date",
    "Potential Value (£)",
    "Status",
]
missing_cols = [col for col in required_cols if col not in df.columns]

if missing_cols:
  st.warning(
      f"Your Google Sheet is missing these expected columns: {missing_cols}. "
      "Please make sure your Sheet header row matches: Client Name | Sales Rep |"
      " Appointment Date | Potential Value (£) | Status | Notes"
  )
  st.stop()

# --- Sidebar Filters ---
st.sidebar.header("Filter Views")
rep_options = ["All"] + list(df["Sales Rep"].unique()) if not df.empty else ["All"]
status_options = (
    ["All"] + list(df["Status"].unique()) if not df.empty else ["All"]
)

selected_rep = st.sidebar.selectbox("Filter by Rep", rep_options)
selected_status = st.sidebar.selectbox("Filter by Status", status_options)

filtered_df = df.copy()
if selected_rep != "All":
  filtered_df = filtered_df[filtered_df["Sales Rep"] == selected_rep]
if selected_status != "All":
  filtered_df = filtered_df[filtered_df["Status"] == selected_status]

# --- Top-Line Financial KPIs ---
total_pipeline = filtered_df["Potential Value (£)"].sum()
sold_val = filtered_df[filtered_df["Status"] == "Sold"][
    "Potential Value (£)"
].sum()
sat_val = filtered_df[filtered_df["Status"] == "Sat"][
    "Potential Value (£)"
].sum()
lost_val = filtered_df[filtered_df["Status"] == "Lost"][
    "Potential Value (£)"
].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Filtered Pipeline", f"£{total_pipeline:,.0f}")
col2.metric("Revenue Won (Sold)", f"£{sold_val:,.0f}")
col3.metric("Attended (Sat)", f"£{sat_val:,.0f}")
col4.metric("Lost Value", f"£{lost_val:,.0f}")

st.divider()

# --- Calendar View Mapping ---
st.subheader("🗓️ Live Calendar Overview")

status_colors = {
    "Sold": "#28a745",  # Green
    "Sat": "#17a2b8",  # Teal / Blue
    "Pending": "#ffc107",  # Yellow / Orange
    "Lost": "#dc3545",  # Red
}

calendar_events = []
for _, row in filtered_df.iterrows():
  # Handle blank or invalid dates gracefully
  if row["Appointment Date"]:
    color = status_colors.get(str(row["Status"]), "#6c757d")
    calendar_events.append({
        "title": (
            f"{row['Client Name']} (£{row['Potential Value (£)']:,.0f}) -"
            f" {row['Status']} ({row['Sales Rep']})"
        ),
        "start": str(row["Appointment Date"]),
        "backgroundColor": color,
        "borderColor": color,
    })

calendar_options = {
    "initialView": "dayGridMonth",
    "headerToolbar": {
        "left": "prev,next today",
        "center": "title",
        "right": "dayGridMonth,timeGridWeek,timeGridDay",
    },
    "editable": False,
    "selectable": True,
}

calendar(events=calendar_events, options=calendar_options)

# --- Raw Data Table Toggle ---
with st.expander("View Raw Spreadsheet Data"):
  st.dataframe(filtered_df, use_container_width=True)
