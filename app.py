from datetime import datetime
import pandas as pd
import requests
import streamlit as st

# --- Page Configuration ---
st.set_page_config(
    page_title="SYComms Sales Command Center", page_icon="📊", layout="wide"
)

st.title("📊 SYComms Sales Command Center & Pipeline")


# --- Zoho CRM Connection & Loading ---
ZOHO_ACCOUNTS_URL = "https://accounts.zoho.eu/oauth/v2/token"
ZOHO_API_DOMAIN = "https://www.zohoapis.eu"
DEAL_FIELDS = "Deal_Name,Owner,Appt_Date_Time,Potential_Value,Services_Value,Stage,Closing_Date"


@st.cache_data(ttl=270)  # Zoho access tokens last 1hr; refresh well before that
def get_access_token():
    try:
        creds = st.secrets["zoho"]
    except Exception as err:
        raise RuntimeError(
            f"Missing Zoho credentials in Streamlit secrets. Details: {err}"
        )

    try:
        resp = requests.post(
            ZOHO_ACCOUNTS_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": creds["client_id"],
                "client_secret": creds["client_secret"],
                "refresh_token": creds["refresh_token"],
            },
            timeout=15,
        )
        payload = resp.json()
    except Exception as err:
        raise RuntimeError(f"Could not reach Zoho accounts server. Details: {err}")

    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"Zoho authentication failed: {payload}")
    return token


@st.cache_data(ttl=30)
def load_data():
    token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    records = []
    page = 1
    while True:
        try:
            resp = requests.get(
                f"{ZOHO_API_DOMAIN}/crm/v2/Deals",
                headers=headers,
                params={
                    "fields": DEAL_FIELDS,
                    "per_page": 200,
                    "page": page,
                    "sort_by": "Modified_Time",
                    "sort_order": "desc",
                },
                timeout=20,
            )
        except Exception as err:
            raise RuntimeError(f"Could not reach Zoho CRM API. Details: {err}")

        if resp.status_code == 204:
            break  # no data at all
        if resp.status_code != 200:
            raise RuntimeError(
                f"Zoho CRM API returned an error (status {resp.status_code}): {resp.text}"
            )

        payload = resp.json()
        records.extend(payload.get("data", []))
        info = payload.get("info", {})
        if not info.get("more_records"):
            break
        page += 1

    rows = []
    for r in records:
        owner = r.get("Owner") or {}
        appt_raw = r.get("Appt_Date_Time")
        appt_str = ""
        if appt_raw:
            try:
                # Zoho returns ISO 8601 with timezone offset, e.g. 2026-09-10T14:00:00+01:00
                dt = datetime.fromisoformat(appt_raw)
                appt_str = dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                appt_str = appt_raw

        rows.append(
            {
                "Client Name": r.get("Deal_Name") or "",
                "Sales Rep": owner.get("name") or "Unassigned",
                "Appointment Date": appt_str,
                "Lease Value (£)": float(r.get("Potential_Value") or 0),
                "Services Value (£)": float(r.get("Services_Value") or 0),
                "Combined Value (£)": 0.0,
                "Status": r.get("Stage") or "",
                "Notes": "",
            }
        )

    return pd.DataFrame(rows)


try:
    df = load_data()
except Exception as e:
    st.error(f"🚨 Zoho CRM Connection Error: {e}")
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
            df[col] = (
                pd.to_numeric(
                    df[col].astype(str).str.replace(r"[^\d.]", "", regex=True),
                    errors="coerce",
                )
                .fillna(0)
                .astype(float)
            )
        else:
            df[col] = 0.0

    # Auto-calculate Total Value if needed
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

# 1. Timeframe Selector
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

st.sidebar.divider()
show_financials = st.sidebar.checkbox(
    "📊 Show Pipeline Financials (Beta)", value=False
)

# --- Top-Line Volume & Health KPIs ---
total_deals_count = len(filtered_df)

# Grouping stage counts flexibly
def count_stages(stages):
    if filtered_df.empty or "Status" not in filtered_df.columns:
        return 0
    return len(filtered_df[filtered_df["Status"].str.lower().isin([s.lower() for s in stages])])

early_stages_count = count_stages(["Meeting Booked", "Booked", "2nd Dem", "Pending"])
active_closing_count = count_stages(["Create Proposal", "Send for Signature", "Negotiations", "On-Hold"])
won_count = count_stages(["Sold", "Closed Won"])
lost_count = count_stages(["Closed Lost", "Not Sold", "Lost", "Unsuccessful"])

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Active Deals", f"{total_deals_count}")
col2.metric("Early Appointments", f"{early_stages_count}")
col3.metric("In Progress / Closing", f"{active_closing_count}")
col4.metric("Won / Closed", f"{won_count} Won ({lost_count} Lost)")

# Optional Financial KPIs if toggled on
if show_financials:
    st.markdown("### 💰 Financial Overview")
    total_pipeline = filtered_df["Total Value (£)"].sum()
    sold_val = filtered_df[filtered_df["Status"].str.lower().isin(["sold", "closed won"])]["Total Value (£)"].sum()
    
    fcol1, fcol2 = st.columns(2)
    fcol1.metric("Total Pipeline Value", f"£{total_pipeline:,.2f}")
    fcol2.metric("Won Revenue", f"£{sold_val:,.2f}")

st.divider()

# --- Main Dashboard Tabs ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Pipeline Schedule",
    "🏆 Consultant Leaderboard",
    "🗓️ Calendar View",
    "📋 Stage Breakdown Summary",
])

with tab1:
    st.subheader(f"Active Sales Diary & Status ({timeframe_option})")
    if filtered_df.empty:
        st.info("No records found matching your selected timeframe and filters.")
    else:
        display_df = filtered_df.sort_values(by="Parsed Date", ascending=True).copy()
        
        cols_to_display = [
            "Appointment Date",
            "Client Name",
            "Sales Rep",
            "Status",
            "Notes",
        ]
        
        if show_financials:
            display_df["Lease Value (£)"] = display_df["Lease Value (£)"].apply(lambda x: f"£{x:,.2f}")
            display_df["Services Value (£)"] = display_df["Services Value (£)"].apply(lambda x: f"£{x:,.2f}")
            display_df["Total Value (£)"] = display_df["Total Value (£)"].apply(lambda x: f"£{x:,.2f}")
            cols_to_display = [
                "Appointment Date",
                "Client Name",
                "Sales Rep",
                "Lease Value (£)",
                "Services Value (£)",
                "Total Value (£)",
                "Status",
                "Notes",
            ]

        st.dataframe(
            display_df[cols_to_display],
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
                Deals_Won=("Status", lambda x: sum(x.str.lower().isin(["sold", "closed won"]))),
                Deals_In_Progress=("Status", lambda x: sum(x.str.lower().isin(["create proposal", "send for signature", "negotiations", "on-hold"]))),
                Deals_Booked=("Status", lambda x: sum(x.str.lower().isin(["meeting booked", "booked", "2nd dem", "pending"]))),
            )
            .reset_index()
        )
        st.dataframe(rep_summary, use_container_width=True, hide_index=True)
    else:
        st.info("Insufficient data for leaderboard metrics in this timeframe.")

with tab3:
    st.subheader("🗓️ Visual Team Diary")

    calendar_events = []
    status_colors = {
        "Sold": "#28a745",
        "Closed Won": "#28a745",
        "2nd Dem": "#17a2b8",
        "Meeting Booked": "#ffc107",
        "Booked": "#ffc107",
        "Pending": "#6c757d",
        "On-Hold": "#fd7e14",
        "Create Proposal": "#6610f2",
        "Send for Signature": "#007bff",
        "Negotiations": "#20c997",
        "Closed Lost": "#dc3545",
        "Not Sold": "#dc3545",
    }

    for _, row in filtered_df.iterrows():
        if pd.notna(row["Parsed Date"]):
            status_str = str(row["Status"])
            color = status_colors.get(status_str, "#6c757d")
            title_text = f"{row['Client Name']} - {status_str} [{row['Sales Rep']}]"
            
            if show_financials:
                title_text = f"{row['Client Name']} (£{row['Total Value (£)']:,.0f}) - {status_str} [{row['Sales Rep']}]"

            calendar_events.append({
                "title": title_text,
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
    st.subheader("📊 Detailed Stage Volume Breakdown")
    if not time_filtered_df.empty:
        all_tracked_stages = [
            "Meeting Booked",
            "Booked",
            "2nd Dem",
            "Pending",
            "Create Proposal",
            "Send for Signature",
            "Negotiations",
            "On-Hold",
            "Sold",
            "Closed Won",
            "Closed Lost",
            "Not Sold"
        ]
        
        stage_counts = []
        for stage in all_tracked_stages:
            count = len(time_filtered_df[time_filtered_df["Status"].str.lower() == stage.lower()])
            stage_counts.append({"Stage / Status": stage, "Total Count": count})
            
        stage_df = pd.DataFrame(stage_counts)
        st.dataframe(stage_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data available for stage breakdown.")
