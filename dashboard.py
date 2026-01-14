"""Interactive dashboard for 24/7 Clean Power Study."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Page config
st.set_page_config(page_title="24/7 Clean Power India", layout="wide")

# Data paths - works locally and on Streamlit Cloud
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "output")
if not os.path.exists(DATA_DIR):
    DATA_DIR = os.path.join(SCRIPT_DIR, "data")  # Fallback for deployed version


@st.cache_data
def load_data():
    """Load all results."""
    sites = pd.read_csv(f"{DATA_DIR}/selected_sites.csv")

    # Load npz and convert to dict of arrays (pickleable)
    with np.load(f"{DATA_DIR}/greedy_results.npz") as f:
        greedy = {k: f[k] for k in f.files}
    with np.load(f"{DATA_DIR}/optimized_results.npz") as f:
        optimized = {k: f[k] for k in f.files}

    return sites, greedy, optimized


sites, greedy, optimized = load_data()

# Header
st.title("🌞 24/7 Clean Power from Solar+Storage in India")
st.markdown("""
**Research Question:** Can 120 distributed solar+storage plants (6 GW solar + 16 GWh battery each)
provide reliable 24/7 clean electricity for a 100 GW target across India? (20% reserve margin)
""")

# Sidebar
st.sidebar.header("Settings")
scenario = st.sidebar.radio("Dispatch Strategy", ["Optimized", "Greedy"])

with st.sidebar.expander("ℹ️ What do these mean?"):
    st.markdown("""
**Greedy Dispatch:**
Each plant operates independently, hour-by-hour:
- If solar ≥ 1 GW: output 1 GW, charge battery with excess
- If solar < 1 GW: discharge battery to reach 1 GW
- No coordination between plants
- No knowledge of future weather

**Optimized Dispatch:**
Central coordinator with perfect foresight:
- Knows all 8,760 hours of solar generation in advance
- Coordinates battery charge/discharge across all 120 plants
- Minimizes total shortfall below 100 GW target
- Uses Gurobi linear programming optimizer

**Key difference:** Greedy reacts hour-by-hour; Optimized plans ahead to save battery for when it's needed most.
    """)

# Get data based on selection
if scenario == "Greedy":
    output = greedy['output']
    battery = greedy['battery']
else:  # Optimized
    output = optimized['output']
    battery = optimized['battery']

# Main metrics
st.header("📊 Key Results")

agg = output.sum(axis=1)
n_plants = output.shape[1]

# Aggregate metrics
st.subheader("Aggregate (120 plants → 100 GW target)")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Energy Delivered", f"{agg.sum()/1000:.0f} TWh", f"{agg.sum()/(100*8760)*100:.1f}% of target")
with col2:
    st.metric("Hours ≥100 GW", f"{(agg >= 100).sum()}", f"{(agg >= 100).sum()/8760*100:.1f}%")
with col3:
    st.metric("Hours ≥95 GW", f"{(agg >= 95).sum()}", f"{(agg >= 95).sum()/8760*100:.1f}%")
with col4:
    st.metric("Worst Hour", f"{agg.min():.1f} GW", "of 100 GW target")

# Per-plant metrics
st.subheader("Per-Plant (each plant → 1 GW target)")
plant_hours_100 = (output >= 1.0).sum(axis=0)  # Hours at full 1 GW
plant_hours_95 = (output >= 0.95).sum(axis=0)  # Hours at 0.95 GW
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Avg Hours ≥1 GW", f"{plant_hours_100.mean():.0f}", f"{plant_hours_100.mean()/8760*100:.1f}%")
with col2:
    st.metric("Avg Hours ≥0.95 GW", f"{plant_hours_95.mean():.0f}", f"{plant_hours_95.mean()/8760*100:.1f}%")
with col3:
    st.metric("Best Plant ≥1 GW", f"{plant_hours_100.max():.0f}", f"{plant_hours_100.max()/8760*100:.1f}%")
with col4:
    st.metric("Worst Plant ≥1 GW", f"{plant_hours_100.min():.0f}", f"{plant_hours_100.min()/8760*100:.1f}%")

# Site Map
st.header("🗺️ Site Locations")
fig_map = px.scatter_mapbox(
    sites, lat='center_lat', lon='center_lon',
    color='avg_cf_dc', size='total_land_km2',
    hover_data=['state', 'total_land_km2', 'avg_cf_dc'],
    color_continuous_scale='YlOrRd',
    mapbox_style='carto-positron',
    zoom=4, center={'lat': 22, 'lon': 80},
    title='120 Selected Solar Sites (20% Reserve Margin)'
)
fig_map.update_layout(height=500)
st.plotly_chart(fig_map, use_container_width=True)

# Time Series
st.header("📈 Aggregate Output Over Time")

# Week selector
week = st.slider("Select Week", 1, 52, 1)
start = (week - 1) * 168
end = start + 168

fig_ts = go.Figure()
fig_ts.add_trace(go.Scatter(x=list(range(start, end)), y=agg[start:end], name=scenario))

fig_ts.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="Target: 100 GW")
fig_ts.add_hline(y=90, line_dash="dot", line_color="orange", annotation_text="90% threshold")
fig_ts.update_layout(
    title=f"Week {week} (Hours {start}-{end})",
    xaxis_title="Hour", yaxis_title="Aggregate Output (GW)",
    yaxis_range=[0, 130], height=400
)
st.plotly_chart(fig_ts, use_container_width=True)

# Individual vs Aggregate Comparison
st.header("🔬 Individual vs Aggregate Availability")

# Use scenario-selected output
if scenario == "Greedy":
    output_selected = greedy['output']
    scenario_label = "Greedy"
elif scenario == "Optimized":
    output_selected = optimized['output']
    scenario_label = "Optimized"
else:
    output_selected = greedy['output']  # Default to greedy for comparison
    scenario_label = "Greedy"

output = output_selected
n_plants = output.shape[1]

# Calculate availability at different time resolutions
def calc_availability_dual(data, plant_threshold, agg_target):
    """Calculate availability for individual plants and aggregate."""
    # Hourly
    plant_hourly = (data >= plant_threshold).mean(axis=0) * 100  # Per plant
    agg_hourly = (data.sum(axis=1) >= agg_target).mean() * 100

    # Daily
    daily_plant = data.reshape(-1, 24, n_plants).mean(axis=1)  # (365, n_plants)
    plant_daily = (daily_plant >= plant_threshold).mean(axis=0) * 100
    agg_daily = (daily_plant.sum(axis=1) >= agg_target).mean() * 100

    # Weekly (52 weeks)
    weekly_plant = data[:8736].reshape(-1, 168, n_plants).mean(axis=1)  # (52, n_plants)
    plant_weekly = (weekly_plant >= plant_threshold).mean(axis=0) * 100
    agg_weekly = (weekly_plant.sum(axis=1) >= agg_target).mean() * 100

    # Annual
    annual_plant = data.mean(axis=0)
    plant_annual = (annual_plant >= plant_threshold).mean() * 100
    agg_annual = 100 if data.sum(axis=1).mean() >= agg_target else 0

    return {
        'Resolution': ['Hourly', 'Daily', 'Weekly', 'Annual'],
        'Individual (avg)': [plant_hourly.mean(), plant_daily.mean(), plant_weekly.mean(), plant_annual],
        'Aggregate': [agg_hourly, agg_daily, agg_weekly, agg_annual]
    }

# Show both thresholds
st.subheader("At 100% threshold (Plant ≥1 GW, Aggregate ≥100 GW)")
avail_100 = calc_availability_dual(output, plant_threshold=1.0, agg_target=100)
df_100 = pd.DataFrame(avail_100)
st.dataframe(df_100, use_container_width=True)

st.subheader("At 95% threshold (Plant ≥0.95 GW, Aggregate ≥95 GW)")
avail_95 = calc_availability_dual(output, plant_threshold=0.95, agg_target=95)
df_95 = pd.DataFrame(avail_95)
st.dataframe(df_95, use_container_width=True)

# Chart for 100% threshold
fig_compare = go.Figure()
fig_compare.add_trace(go.Bar(name='Individual Plant (avg)', x=df_100['Resolution'],
                              y=df_100['Individual (avg)'], marker_color='#2ecc71'))
fig_compare.add_trace(go.Bar(name='Aggregate (120→100 GW)', x=df_100['Resolution'],
                              y=df_100['Aggregate'], marker_color='#3498db'))
fig_compare.update_layout(
    title='Availability: Individual vs Aggregate (100% threshold: 1 GW per plant, 100 GW aggregate)',
    yaxis_title='Availability (%)',
    yaxis_range=[0, 100],
    barmode='group'
)
st.plotly_chart(fig_compare, use_container_width=True)

# Chart for 95% threshold
fig_compare_95 = go.Figure()
fig_compare_95.add_trace(go.Bar(name='Individual Plant (avg)', x=df_95['Resolution'],
                              y=df_95['Individual (avg)'], marker_color='#27ae60'))
fig_compare_95.add_trace(go.Bar(name='Aggregate (120→95 GW)', x=df_95['Resolution'],
                              y=df_95['Aggregate'], marker_color='#2980b9'))
fig_compare_95.update_layout(
    title='Availability: Individual vs Aggregate (95% threshold: 0.95 GW per plant, 95 GW aggregate)',
    yaxis_title='Availability (%)',
    yaxis_range=[0, 100],
    barmode='group'
)
st.plotly_chart(fig_compare_95, use_container_width=True)

# Calculate actual values for key insight
ind_100 = df_100['Individual (avg)'].iloc[0]  # Hourly individual at 100%
agg_100 = df_100['Aggregate'].iloc[0]  # Hourly aggregate at 100%
ind_95 = df_95['Individual (avg)'].iloc[0]  # Hourly individual at 95%
agg_95 = df_95['Aggregate'].iloc[0]  # Hourly aggregate at 95%

# Calculate greedy vs optimized for comparison
greedy_agg_100 = (greedy['output'].sum(axis=1) >= 100).mean() * 100
opt_agg_100 = (optimized['output'].sum(axis=1) >= 100).mean() * 100

st.markdown(f"""
**Key Insight ({scenario_label}):** With 120 plants (20% reserve margin) targeting 100 GW:
- **At 100% threshold**: Individual plants achieve {ind_100:.0f}% hourly availability, aggregate achieves {agg_100:.0f}%
- **At 95% threshold**: Individual plants achieve {ind_95:.0f}% hourly availability, aggregate achieves {agg_95:.0f}%
""")

st.markdown(f"""
**Critical Finding - Coordination matters more than diversification:**
- **Greedy dispatch** (each plant operates independently): {greedy_agg_100:.0f}% hours ≥100 GW
- **Optimized dispatch** (coordinated battery management): {opt_agg_100:.0f}% hours ≥100 GW

Geographic diversity alone (greedy) achieves ~{greedy_agg_100:.0f}% reliability. Adding coordination (optimized) achieves ~{opt_agg_100:.0f}%.
The **{opt_agg_100 - greedy_agg_100:.0f} percentage point improvement** comes from smart battery coordination, not more plants.
""")

# Correlation Proof Section
st.header(f"🔗 Understanding the Gap: Individual vs Aggregate ({scenario_label})")

st.markdown(f"""
Individual plants achieve {ind_100:.0f}% availability at 1 GW. What determines aggregate performance?
""")

output_corr = output_selected  # Use scenario-selected output
n_plants_corr = output_corr.shape[1]
plants_at_1gw = (output_corr >= 1.0).sum(axis=1)
plants_below_1gw = (output_corr < 1.0).sum(axis=1)
agg_corr = output_corr.sum(axis=1)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Max plants failing together", f"{plants_below_1gw.max()}", "out of 120")
with col2:
    bad_hours = (plants_below_1gw > 50).sum()
    st.metric("Hours with >50 failures", f"{bad_hours}", f"{bad_hours/8760*100:.1f}% of year")
with col3:
    avg_when_fail = output_corr[output_corr < 1.0].mean()
    st.metric("Avg output when failing", f"{avg_when_fail:.2f} GW", "not 0.88 GW!")

with st.expander("ℹ️ What do these metrics mean?"):
    st.markdown("""
    **Max plants failing together (111 out of 120):**
    - A plant "fails" when its output drops below 1 GW (target)
    - This shows the worst hour: 111 plants simultaneously had output < 1 GW
    - Only 9 plants maintained full output during that hour
    - This happens during extended cloudy periods when batteries are depleted

    **Hours with >50 failures (555 hours, 6.3%):**
    - Number of hours where more than 50 plants (out of 120) had output < 1 GW
    - These are the "bad hours" where aggregate output drops significantly
    - 6.3% of the year experiences major correlated failures

    **Avg output when failing (0.26 GW, not 0.88 GW!):**
    - When a plant's output drops below 1 GW, what's the average output?
    - If failures were "soft" (e.g., 0.9 GW), aggregate would still be high
    - But actual average is only 0.26 GW - batteries are depleted, minimal solar
    - This is why aggregate drops sharply when many plants fail
    """)

# Scatter plot: Plants at 1 GW vs Aggregate
fig_scatter = go.Figure()
fig_scatter.add_trace(go.Scatter(
    x=plants_at_1gw, y=agg_corr, mode='markers',
    marker=dict(size=3, opacity=0.3, color='blue'),
    name='Each hour'
))
fig_scatter.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="100 GW target")
fig_scatter.add_vline(x=100, line_dash="dash", line_color="orange", annotation_text="100 plants at 1 GW")
fig_scatter.update_layout(
    title='Plants at 1 GW vs Aggregate Output (Each dot = 1 hour)',
    xaxis_title='Number of Plants at ≥1 GW',
    yaxis_title='Aggregate Output (GW)',
    height=400
)
st.plotly_chart(fig_scatter, use_container_width=True)

with st.expander("ℹ️ How to read this scatter plot"):
    st.markdown("""
    **What this chart shows:**
    - Each blue dot represents ONE HOUR of the year (8,760 dots total)
    - X-axis: How many plants (out of 120) output ≥1 GW that hour
    - Y-axis: Total aggregate output (sum of all 120 plants) that hour

    **Key observations:**
    - **Red horizontal line (100 GW):** Our target aggregate output
    - **Orange vertical line (100 plants):** If 100 plants hit 1 GW each, we'd meet target

    **Example calculation:**
    - Say 80 plants output 1 GW each → contributes 80 GW
    - The other 40 plants are "failing" (output < 1 GW)
    - If those 40 failing plants output 0.26 GW each → contributes 40 × 0.26 = 10.4 GW
    - Total aggregate = 80 + 10.4 = **90.4 GW** (below 100 GW target!)

    **Why we don't hit 100 GW easily:**
    - We need ~100 plants at 1 GW to meet target
    - But during bad hours, only 80 or fewer plants hit 1 GW
    - The failing plants contribute very little (0.26 GW avg, not 0.88 GW)
    - So aggregate drops well below 100 GW
    """)

# Histogram of simultaneous failures
fig_hist = go.Figure()
fig_hist.add_trace(go.Histogram(x=plants_below_1gw, nbinsx=50, name='Hours'))
fig_hist.add_vline(x=plants_below_1gw.mean(), line_dash="dash", line_color="red",
                   annotation_text=f"Mean: {plants_below_1gw.mean():.0f}")
fig_hist.update_layout(
    title='Distribution of Simultaneous Plant Failures',
    xaxis_title='Number of Plants Below 1 GW (per hour)',
    yaxis_title='Number of Hours',
    height=350
)
st.plotly_chart(fig_hist, use_container_width=True)

with st.expander("ℹ️ How to read this histogram"):
    st.markdown("""
    **What this chart shows:**
    - X-axis: Number of plants failing (output < 1 GW) in a given hour
    - Y-axis: How many hours had that many failures
    - Red dashed line: Average number of failing plants per hour

    **If failures were RANDOM (uncorrelated):**
    - Each plant fails independently 12% of the time
    - Expected failures per hour = 120 × 0.12 = 14.4 plants
    - Distribution would be tight bell curve around 14

    **What we actually see (CORRELATED failures):**
    - Most hours have few failures (0-20 plants) - good weather
    - But there's a long right tail: hours with 50, 80, even 100+ failures
    - This right-skew proves failures are correlated by weather

    **Why correlation matters:**
    - Random: Always ~14 failures → 106 plants at 1 GW → 106+ GW aggregate
    - Correlated: Sometimes 80+ failures → only 40 plants at 1 GW → ~50 GW aggregate
    """)

# Heatmap for worst week
weekly_avg = agg_corr[:8736].reshape(-1, 168).mean(axis=1)
worst_week = int(weekly_avg.argmin())
start_h = worst_week * 168
end_h = start_h + 168

st.subheader(f"Worst Week Heatmap (Week {worst_week + 1})")
fig_heatmap = go.Figure(data=go.Heatmap(
    z=output_corr[start_h:end_h, :].T,
    x=list(range(168)),
    y=list(range(n_plants_corr)),
    colorscale='RdYlGn',
    zmin=0, zmax=1,
    colorbar=dict(title='Output (GW)')
))
fig_heatmap.update_layout(
    title=f'Plant Output During Worst Week - Green=1 GW, Red=0 GW',
    xaxis_title='Hour of Week (0-167)',
    yaxis_title='Plant ID (0-119)',
    height=500
)
st.plotly_chart(fig_heatmap, use_container_width=True)

with st.expander("ℹ️ How to read this heatmap"):
    st.markdown("""
    **What this chart shows:**
    - Each row = One plant (120 rows for 120 plants)
    - Each column = One hour of the week (168 columns = 7 days × 24 hours)
    - Color: Green = 1 GW output, Red = 0 GW output, Yellow = partial

    **Key pattern to look for: VERTICAL BANDS**
    - Vertical green band = All plants at 1 GW at the same hour (good hour)
    - Vertical red band = All plants failing at the same hour (bad hour)
    - If failures were random, you'd see scattered red dots, not vertical bands

    **What the worst week shows:**
    - This is Week {worst_week}, likely during monsoon season
    - Notice the vertical red bands: when it's cloudy/rainy, ALL plants suffer
    - Geographic diversity helps (some rows stay green) but doesn't eliminate correlation
    - The vertical pattern proves weather affects all plants simultaneously

    **Day/night cycle:**
    - You can see daily patterns (roughly 24-hour cycles)
    - Nighttime hours show more red (batteries depleting)
    - Daytime hours show more green (solar recharging)
    """.replace("{worst_week}", str(worst_week + 1)))

st.markdown(f"""
**Summary ({scenario_label}):**

**Weather correlation exists** - the vertical red bands show plants are affected by similar weather patterns.
When plants fail, they output only {avg_when_fail:.2f} GW on average (batteries depleted).

**But correlation is NOT the whole story:**
- If weather correlation were the main constraint, coordinated dispatch couldn't help much
- Yet optimized dispatch achieves **{opt_agg_100:.0f}%** vs greedy's **{greedy_agg_100:.0f}%** at 100 GW target
- This {opt_agg_100 - greedy_agg_100:.0f} percentage point gap shows that **battery coordination** matters enormously

**Conclusion:** 120 distributed solar+storage plants CAN provide ~{opt_agg_100:.0f}% hourly availability at 100 GW
through geographic diversity + coordinated battery management. The key is not just building more plants,
but operating them intelligently with forecasting and coordination.
""")

# Footer
st.markdown("---")
st.markdown("**Data:** NREL India Solar Resource Data (2015) | **Model:** 6 GW Solar + 16 GWh Battery per site")
