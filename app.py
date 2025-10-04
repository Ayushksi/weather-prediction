import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import folium
from streamlit_folium import st_folium
import plotly.express as px
from io import BytesIO

# === Caching for performance ===
@st.cache_data
def fetch_weather(lat, lon, start=1985, end=2023):
    try:
        parameters = "T2M,PRECTOTCORR,WS10M,ALLSKY_SFC_UV_INDEX,RH2M"
        url = (
            f"https://power.larc.nasa.gov/api/temporal/daily/point?"
            f"parameters={parameters}&community=RE&longitude={lon}&latitude={lat}"
            f"&start={start}0101&end={end}1231&format=JSON"
        )
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()["properties"]["parameter"]
        df = pd.DataFrame({
            "date": list(data["T2M"].keys()),
            "temperature": list(data["T2M"].values()),
            "precip": list(data["PRECTOTCORR"].values()),
            "windspeed": list(data["WS10M"].values()),
            "solar_uv": list(data["ALLSKY_SFC_UV_INDEX"].values()),
            "humidity": list(data["RH2M"].values())
        })
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        st.error(f"NASA API error: {e}")
        return pd.DataFrame()

# === Analysis ===
def analyze_conditions(df, month, day, hot, cold, wind, rain, humidity):
    df["month"], df["day"] = df["date"].dt.month, df["date"].dt.day
    subset = df[(df["month"] == month) & (df["day"] == day)]
    if subset.empty:
        return None, None

    results = {
        f"☀️ Very Hot (>{hot}°C)": (subset["temperature"] > hot).mean() * 100,
        f"❄️ Very Cold (<{cold}°C)": (subset["temperature"] < cold).mean() * 100,
        f"🌬️ Very Windy (>{wind} m/s)": (subset["windspeed"] > wind).mean() * 100,
        f"🌧️ Very Wet (>{rain} mm)": (subset["precip"] > rain).mean() * 100,
        "🥵 Very Uncomfortable": (
            ((subset["temperature"] > hot) | (subset["temperature"] < cold)) &
            (subset["humidity"] > humidity)
        ).mean() * 100,
        "Average Temperature (°C)": subset["temperature"].mean(),
        "Average Rainfall (mm)": subset["precip"].mean(),
        "Average Windspeed (m/s)": subset["windspeed"].mean(),
        "Average Humidity (%)": subset["humidity"].mean()
    }

    comfort = 100 - (
        abs(results["Average Temperature (°C)"] - 22) * 2 +
        results["Average Humidity (%)"] * 0.3 +
        results["Average Windspeed (m/s)"] * 1.5
    )
    results["Comfort Index"] = max(0, min(100, comfort))
    return results, subset

# === Map creator ===
def create_map(lat, lon, zoom=4):
    m = folium.Map(location=[lat, lon], zoom_start=zoom)
    folium.Marker(location=[lat, lon], draggable=True).add_to(m)
    return m

# === Export Helpers ===
def get_excel_download_link(df):
    output = BytesIO()
    df.to_excel(output, index=False, engine="openpyxl")
    return output.getvalue()

# === Streamlit Config ===
st.set_page_config(page_title="NASA Weather Predictor", layout="wide")
st.title("🌍 WILL IT RAIN ON MY PARADE?")
st.markdown("Check probabilities of weather conditions for any place and date.")

# === Session Defaults ===
if "lat" not in st.session_state:
    st.session_state.lat, st.session_state.lon = 40.7128, -74.0060
if "location_name" not in st.session_state:
    st.session_state.location_name = "NOT LOCATED"

# === Inputs (Single Column) ===
st.subheader("🌐 Location & Weather Settings")

# Search Location
search_query = st.text_input("Type a location (city, country, address)")
if st.button("Go", key="search_go"):
    if search_query:
        try:
            url = f"https://nominatim.openstreetmap.org/search?format=json&q={search_query}"
            response = requests.get(url, headers={"User-Agent": "streamlit-weather-app"})
            data = response.json()
            if data:
                st.session_state.lat = float(data[0]["lat"])
                st.session_state.lon = float(data[0]["lon"])
                st.session_state.location_name = data[0]['display_name']
                st.info(f"📍 {data[0]['display_name']}")
            else:
                st.warning("Location not found.")
        except:
            st.error("Error fetching location data.")

# Date Picker
date = st.date_input("Pick Date", datetime.today())

# Map Selection (Mobile-Friendly)
st.subheader("Select Location on Map")
map_obj = create_map(st.session_state.lat, st.session_state.lon)
map_data = st_folium(map_obj, width=350, height=250)
if map_data and map_data.get("last_clicked"):
    lat_clicked = map_data["last_clicked"]["lat"]
    lon_clicked = map_data["last_clicked"]["lng"]
    st.session_state.lat, st.session_state.lon = lat_clicked, lon_clicked
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat_clicked}&lon={lon_clicked}"
        response = requests.get(url, headers={"User-Agent": "streamlit-weather-app"})
        data = response.json()
        st.session_state.location_name = data.get("display_name", f"{lat_clicked:.2f}, {lon_clicked:.2f}")
    except:
        st.session_state.location_name = f"{lat_clicked:.2f}, {lon_clicked:.2f}"
    st.info(f"Map Selected: {st.session_state.location_name}")

# Weather Check Button
check_btn = st.button("🔍 Check Weather Probability", use_container_width=True)

# Display Selected Location
selected_location = st.session_state.get("location_name", "")
st.markdown(f"**Selected Location:** {selected_location}")

# Threshold Sliders (Compact)
st.subheader("⚙️ Weather Thresholds")

# Make sliders narrower: 1/6 center, 5/12 margins on both sides
left_margin, slider_col, right_margin = st.columns([5, 2, 5])

with slider_col:
    hot_thresh = st.slider("Hot > °C", 20, 50, 35, key="hot")
    cold_thresh = st.slider("Cold < °C", -20, 20, 5, key="cold")
    wind_thresh = st.slider("Wind > m/s", 0, 30, 10, key="wind")
    rain_thresh = st.slider("Rain > mm", 0, 50, 10, key="rain")
    humidity_thresh = st.slider("Humid > %", 0, 100, 80, key="humidity")

# === Tabs ===
tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "📈 Trends", "🗺️ Map", "📑 Report"])

# === Weather Analysis ===
if check_btn:
    lat, lon = st.session_state.lat, st.session_state.lon
    df = fetch_weather(lat, lon)
    if df.empty:
        st.warning("No data available.")
    else:
        month, day = date.month, date.day
        results, subset = analyze_conditions(df, month, day, hot_thresh, cold_thresh, wind_thresh, rain_thresh, humidity_thresh)

        with tab1:
            st.subheader("🌡️ Condition Probabilities Overview")
            location_name = st.session_state.location_name
        
            # Overall Rain Summary
            rain_prob_key = f"🌧️ Very Wet (>{rain_thresh} mm)"
            rain_prob = results.get(rain_prob_key, 0)
            if rain_prob > 50:
                st.markdown(f"### 🌧️ WILL RAIN ON {location_name.upper()}")
            else:
                st.markdown(f"### ☀️ WILL NOT RAIN ON {location_name.upper()}")
        
            # === 3 Columns Layout ===
            col1, col2, col3 = st.columns(3)
        
            with col1:
                st.markdown("### 🌡 Temperature")
                st.metric("Average Temp (°C)", f"{results['Average Temperature (°C)']:.2f}")
                st.progress(min(100, max(0, int((results['Average Temperature (°C)']+20)/70*100))))
                st.metric(f"☀️ Hot Days >{hot_thresh}°C", f"{results[f'☀️ Very Hot (>{hot_thresh}°C)']:.1f}%")
                st.metric(f"❄️ Cold Days <{cold_thresh}°C", f"{results[f'❄️ Very Cold (<{cold_thresh}°C)']:.1f}%")
        
            with col2:
                st.markdown("### 💧 Precipitation & Humidity")
                st.metric("Average Rainfall (mm)", f"{results['Average Rainfall (mm)']:.2f}")
                st.progress(min(100, max(0, int(results[f'🌧️ Very Wet (>{rain_thresh} mm)']))))
                st.metric("Average Humidity (%)", f"{results['Average Humidity (%)']:.1f}")
                st.metric(f"🥵 Very Uncomfortable", f"{results['🥵 Very Uncomfortable']:.1f}%")
        
            with col3:
                st.markdown("### 🌬 Wind & Comfort")
                st.metric("Average Windspeed (m/s)", f"{results['Average Windspeed (m/s)']:.2f}")
                st.progress(min(100, max(0, int(results['Average Windspeed (m/s)']*3.3))))  # scale for visualization
                st.metric("Comfort Index", f"{results['Comfort Index']:.1f}%")
                st.metric(f"🌬 Very Windy >{wind_thresh} m/s", f"{results[f'🌬️ Very Windy (>{wind_thresh} m/s)']:.1f}%")

        with tab2:
            st.subheader("📈 Interactive Weather Trends")
            fig = px.line(subset, x=subset["date"].dt.year, y="temperature", title="Temperature Trend", markers=True)
            fig.add_bar(x=subset["date"].dt.year, y=subset["precip"], name="Rainfall")
            st.plotly_chart(fig, use_container_width=True)
            st.subheader("🌞 Seasonal Heatmap")
            heat = df.groupby([df["date"].dt.month, df["date"].dt.day])["temperature"].mean().unstack()
            st.write(px.imshow(heat, title="Average Daily Temperature Heatmap"))
            
            # === Additional Graphs for Overview ===
            st.markdown("### 📊 Temperature & Rain Distribution")
            overview_fig = px.scatter(
                subset,
                x="temperature",
                y="precip",
                size="humidity",
                color="windspeed",
                labels={
                    "temperature": "Temp (°C)",
                    "precip": "Rainfall (mm)",
                    "humidity": "Humidity (%)",
                    "windspeed": "Windspeed (m/s)"
                },
                title="Temperature vs Rainfall (Bubble size = Humidity, Color = Windspeed)"
            )
            st.plotly_chart(overview_fig, use_container_width=True)

        with tab3:
            st.subheader("🗺️ Location")
            st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))

        with tab4:
            st.subheader("📑 Export Report")
            st.download_button("⬇️ Download CSV", subset.to_csv(index=False), "weather.csv")
            st.download_button("⬇️ Download Excel", get_excel_download_link(subset), "weather.xlsx")




