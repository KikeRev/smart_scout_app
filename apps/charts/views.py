# apps/charts/views.py
from urllib.parse import quote  # ⬅️  sustituye a urlquote
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from apps.charts.models import TempChart
from pathlib import Path
from django.http import HttpResponse
import pandas as pd


def serve_chart(request, pk, download: bool = False):
    """Stream PNG from /tmp; if *download* fuerza la descarga."""
    chart = get_object_or_404(TempChart, pk=pk)
    fname = Path(chart.filepath).name          # chart.png

    resp = FileResponse(open(chart.filepath, "rb"), content_type="image/png")
    if download:
        resp["Content-Disposition"] = (
            f'attachment; filename="{quote(fname)}"'
        )
    return resp


def file(request, pk):
    chart = get_object_or_404(TempChart, pk=pk)
    return FileResponse(chart.image.open("rb"), filename=chart.image.name)
