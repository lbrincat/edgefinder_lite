EdgeFinder Lite v2 (Render-ready)

Run locally:
1. python -m venv .venv && source .venv/bin/activate   (on Windows: .venv\Scripts\activate)
2. pip install -r requirements.txt
3. streamlit run app/Home.py

Deploy on Render:
- Start Command:
  streamlit run app/Home.py --server.port=$PORT --server.address=0.0.0.0

Notes:
- Home.py = main score dashboard
- pages/1_Macro_Dashboard.py = macro overview page
- shared_data.py = macro scraping & scoring (Investing.com)
- Macro data cached ~12h, includes timestamp
