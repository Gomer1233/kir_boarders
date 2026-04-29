import os
import tkinter as tk
from tkinter import ttk

import pandas as pd


class KIRDashboard:
    def __init__(self, data_path):
        self.data_path = data_path

    def _load_data(self):
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Dashboard data file not found: {self.data_path}")
        return pd.read_excel(self.data_path)

    def run(self):
        data = self._load_data()

        try:
            root = tk.Tk()
        except tk.TclError:
            self._print_summary(data)
            return

        root.title("KIR Dashboard")
        root.geometry("920x620")

        summary = ttk.Frame(root, padding=12)
        summary.pack(fill=tk.X)

        ttk.Label(summary, text=f"File: {self.data_path}").pack(anchor=tk.W)
        ttk.Label(summary, text=f"Rows: {len(data):,}").pack(anchor=tk.W)
        ttk.Label(summary, text=f"Columns: {len(data.columns):,}").pack(anchor=tk.W)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self._add_columns_tab(notebook, data)
        self._add_preview_tab(notebook, data)

        root.mainloop()

    def _add_columns_tab(self, notebook, data):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Columns")

        columns = ("name", "dtype", "non_null")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, anchor=tk.W, width=220)

        for name in data.columns:
            tree.insert("", tk.END, values=(name, str(data[name].dtype), int(data[name].notna().sum())))

        tree.pack(fill=tk.BOTH, expand=True)

    def _add_preview_tab(self, notebook, data):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Preview")

        preview = data.head(100)
        columns = [str(column) for column in preview.columns]
        tree = ttk.Treeview(frame, columns=columns, show="headings")

        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=140, anchor=tk.W)

        for _, row in preview.iterrows():
            tree.insert("", tk.END, values=[self._format_value(row[column]) for column in preview.columns])

        x_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        y_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

    def _print_summary(self, data):
        print("[DASHBOARD] Tkinter display is unavailable.")
        print(f"[DASHBOARD] File: {self.data_path}")
        print(f"[DASHBOARD] Rows: {len(data):,}; columns: {len(data.columns):,}")

    @staticmethod
    def _format_value(value):
        if pd.isna(value):
            return ""
        text = str(value)
        return text if len(text) <= 120 else f"{text[:117]}..."
