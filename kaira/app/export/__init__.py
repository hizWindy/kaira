"""Data export abstraction module."""

from __future__ import annotations

import csv
import io
from typing import Any, List

try:
    import openpyxl

    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False


class Export:
    """Export dataset to XLSX, PDF, or CSV format."""

    @staticmethod
    def to_csv(data: list[dict[str, Any]]) -> str:
        """Export data to CSV format."""
        if not data:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()

    @staticmethod
    def to_xlsx(data: list[dict[str, Any]], filename: str = "export.xlsx") -> str:
        """Export data to XLSX format."""
        if not _HAS_OPENPYXL:
            raise RuntimeError(
                "openpyxl is not installed. Install with 'pip install openpyxl'"
            )
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Export"
        if data:
            headers = list(data[0].keys())
            ws.append(headers)
            for row in data:
                ws.append([row.get(h, "") for h in headers])
        wb.save(filename)
        return filename

    @staticmethod
    def to_pdf(data: list[dict[str, Any]], filename: str = "export.pdf") -> str:
        """Export data to PDF format."""
        if not _HAS_REPORTLAB:
            raise RuntimeError(
                "reportlab is not installed. Install with 'pip install reportlab'"
            )
        doc = SimpleDocTemplate(filename, pagesize=letter)
        elements: list[Any] = []
        if data:
            headers = list(data[0].keys())
            elements.append(Paragraph(" | ".join(headers), doc.style))
            for row in data:
                elements.append(
                    Paragraph(" | ".join(str(v) for v in row.values()), doc.style)
                )
        doc.build(elements)
        return filename


__all__ = ["Export"]
