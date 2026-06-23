from __future__ import annotations

import ttkbootstrap as ttk


def pack_tree_with_scrollbar(tree, **pack_options):
    parent = tree.master
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    options = {"side": "left", "fill": "both", "expand": True}
    options.update(pack_options)
    tree.pack(**options)
    scrollbar.pack(side="right", fill="y")
    return scrollbar


def grid_tree_with_scrollbar(tree, row: int = 0, column: int = 0, **grid_options):
    parent = tree.master
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    options = {"sticky": "nsew"}
    options.update(grid_options)
    tree.grid(row=row, column=column, **options)
    scrollbar.grid(row=row, column=column + 1, sticky="ns")
    return scrollbar


def grid_text_with_scrollbar(text, row: int = 0, column: int = 0, **grid_options):
    parent = text.master
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    options = {"sticky": "nsew"}
    options.update(grid_options)
    text.grid(row=row, column=column, **options)
    scrollbar.grid(row=row, column=column + 1, sticky="ns")
    return scrollbar


def pack_text_with_scrollbar(text, **pack_options):
    parent = text.master
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    options = {"side": "left", "fill": "both", "expand": True}
    options.update(pack_options)
    text.pack(**options)
    scrollbar.pack(side="right", fill="y")
    return scrollbar
