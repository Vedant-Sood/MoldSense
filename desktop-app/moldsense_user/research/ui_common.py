from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json, math, os, queue, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from matplotlib import dates as mdates
from .database import Database, FIELDS, LABELS
from .acquisition import Acquisition
from .statistics import (
    DEFAULT_SETTINGS,
    analyze_database,
    percent,
    distributions_database,
)
from .plots import (
    longitudinal_figure,
    time_figure,
    analysis_figure,
    gas_unit,
    distribution_figure,
)
from .exports import export_data, save_figure, session_report
from .migration import import_legacy
from . import VERSION

BG = "#f3f5f4"
INK = "#253630"
MUTED = "#64736e"
ACCENT = "#176b62"


def fmt(value, digits=2):
    return (
        "—"
        if value is None
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        else f"{value:,.{digits}f}"
    )
