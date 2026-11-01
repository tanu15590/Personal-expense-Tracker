"""
Personal Expense Tracker
------------------------
A modern desktop expense tracker using CustomTkinter, SQLite, pandas, and Matplotlib.

Features:
- Add, edit, and delete expenses
- Dashboard summaries and embedded charts
- Category and overall monthly budgets
- CSV export and CSV import
- Search, filter, and sortable expense table
- Persistent local SQLite database

Run:
    pip install customtkinter pandas matplotlib
    python expense_tracker.py
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import matplotlib
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

APP_NAME = "PocketWise Expense Tracker"
DB_PATH = Path(__file__).with_name("expense_tracker.db")

BG = "#10131C"
PANEL = "#191E2B"
PANEL_ALT = "#202738"
TEXT = "#F3F5FA"
MUTED = "#9AA5B8"
GREEN = "#24D18F"
RED = "#FF647C"
BLUE = "#6D9EFF"
PURPLE = "#B18CFF"
ORANGE = "#FFB454"
BORDER = "#2C3447"

CATEGORIES = [
    "Food", "Travel", "Bills", "Shopping", "Health", "Education",
    "Entertainment", "Groceries", "Rent", "Other"
]
PAYMENT_METHODS = ["UPI", "Cash", "Debit Card", "Credit Card", "Net Banking", "Wallet", "Other"]


class ExpenseDatabase:
    """SQLite persistence layer. All user-entered values are parameterized."""

    def __init__(self, path: Path = DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def _initialize(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL,
                expense_date TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                UNIQUE(month, category)
            );
        """)
        self.conn.commit()

    def add_expense(self, amount, category, expense_date, payment_method, note):
        with self.conn:
            self.conn.execute(
                """INSERT INTO expenses(amount, category, expense_date, payment_method, note)
                   VALUES (?, ?, ?, ?, ?)""",
                (amount, category, expense_date, payment_method, note.strip())
            )

    def update_expense(self, expense_id, amount, category, expense_date, payment_method, note):
        with self.conn:
            self.conn.execute(
                """UPDATE expenses SET amount=?, category=?, expense_date=?,
                   payment_method=?, note=? WHERE id=?""",
                (amount, category, expense_date, payment_method, note.strip(), expense_id)
            )

    def delete_expense(self, expense_id):
        with self.conn:
            self.conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))

    def get_expenses(self):
        return pd.read_sql_query(
            "SELECT id, amount, category, expense_date, payment_method, note FROM expenses ORDER BY expense_date DESC, id DESC",
            self.conn
        )

    def get_budgets(self, month):
        return pd.read_sql_query(
            "SELECT category, amount FROM budgets WHERE month=? ORDER BY category",
            self.conn, params=(month,)
        )

    def save_budget(self, month, category, amount):
        with self.conn:
            self.conn.execute(
                """INSERT INTO budgets(month, category, amount) VALUES (?, ?, ?)
                   ON CONFLICT(month, category) DO UPDATE SET amount=excluded.amount""",
                (month, category, amount)
            )

    def close(self):
        self.conn.close()


class ExpenseTracker(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1240x820")
        self.minsize(1050, 700)
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.db = ExpenseDatabase()
        self.expenses = pd.DataFrame()
        self.selected_id = None
        self.sort_column = "expense_date"
        self.sort_reverse = True
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._configure_treeview()
        self._build_layout()
        self.refresh_all()

    def _configure_treeview(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Expense.Treeview", background=PANEL, foreground=TEXT,
            fieldbackground=PANEL, borderwidth=0, rowheight=34, font=("Segoe UI", 10)
        )
        style.configure(
            "Expense.Treeview.Heading", background=PANEL_ALT, foreground=TEXT,
            borderwidth=0, font=("Segoe UI Semibold", 10), padding=(10, 10)
        )
        style.map("Expense.Treeview", background=[("selected", "#34476A")], foreground=[("selected", TEXT)])
        style.map("Expense.Treeview.Heading", background=[("active", "#303A50")])

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#141925")
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(sidebar, text="◈  PocketWise", font=("Segoe UI", 23, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=22, pady=(28, 4))
        ctk.CTkLabel(sidebar, text="YOUR MONEY, IN FOCUS", font=("Segoe UI", 9, "bold"),
                     text_color=MUTED).pack(anchor="w", padx=24, pady=(0, 28))

        self.nav_buttons = {}
        for label, icon in [("Dashboard", "◫"), ("Expenses", "↗"), ("Budgets", "◉")]:
            button = ctk.CTkButton(
                sidebar, text=f"{icon}   {label}", anchor="w", height=44,
                fg_color="#273149" if label == "Dashboard" else "transparent",
                hover_color="#273149", text_color=TEXT, corner_radius=10,
                font=("Segoe UI", 13), command=lambda page=label: self.show_page(page)
            )
            button.pack(fill="x", padx=14, pady=4)
            self.nav_buttons[label] = button

        ctk.CTkFrame(sidebar, height=1, fg_color=BORDER).pack(fill="x", padx=18, pady=22)
        ctk.CTkLabel(sidebar, text="LOCAL DATABASE", text_color=MUTED,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=22)
        ctk.CTkLabel(sidebar, text="Your records stay on\nthis computer.",
                     text_color="#CBD2DF", justify="left", font=("Segoe UI", 11)).pack(anchor="w", padx=22, pady=8)
        ctk.CTkLabel(sidebar, text="PocketWise  •  v1.0", text_color="#657188",
                     font=("Segoe UI", 10)).pack(side="bottom", anchor="w", padx=22, pady=20)

        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=24, pady=22)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        self.header = ctk.CTkFrame(self.content, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        self.header.grid_columnconfigure(0, weight=1)
        self.page_title = ctk.CTkLabel(self.header, text="Dashboard",
                                       font=("Segoe UI", 27, "bold"), text_color=TEXT)
        self.page_title.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(self.header, text=date.today().strftime("%A, %d %B %Y"),
                     text_color=MUTED, font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ctk.CTkButton(self.header, text="+ Add Expense", width=145, height=40,
                      fg_color=GREEN, hover_color="#16B979", text_color="#081810",
                      font=("Segoe UI", 12, "bold"), command=self.open_add_dialog).grid(row=0, column=1, rowspan=2, padx=(12, 0))

        self.page_host = ctk.CTkFrame(self.content, fg_color="transparent")
        self.page_host.grid(row=1, column=0, sticky="nsew")
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)
        self.pages = {}
        self._build_dashboard()
        self._build_expenses_page()
        self._build_budgets_page()

    def _clear_frame(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def show_page(self, page):
        self.current_page = page
        for name, button in self.nav_buttons.items():
            button.configure(fg_color="#273149" if name == page else "transparent")
        for frame in self.pages.values():
            frame.grid_remove()
        self.pages[page].grid(row=0, column=0, sticky="nsew")
        self.page_title.configure(text=page)
        if page == "Dashboard":
            self.refresh_dashboard()
        elif page == "Expenses":
            self.refresh_expense_table()
        elif page == "Budgets":
            self.refresh_budgets()

    def _build_dashboard(self):
        page = ctk.CTkFrame(self.page_host, fg_color="transparent")
        page.grid_columnconfigure((0, 1, 2), weight=1, uniform="cards")
        page.grid_rowconfigure(1, weight=1)
        self.pages["Dashboard"] = page

        self.summary_labels = {}
        cards = [
            ("Today", "today", BLUE, "↗"),
            ("This Month", "month", GREEN, "◷"),
            ("All Time", "all", PURPLE, "◉"),
        ]
        for col, (title, key, accent, icon) in enumerate(cards):
            card = ctk.CTkFrame(page, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
            card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 8 if col < 2 else 0), pady=(0, 16))
            ctk.CTkLabel(card, text=f"{icon}  {title}", text_color=MUTED,
                         font=("Segoe UI", 12)).pack(anchor="w", padx=18, pady=(17, 7))
            label = ctk.CTkLabel(card, text="₹0.00", text_color=accent,
                                 font=("Segoe UI", 25, "bold"))
            label.pack(anchor="w", padx=18, pady=(0, 17))
            self.summary_labels[key] = label

        chart_card = ctk.CTkFrame(page, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
        chart_card.grid(row=1, column=0, columnspan=3, sticky="nsew")
        chart_card.grid_columnconfigure((0, 1), weight=1, uniform="charts")
        chart_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(chart_card, text="Spending Analytics", text_color=TEXT,
                     font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 0))
        self.category_fig = Figure(figsize=(4.6, 3.2), dpi=100, facecolor=PANEL)
        self.category_ax = self.category_fig.add_subplot(111)
        self.trend_fig = Figure(figsize=(4.6, 3.2), dpi=100, facecolor=PANEL)
        self.trend_ax = self.trend_fig.add_subplot(111)
        self.category_canvas = FigureCanvasTkAgg(self.category_fig, master=chart_card)
        self.category_canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=(10, 4), pady=10)
        self.trend_canvas = FigureCanvasTkAgg(self.trend_fig, master=chart_card)
        self.trend_canvas.get_tk_widget().grid(row=1, column=1, sticky="nsew", padx=(4, 10), pady=10)

    def _build_expenses_page(self):
        page = ctk.CTkFrame(self.page_host, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        self.pages["Expenses"] = page

        filters = ctk.CTkFrame(page, fg_color=PANEL, corner_radius=14)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        filters.grid_columnconfigure(0, weight=1)
        self.search_var = ctk.StringVar()
        search = ctk.CTkEntry(filters, textvariable=self.search_var, placeholder_text="Search notes or category...",
                              height=38, width=230)
        search.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        search.bind("<KeyRelease>", lambda _e: self.refresh_expense_table())
        self.filter_category = ctk.StringVar(value="All categories")
        ctk.CTkOptionMenu(filters, variable=self.filter_category,
                          values=["All categories"] + CATEGORIES, width=160,
                          command=lambda _v: self.refresh_expense_table()).grid(row=0, column=1, padx=6)
        ctk.CTkButton(filters, text="Import CSV", fg_color=PANEL_ALT, hover_color="#303A50",
                      command=self.import_csv).grid(row=0, column=2, padx=6)
        ctk.CTkButton(filters, text="Export CSV", fg_color=BLUE, hover_color="#4D7FE4",
                      command=self.export_csv).grid(row=0, column=3, padx=(6, 12))

        table_frame = ctk.CTkFrame(page, fg_color=PANEL, corner_radius=14)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        columns = ("id", "date", "category", "amount", "payment", "note")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", style="Expense.Treeview", selectmode="browse")
        headings = {"id": "ID", "date": "DATE", "category": "CATEGORY", "amount": "AMOUNT (₹)",
                    "payment": "PAYMENT", "note": "NOTE / DESCRIPTION"}
        widths = {"id": 55, "date": 105, "category": 125, "amount": 125, "payment": 130, "note": 300}
        for col in columns:
            self.tree.heading(col, text=headings[col], command=lambda c=col: self.sort_table(c))
            self.tree.column(col, width=widths[col], anchor="w" if col in ("category", "note", "payment") else "center",
                             stretch=col == "note")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=(10, 0))
        yscroll.grid(row=0, column=1, sticky="ns", pady=(10, 0), padx=(0, 10))
        xscroll.grid(row=1, column=0, sticky="ew", padx=10)
        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkButton(actions, text="Edit Selected", fg_color=BLUE, command=self.edit_selected).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Delete Selected", fg_color=RED, hover_color="#E64B66",
                      command=self.delete_selected).pack(side="left")
        self.table_count = ctk.CTkLabel(actions, text="", text_color=MUTED)
        self.table_count.pack(side="right")

    def _build_budgets_page(self):
        page = ctk.CTkFrame(self.page_host, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        self.pages["Budgets"] = page

        form = ctk.CTkFrame(page, fg_color=PANEL, corner_radius=14)
        form.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(form, text="Set a monthly budget", text_color=TEXT,
                     font=("Segoe UI", 15, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(15, 10))
        self.budget_month = ctk.StringVar(value=date.today().strftime("%Y-%m"))
        self.budget_category = ctk.StringVar(value="Overall")
        self.budget_amount = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self.budget_month, placeholder_text="YYYY-MM", width=130).grid(row=1, column=0, padx=(16, 8), pady=(0, 16))
        ctk.CTkOptionMenu(form, variable=self.budget_category, values=["Overall"] + CATEGORIES, width=160).grid(row=1, column=1, padx=8, pady=(0, 16))
        ctk.CTkEntry(form, textvariable=self.budget_amount, placeholder_text="Budget amount (₹)", width=170).grid(row=1, column=2, padx=8, pady=(0, 16))
        ctk.CTkButton(form, text="Save Budget", fg_color=GREEN, hover_color="#16B979",
                      text_color="#081810", command=self.save_budget).grid(row=1, column=3, padx=(8, 16), pady=(0, 16))

        self.budget_list = ctk.CTkScrollableFrame(page, fg_color=PANEL, corner_radius=14)
        self.budget_list.grid(row=1, column=0, sticky="nsew")
        self.budget_list.grid_columnconfigure(0, weight=1)

    def refresh_all(self):
        self.expenses = self.db.get_expenses()
        self.refresh_dashboard()
        self.refresh_expense_table()
        self.refresh_budgets()

    def refresh_dashboard(self):
        df = self.db.get_expenses()
        today_str = date.today().isoformat()
        month_str = date.today().strftime("%Y-%m")
        if df.empty:
            today_total = month_total = all_total = 0.0
        else:
            df["expense_date"] = pd.to_datetime(df["expense_date"], errors="coerce")
            today_total = df.loc[df["expense_date"].dt.date == date.today(), "amount"].sum()
            month_total = df.loc[df["expense_date"].dt.strftime("%Y-%m") == month_str, "amount"].sum()
            all_total = df["amount"].sum()
        self.summary_labels["today"].configure(text=f"₹{today_total:,.2f}")
        self.summary_labels["month"].configure(text=f"₹{month_total:,.2f}")
        self.summary_labels["all"].configure(text=f"₹{all_total:,.2f}")
        self._draw_charts(df)

    def _draw_charts(self, df):
        for ax in (self.category_ax, self.trend_ax):
            ax.clear()
            ax.set_facecolor(PANEL)
            ax.tick_params(colors=MUTED, labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(BORDER)
        if df.empty:
            self.category_ax.text(0.5, 0.5, "No expenses yet", color=MUTED, ha="center", va="center", transform=self.category_ax.transAxes)
            self.trend_ax.text(0.5, 0.5, "Add expenses to see trends", color=MUTED, ha="center", va="center", transform=self.trend_ax.transAxes)
        else:
            category_data = df.groupby("category")["amount"].sum().sort_values(ascending=False)
            if len(category_data):
                self.category_ax.pie(category_data.values, labels=category_data.index, autopct="%1.0f%%",
                                     startangle=90, textprops={"color": TEXT, "fontsize": 8},
                                     wedgeprops={"linewidth": 1, "edgecolor": PANEL})
                self.category_ax.set_title("By Category", color=TEXT, fontsize=11, pad=10)
            df = df.copy()
            df["expense_date"] = pd.to_datetime(df["expense_date"], errors="coerce")
            monthly = df.dropna(subset=["expense_date"]).set_index("expense_date").resample("MS")["amount"].sum()
            self.trend_ax.plot(monthly.index, monthly.values, color=GREEN, marker="o", linewidth=2.5, markersize=5)
            self.trend_ax.fill_between(monthly.index, monthly.values, color=GREEN, alpha=0.12)
            self.trend_ax.set_title("Monthly Spending", color=TEXT, fontsize=11, pad=10)
            self.trend_ax.grid(axis="y", color=BORDER, alpha=0.8)
            self.trend_ax.tick_params(axis="x", rotation=25, colors=MUTED, labelsize=8)
            self.trend_ax.tick_params(axis="y", colors=MUTED, labelsize=8)
            self.trend_ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("₹{x:,.0f}"))
        self.category_fig.tight_layout()
        self.trend_fig.tight_layout()
        self.category_canvas.draw_idle()
        self.trend_canvas.draw_idle()

    def refresh_expense_table(self):
        if not hasattr(self, "tree"):
            return
        df = self.db.get_expenses()
        if not df.empty:
            df["expense_date"] = pd.to_datetime(df["expense_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        if query and not df.empty:
            mask = df["note"].fillna("").str.lower().str.contains(query, regex=False) | df["category"].str.lower().str.contains(query, regex=False)
            df = df[mask]
        category = self.filter_category.get() if hasattr(self, "filter_category") else "All categories"
        if category != "All categories" and not df.empty:
            df = df[df["category"] == category]
        sort_map = {"id": "id", "date": "expense_date", "category": "category", "amount": "amount", "payment": "payment_method", "note": "note"}
        sort_col = sort_map.get(self.sort_column, "expense_date")
        if sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=not self.sort_reverse, kind="stable")
        for item in self.tree.get_children():
            self.tree.delete(item)
        for _, row in df.iterrows():
            self.tree.insert("", "end", iid=str(int(row["id"])), values=(
                int(row["id"]), row["expense_date"], row["category"], f'{row["amount"]:,.2f}',
                row["payment_method"], row["note"]
            ))
        self.table_count.configure(text=f"{len(df)} record(s)")

    def sort_table(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column, self.sort_reverse = column, False
        self.refresh_expense_table()

    def _expense_dialog(self, existing=None):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit Expense" if existing else "Add Expense")
        dialog.geometry("460x560")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Edit expense" if existing else "Add a new expense",
                     font=("Segoe UI", 22, "bold"), text_color=TEXT).pack(anchor="w", padx=26, pady=(24, 5))
        ctk.CTkLabel(dialog, text="Record the details below.", text_color=MUTED).pack(anchor="w", padx=26, pady=(0, 18))

        data = existing or {}
        amount_var = ctk.StringVar(value=str(data.get("amount", "")))
        category_var = ctk.StringVar(value=data.get("category", CATEGORIES[0]))
        date_var = ctk.StringVar(value=data.get("expense_date", date.today().isoformat()))
        payment_var = ctk.StringVar(value=data.get("payment_method", PAYMENT_METHODS[0]))
        note_var = ctk.StringVar(value=data.get("note", ""))

        def field(label, widget):
            ctk.CTkLabel(dialog, text=label, text_color="#D9DFEA", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=26, pady=(7, 4))
            widget.pack(fill="x", padx=26)

        field("Amount (₹)", ctk.CTkEntry(dialog, textvariable=amount_var, placeholder_text="e.g. 249.50", height=38))
        field("Category", ctk.CTkOptionMenu(dialog, variable=category_var, values=CATEGORIES, height=36))
        field("Date (YYYY-MM-DD)", ctk.CTkEntry(dialog, textvariable=date_var, placeholder_text="YYYY-MM-DD", height=38))
        field("Payment method", ctk.CTkOptionMenu(dialog, variable=payment_var, values=PAYMENT_METHODS, height=36))
        field("Note / description", ctk.CTkEntry(dialog, textvariable=note_var, placeholder_text="What was this expense for?", height=38))

        def save():
            try:
                amount = float(amount_var.get().strip())
                if amount <= 0 or amount != amount or amount == float("inf"):
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid amount", "Enter an amount greater than zero.", parent=dialog)
                return
            try:
                parsed_date = datetime.strptime(date_var.get().strip(), "%Y-%m-%d").date().isoformat()
            except ValueError:
                messagebox.showerror("Invalid date", "Use a valid date in YYYY-MM-DD format.", parent=dialog)
                return
            try:
                if existing:
                    self.db.update_expense(existing["id"], amount, category_var.get(), parsed_date, payment_var.get(), note_var.get())
                else:
                    self.db.add_expense(amount, category_var.get(), parsed_date, payment_var.get(), note_var.get())
            except sqlite3.Error as exc:
                messagebox.showerror("Database error", f"Could not save the expense.\n{exc}", parent=dialog)
                return
            dialog.destroy()
            self.refresh_all()

        ctk.CTkButton(dialog, text="Save Expense", height=42, fg_color=GREEN, hover_color="#16B979",
                      text_color="#081810", font=("Segoe UI", 12, "bold"), command=save).pack(fill="x", padx=26, pady=22)

    def open_add_dialog(self):
        self._expense_dialog()

    def edit_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select an expense", "Choose an expense row first.")
            return
        expense_id = int(selected[0])
        df = self.db.get_expenses()
        row = df[df["id"] == expense_id].iloc[0].to_dict()
        self._expense_dialog(row)

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select an expense", "Choose an expense row first.")
            return
        if messagebox.askyesno("Delete expense", "Delete the selected expense permanently?"):
            self.db.delete_expense(int(selected[0]))
            self.refresh_all()

    def export_csv(self):
        df = self.db.get_expenses()
        if df.empty:
            messagebox.showinfo("Nothing to export", "Add at least one expense before exporting.")
            return
        path = filedialog.asksaveasfilename(
            title="Export expenses", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")], initialfile="expenses.csv"
        )
        if not path:
            return
        try:
            df.to_csv(path, index=False, encoding="utf-8-sig")
            messagebox.showinfo("Export complete", f"Exported {len(df)} expenses.")
        except (OSError, PermissionError) as exc:
            messagebox.showerror("Export failed", str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(title="Import expenses CSV", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path)
            required = {"amount", "category", "expense_date", "payment_method"}
            missing = required - set(df.columns)
            if missing:
                raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
            imported = 0
            with self.db.conn:
                for _, row in df.iterrows():
                    amount = float(row["amount"])
                    if pd.isna(amount) or amount <= 0:
                        continue
                    parsed_date = pd.to_datetime(row["expense_date"], errors="coerce")
                    if pd.isna(parsed_date):
                        continue
                    category = str(row["category"]).strip() or "Other"
                    payment = str(row["payment_method"]).strip() or "Other"
                    note = "" if pd.isna(row.get("note", "")) else str(row.get("note", ""))
                    self.db.conn.execute(
                        "INSERT INTO expenses(amount, category, expense_date, payment_method, note) VALUES (?, ?, ?, ?, ?)",
                        (amount, category, parsed_date.strftime("%Y-%m-%d"), payment, note)
                    )
                    imported += 1
            self.refresh_all()
            messagebox.showinfo("Import complete", f"Imported {imported} valid expense(s). Invalid rows were skipped.")
        except (OSError, ValueError, pd.errors.ParserError, sqlite3.Error) as exc:
            messagebox.showerror("Import failed", str(exc))

    def save_budget(self):
        month = self.budget_month.get().strip()
        try:
            datetime.strptime(month, "%Y-%m")
            amount = float(self.budget_amount.get().strip())
            if amount <= 0 or amount != amount or amount == float("inf"):
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid budget", "Enter a month as YYYY-MM and a budget amount greater than zero.")
            return
        category = self.budget_category.get()
        try:
            self.db.save_budget(month, category, amount)
        except sqlite3.Error as exc:
            messagebox.showerror("Database error", str(exc))
            return
        self.budget_amount.set("")
        self.refresh_budgets()
        messagebox.showinfo("Budget saved", f"Budget for {category} in {month} saved.")

    def refresh_budgets(self):
        if not hasattr(self, "budget_list"):
            return
        for child in self.budget_list.winfo_children():
            child.destroy()
        month = self.budget_month.get().strip() if hasattr(self, "budget_month") else date.today().strftime("%Y-%m")
        if not month:
            month = date.today().strftime("%Y-%m")
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError:
            month = date.today().strftime("%Y-%m")
        budgets = self.db.get_budgets(month)
        df = self.db.get_expenses()
        if not df.empty:
            df["expense_date"] = pd.to_datetime(df["expense_date"], errors="coerce")
            df = df[df["expense_date"].dt.strftime("%Y-%m") == month]
        else:
            df = pd.DataFrame(columns=["category", "amount"])
        overall_spent = float(df["amount"].sum()) if not df.empty else 0.0
        overall = budgets[budgets["category"] == "Overall"] if not budgets.empty else pd.DataFrame()
        if not overall.empty:
            self._budget_row("Overall monthly budget", overall_spent, float(overall.iloc[0]["amount"]))
        else:
            ctk.CTkLabel(self.budget_list, text="No overall budget set for this month.",
                         text_color=MUTED).grid(row=0, column=0, sticky="w", padx=18, pady=12)
        for i, row in budgets[budgets["category"] != "Overall"].reset_index(drop=True).iterrows():
            spent = float(df.loc[df["category"] == row["category"], "amount"].sum()) if not df.empty else 0.0
            self._budget_row(str(row["category"]), spent, float(row["amount"]), row=i + 1)

    def _budget_row(self, title, spent, budget, row=0):
        ratio = spent / budget if budget else 0
        color = RED if ratio >= 1 else ORANGE if ratio >= 0.8 else GREEN
        card = ctk.CTkFrame(self.budget_list, fg_color=PANEL_ALT, corner_radius=12)
        card.grid(row=row, column=0, sticky="ew", padx=12, pady=7)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, text_color=TEXT, font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 3))
        ctk.CTkLabel(card, text=f"₹{spent:,.2f} spent of ₹{budget:,.2f}  •  {ratio:.0%}",
                     text_color=color, font=("Segoe UI", 11)).grid(row=0, column=1, sticky="e", padx=14, pady=(12, 3))
        bar = ctk.CTkProgressBar(card, progress_color=color, fg_color="#30394D", height=9)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(5, 13))
        bar.set(min(ratio, 1.0))

    def on_close(self):
        self.db.close()
        self.destroy()


if __name__ == "__main__":
    app = ExpenseTracker()
    app.mainloop()
