"""Milestone 4: run the web dashboard.

Two modes:
  python milestone4_dashboard.py            -> writes dashboard.html (a file you can open)
  python milestone4_dashboard.py --serve    -> runs a live local website at http://localhost:8000
"""

import sys
from pathlib import Path

from app.web import app, render_static

if __name__ == "__main__":
    if "--serve" in sys.argv:
        app.run(host="127.0.0.1", port=8000, debug=False)
    else:
        output = render_static(Path(__file__).parent / "dashboard.html")
        print(f"Dashboard written to {output}")
