# 24/7 Clean Power Dashboard

Interactive dashboard showing results from the India Solar+Storage 24/7 Clean Power Study.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

## Deploy to Streamlit Cloud

1. Push this `app/` folder to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Select `app/dashboard.py` as the main file
5. Deploy!

## Data

The `data/` folder contains pre-computed results:
- `selected_sites.csv` - 100 selected solar sites
- `greedy_results.npz` - Greedy dispatch simulation (8760 hours × 100 sites)
- `optimized_results.npz` - Gurobi-optimized dispatch
- `state_results.csv` - State-level aggregation
