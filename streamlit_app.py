"""Streamlit Cloud entry point.

This file's only job is to be discoverable at the repo root. The actual
application is in `market_predict/ui/app.py` — running this file via
`streamlit run streamlit_app.py` is equivalent.
"""
from market_predict.ui import app  # noqa: F401  (importing runs the Streamlit script)
