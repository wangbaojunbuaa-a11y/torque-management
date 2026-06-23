from __future__ import annotations

from datetime import date

import ttkbootstrap as ttk


def normalize_date_text(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return date.today().isoformat()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return text


def create_date_picker(parent, variable, width: int = 14):
    variable.set(normalize_date_text(variable.get()))
    try:
        startdate = date.fromisoformat(variable.get())
    except ValueError:
        startdate = date.today()
    try:
        widget = ttk.DateEntry(
            parent,
            dateformat="%Y-%m-%d",
            startdate=startdate,
            width=width,
        )
        if hasattr(widget, "entry"):
            widget.entry.configure(textvariable=variable)
        return widget
    except Exception:
        return ttk.Entry(parent, textvariable=variable, width=width)


def date_value(variable) -> str:
    text = (variable.get() or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return text
