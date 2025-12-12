# components/sidebar.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import date, timedelta
import os

def render_sidebar(default_date, refresh_interval_seconds):
    # Display logo at the top of sidebar
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ISI_logo.png")
    if os.path.exists(logo_path):
        st.sidebar.image(logo_path, use_container_width=True)
    
    st.sidebar.title("Filters & Refresh")

    # Quick date selector
    date_option = st.sidebar.radio(
        "Date Selection",
        options=["Today", "Custom Range"],
        index=0,
        horizontal=True
    )
    
    if date_option == "Today":
        # Use today's date
        today = default_date if default_date else date.today()
        start_date = end_date = today
    else:
        # Date range picker - default to last 7 days ending with default_date
        default_start = default_date - timedelta(days=6) if default_date else date.today() - timedelta(days=6)
        default_end = default_date if default_date else date.today()
        
        date_range = st.sidebar.date_input(
            "Select date range",
            value=(default_start, default_end),
            help="Select start and end dates for the report period"
        )
        
        # Handle both single date and date range
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        elif isinstance(date_range, tuple) and len(date_range) == 1:
            start_date = end_date = date_range[0]
        else:
            start_date = end_date = date_range
    
    # JavaScript to auto-switch to Custom Range when date picker is clicked
    st.sidebar.markdown("""
        <script>
        function setupDateRangeAutoSwitch() {
            const dateInputs = document.querySelectorAll('input[aria-label*="date"], input[type="date"]');
            const radioButtons = document.querySelectorAll('input[type="radio"]');
            
            dateInputs.forEach(input => {
                input.addEventListener('click', () => {
                    radioButtons.forEach(radio => {
                        if (radio.value === 'Custom Range' || radio.nextSibling?.textContent?.includes('Custom Range')) {
                            radio.checked = true;
                            radio.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    });
                });
            });
        }
        
        // Run on load and after Streamlit updates
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupDateRangeAutoSwitch);
        } else {
            setupDateRangeAutoSwitch();
        }
        
        // Re-run after Streamlit rerenders
        window.addEventListener('load', setupDateRangeAutoSwitch);
        setTimeout(setupDateRangeAutoSwitch, 100);
        setTimeout(setupDateRangeAutoSwitch, 500);
        </script>
    """, unsafe_allow_html=True)

    # Auto refresh
    auto_refresh = st.sidebar.checkbox("Auto refresh", value=True)
    # If auto refresh enabled, use st_autorefresh in main with given interval.

    # Manual refresh button
    manual_refresh = st.sidebar.button("Manual refresh")

    # Upload/Unload selector
    upload_type = st.sidebar.selectbox("Loading / Unloading", options=["All", "Loading", "Unloading"], index=0)

    # Truck Condition selector
    truck_condition = st.sidebar.selectbox(
        "Truck Condition", 
        options=["All", "OutSource Truck", "Company Truck", "Customer Truck"], 
        index=0
    )

    # Product groups (multi)
    product_options = ["Pipe", "Coil KMH1", "Coil KMH2", "Trading", "Roofing", "PU", "CZD", "BM", "Other"]
    product_selected = st.sidebar.multiselect("Product Group", options=product_options, default=product_options)

    # compact info
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"Auto-refresh: ⏱️ {refresh_interval_seconds}s")
    # st.sidebar.markdown("Data source: Google Sheets")

    return {
        "start_date": start_date,
        "end_date": end_date,
        "auto_refresh": auto_refresh,
        "manual_refresh": manual_refresh,
        "upload_type": None if upload_type == "All" else upload_type,
        "truck_condition": None if truck_condition == "All" else truck_condition,
        "product_selected": product_selected
    }
