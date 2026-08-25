# --- Main Dashboard Tabs ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Pipeline Schedule",
    "🏆 Consultant Leaderboard",
    "🗓️ Calendar View",
    "📋 Master Data View",
])

# ... (Tabs 1, 2, and 3 stay as they are) ...

with tab4:  # (or tab3 if reordered)
  st.subheader("🗓️ Visual Team Diary")
  st.markdown(
      "Here is the interactive calendar view of your scheduled appointments."
  )

  # Map filtered data into FullCalendar format
  calendar_events = []
  status_colors = {
      "Sold": "#28a745",  # Green
      "Sat": "#17a2b8",  # Teal
      "Booked": "#ffc107",  # Yellow/Orange
      "Not Sold": "#dc3545",  # Red
      "Lost": "#dc3545",  # Red
  }

  for _, row in filtered_df.iterrows():
    if pd.notna(row["Parsed Date"]):
      status_str = str(row["Status"])
      color = status_colors.get(status_str, "#6c757d")

      # Format monetary value nicely for the calendar badge
      val_formatted = f"£{row['Potential Value (£)']:,.0f}"

      calendar_events.append({
          "title": f"{row['Client Name']} ({val_formatted}) - {status_str} [{row['Sales Rep']}]",
          "start": row["Parsed Date"].strftime("%Y-%m-%d"),
          "backgroundColor": color,
          "borderColor": color,
      })

  calendar_options = {
      "initialView": "dayGridMonth",  # Can also be timeGridWeek or listMonth
      "headerToolbar": {
          "left": "prev,next today",
          "center": "title",
          "right": "dayGridMonth,timeGridWeek,listMonth",
      },
      "editable": False,
      "selectable": True,
  }

  # Requires: pip install streamlit-calendar
  try:
    from streamlit_calendar import calendar

    calendar(events=calendar_events, options=calendar_options)
  except ImportError:
    st.warning(
        "Please add `streamlit-calendar` to your requirements.txt to enable the"
        " calendar view component."
    )
