"""
Agua Clara AI - punto de entrada de la interfaz.
Iniciar:  streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from interface.streamlit_app import main  # noqa: E402

main()
