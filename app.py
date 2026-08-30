from __future__ import annotations

import csv
import html
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

APP_NAME = "dwrean Αποθήκη"
APP_VERSION = "1.1.0"
APP_WEBSITE = "https://dwrean.net"
APP_CREATOR = "Κυριάκος Οικονομίδης"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_dir()
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "apothiki.db"


class InventoryDB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE COLLATE NOCASE,
                storage_position TEXT NOT NULL DEFAULT '',
                material_type TEXT NOT NULL DEFAULT '',
                warehouse TEXT NOT NULL DEFAULT '',
                photo_path TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._ensure_column("photo_path", "TEXT NOT NULL DEFAULT ''")
        self.conn.commit()

    def _ensure_column(self, name: str, definition: str):
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(materials)")}
        if name not in columns:
            self.conn.execute(f"ALTER TABLE materials ADD COLUMN {name} {definition}")

    def close(self):
        self.conn.close()

    def add(self, values: dict[str, str]):
        cur = self.conn.execute(
            """
            INSERT INTO materials(name, code, storage_position, material_type, warehouse, photo_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                values["name"], values["code"], values["storage_position"],
                values["material_type"], values["warehouse"], values.get("photo_path", ""),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def update(self, item_id: int, values: dict[str, str]):
        self.conn.execute(
            """
            UPDATE materials
            SET name=?, code=?, storage_position=?, material_type=?, warehouse=?, photo_path=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                values["name"], values["code"], values["storage_position"],
                values["material_type"], values["warehouse"], values.get("photo_path", ""), item_id,
            ),
        )
        self.conn.commit()

    def delete_many(self, ids: list[int]):
        if not ids:
            return
        self.conn.executemany("DELETE FROM materials WHERE id=?", [(i,) for i in ids])
        self.conn.commit()

    def query(self, filters: dict[str, str], search_text: str = ""):
        where = []
        params: list[str] = []
        field_map = {
            "name": "name",
            "code": "code",
            "storage_position": "storage_position",
            "material_type": "material_type",
            "warehouse": "warehouse",
        }
        for key, column in field_map.items():
            value = filters.get(key, "").strip()
            if value:
                where.append(f"{column} LIKE ?")
                params.append(f"%{value}%")
        search_text = search_text.strip()
        if search_text:
            like = f"%{search_text}%"
            where.append("(name LIKE ? OR code LIKE ? OR storage_position LIKE ? OR material_type LIKE ? OR warehouse LIKE ?)")
            params.extend([like] * 5)
        sql = "SELECT * FROM materials"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY name COLLATE NOCASE, code COLLATE NOCASE"
        return self.conn.execute(sql, params).fetchall()

    def get_many(self, ids: list[int]):
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        return self.conn.execute(
            f"SELECT * FROM materials WHERE id IN ({marks}) ORDER BY name COLLATE NOCASE", ids
        ).fetchall()

    def distinct(self, column: str):
        allowed = {"material_type", "warehouse", "storage_position"}
        if column not in allowed:
            return []
        rows = self.conn.execute(
            f"SELECT DISTINCT {column} AS v FROM materials WHERE TRIM({column}) <> '' ORDER BY {column} COLLATE NOCASE"
        ).fetchall()
        return [r["v"] for r in rows]

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]


class InventoryApp(tk.Tk):
    COLUMNS = ("name", "code", "storage_position", "material_type", "warehouse", "photo")

    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1240x800")
        self.minsize(1050, 700)
        self.db = InventoryDB(DB_PATH)
        self.selected_id: int | None = None
        self.photo_path = ""
        self.preview_image = None
        self.full_photo_image = None
        self._setup_style()
        self._build_menu()
        self._build_ui()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 20))
        style.configure("Muted.TLabel", font=("Segoe UI", 9))
        style.configure("Link.TLabel", font=("Segoe UI", 10, "underline"))

    def _build_menu(self):
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Δημιουργία Backup...", command=self.create_backup)
        file_menu.add_command(label="Επαναφορά από Backup...", command=self.restore_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Έξοδος", command=self.on_close)
        menu_bar.add_cascade(label="Αρχείο", menu=file_menu)
        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="Οδηγίες χρήσης", command=self.show_help)
        help_menu.add_separator()
        help_menu.add_command(label="Πληροφορίες εφαρμογής", command=self.show_about)
        menu_bar.add_cascade(label="Βοήθεια", menu=help_menu)
        self.config(menu=menu_bar)

    def _build_ui(self):
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text=APP_NAME, style="Header.TLabel").pack(side="left")
        self.stats_label = ttk.Label(header, text="", style="Muted.TLabel")
        self.stats_label.pack(side="right", padx=4)
        editor = ttk.LabelFrame(outer, text=" Στοιχεία υλικού ", padding=10)
        editor.pack(fill="x", pady=(0, 10))
        form = ttk.Frame(editor)
        form.pack(side="left", fill="both", expand=True)
        photo_box = ttk.Frame(editor, width=205)
        photo_box.pack(side="right", fill="y", padx=(14, 0))
        photo_box.pack_propagate(False)
        self.vars = {
            "name": tk.StringVar(),
            "code": tk.StringVar(),
            "storage_position": tk.StringVar(),
            "material_type": tk.StringVar(),
            "warehouse": tk.StringVar(),
        }
        labels = [
            ("Ονομασία υλικού", "name"),
            ("Κωδικός αριθμός", "code"),
            ("Θέση αποθήκευσης", "storage_position"),
            ("Είδος υλικού", "material_type"),
            ("Αποθήκη", "warehouse"),
        ]
        for col, (label, key) in enumerate(labels):
            ttk.Label(form, text=label).grid(row=0, column=col, sticky="w", padx=4, pady=(0, 4))
            if key in {"material_type", "warehouse", "storage_position"}:
                widget = ttk.Combobox(form, textvariable=self.vars[key])
                setattr(self, f"combo_{key}", widget)
            else:
                widget = ttk.Entry(form, textvariable=self.vars[key])
            widget.grid(row=1, column=col, sticky="ew", padx=4)
            form.columnconfigure(col, weight=1)
        actions = ttk.Frame(form)
        actions.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(10, 0), padx=4)
        ttk.Button(actions, text="Νέα καταχώριση", command=self.clear_form).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Αποθήκευση", command=self.save_item).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Διαγραφή", command=self.delete_selected).pack(side="left")
        ttk.Label(photo_box, text="Φωτογραφία υλικού").pack(anchor="w", pady=(0, 4))
        preview_frame = tk.Frame(photo_box, width=185, height=185, bd=1, relief="solid")
        preview_frame.pack(pady=(0, 6))
        preview_frame.pack_propagate(False)
        self.photo_label = tk.Label(preview_frame, text="Χωρίς φωτογραφία", anchor="center", justify="center", bg="white")
        self.photo_label.pack(fill="both", expand=True)
        self.photo_label.bind("<Button-1>", self.open_full_photo)
        ttk.Button(photo_box, text="Επιλογή φωτογραφίας", command=self.choose_photo).pack(fill="x", pady=(0, 4))
        ttk.Button(photo_box, text="Αφαίρεση φωτογραφίας", command=self.remove_photo).pack(fill="x")
        filters = ttk.LabelFrame(outer, text=" Αναζήτηση και φίλτρα ", padding=10)
        filters.pack(fill="x", pady=(0, 10))
        self.search_var = tk.StringVar()
        ttk.Label(filters, text="Γενική αναζήτηση").grid(row=0, column=0, sticky="w", padx=4)
        search_entry = ttk.Entry(filters, textvariable=self.search_var)
        search_entry.grid(row=1, column=0, sticky="ew", padx=4)
        search_entry.bind("<KeyRelease>", lambda _e: self.refresh())
        self.filter_vars = {
            "material_type": tk.StringVar(),
            "warehouse": tk.StringVar(),
            "storage_position": tk.StringVar(),
        }
        filter_defs = [("Είδος υλικού", "material_type"), ("Αποθήκη", "warehouse"), ("Θέση", "storage_position")]
        self.filter_combos = {}
        for i, (label, key) in enumerate(filter_defs, start=1):
            ttk.Label(filters, text=label).grid(row=0, column=i, sticky="w", padx=4)
            combo = ttk.Combobox(filters, textvariable=self.filter_vars[key], state="readonly")
            combo.grid(row=1, column=i, sticky="ew", padx=4)
            combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
            self.filter_combos[key] = combo
        ttk.Button(filters, text="Καθαρισμός φίλτρων", command=self.clear_filters).grid(row=1, column=4, sticky="ew", padx=4)
        for i in range(5):
            filters.columnconfigure(i, weight=1 if i < 4 else 0)
        table_frame = ttk.Frame(outer)
        table_frame.pack(fill="both", expand=True)
        headings = {
            "name": "Ονομασία υλικού",
            "code": "Κωδικός",
            "storage_position": "Θέση αποθήκευσης",
            "material_type": "Είδος υλικού",
            "warehouse": "Αποθήκη",
            "photo": "Φωτογραφία",
        }
        self.tree = ttk.Treeview(table_frame, columns=self.COLUMNS, show="headings", selectmode="extended")
        for col in self.COLUMNS:
            self.tree.heading(col, text=headings[col], command=lambda c=col: self.sort_tree(c, False))
            width = 245 if col == "name" else (95 if col == "photo" else 165)
            self.tree.column(col, width=width, minwidth=80, anchor="w")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.on_tree_select)
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Εκτύπωση φίλτρου", command=self.print_filtered).pack(side="left", padx=(0, 6))
        ttk.Button(bottom, text="Εκτύπωση επιλεγμένων", command=self.print_selected).pack(side="left", padx=(0, 6))
        ttk.Button(bottom, text="Εξαγωγή CSV", command=self.export_csv).pack(side="left")
        ttk.Label(bottom, text=f"Βάση: {DB_PATH}", style="Muted.TLabel").pack(side="right")

    def form_values(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        values["photo_path"] = self.photo_path
        return values

    def validate_form(self, values: dict[str, str]):
        if not values["name"]:
            messagebox.showwarning(APP_NAME, "Συμπλήρωσε την ονομασία του υλικού.")
            return False
        if not values["code"]:
            messagebox.showwarning(APP_NAME, "Συμπλήρωσε τον κωδικό αριθμό.")
            return False
        return True

    def save_item(self):
        values = self.form_values()
        if not self.validate_form(values):
            return
        try:
            if self.selected_id is None:
                self.db.add(values)
            else:
                self.db.update(self.selected_id, values)
        except sqlite3.IntegrityError:
            messagebox.showerror(APP_NAME, "Υπάρχει ήδη υλικό με αυτόν τον κωδικό αριθμό.")
            return
        self.clear_form()
        self.refresh()

    def clear_form(self):
        self.selected_id = None
        self.photo_path = ""
        for var in self.vars.values():
            var.set("")
        self.tree.selection_remove(self.tree.selection())
        self.show_photo_preview("")

    def selected_ids(self):
        return [int(item) for item in self.tree.selection()]

    def delete_selected(self):
        ids = self.selected_ids()
        if not ids and self.selected_id is not None:
            ids = [self.selected_id]
        if not ids:
            messagebox.showinfo(APP_NAME, "Επίλεξε πρώτα μία ή περισσότερες καταχωρίσεις.")
            return
        if not messagebox.askyesno(APP_NAME, f"Να διαγραφούν οι επιλεγμένες καταχωρίσεις ({len(ids)});"):
            return
        rows = self.db.get_many(ids)
        self.db.delete_many(ids)
        for row in rows:
            self._delete_photo_if_unused(row["photo_path"])
        self.clear_form()
        self.refresh()

    def _delete_photo_if_unused(self, relative_path: str):
        if not relative_path:
            return
        count = self.db.conn.execute("SELECT COUNT(*) FROM materials WHERE photo_path=?", (relative_path,)).fetchone()[0]
        if count == 0:
            path = BASE_DIR / relative_path
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

    def choose_photo(self):
        source = filedialog.askopenfilename(
            title="Επιλογή φωτογραφίας υλικού",
            filetypes=[("Εικόνες", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Όλα τα αρχεία", "*.*")],
        )
        if not source:
            return
        source_path = Path(source)
        if source_path.suffix.lower() not in IMAGE_EXTENSIONS:
            messagebox.showerror(APP_NAME, "Η μορφή της εικόνας δεν υποστηρίζεται.")
            return
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        destination = IMAGES_DIR / f"{uuid.uuid4().hex}{source_path.suffix.lower()}"
        try:
            shutil.copy2(source_path, destination)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Δεν ήταν δυνατή η αντιγραφή της φωτογραφίας.\n\n{exc}")
            return
        old_photo = self.photo_path
        self.photo_path = str(destination.relative_to(BASE_DIR))
        self.show_photo_preview(self.photo_path)
        if old_photo and old_photo != self.photo_path and self.selected_id is None:
            self._delete_photo_if_unused(old_photo)

    def remove_photo(self):
        old_photo = self.photo_path
        self.photo_path = ""
        self.show_photo_preview("")
        if old_photo and self.selected_id is None:
            self._delete_photo_if_unused(old_photo)

    def show_photo_preview(self, relative_path: str):
        self.preview_image = None
        self.photo_label.configure(image="", text="Χωρίς φωτογραφία", cursor="")
        if not relative_path:
            return
        path = BASE_DIR / relative_path
        if not path.exists():
            self.photo_label.configure(text="Η φωτογραφία\nδεν βρέθηκε")
            return
        try:
            with Image.open(path) as source:
                image = source.copy()
            image.thumbnail((177, 177), Image.Resampling.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(image)
            self.photo_label.configure(image=self.preview_image, text="", cursor="hand2")
        except Exception:
            self.photo_label.configure(text="Αδυναμία προβολής\nφωτογραφίας")

    def open_full_photo(self, _event=None):
        if not self.photo_path:
            return
        path = BASE_DIR / self.photo_path
        if not path.exists():
            messagebox.showwarning(APP_NAME, "Η φωτογραφία δεν βρέθηκε.")
            return
        try:
            with Image.open(path) as source:
                image = source.copy()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Δεν ήταν δυνατή η προβολή της φωτογραφίας.\n\n{exc}")
            return
        window = tk.Toplevel(self)
        window.title("Φωτογραφία υλικού")
        window.configure(bg="#202020")
        window.transient(self)
        max_w = max(640, int(self.winfo_screenwidth() * 0.88))
        max_h = max(480, int(self.winfo_screenheight() * 0.82))
        image.thumbnail((max_w - 40, max_h - 70), Image.Resampling.LANCZOS)
        full_image = ImageTk.PhotoImage(image)
        image_label = tk.Label(window, image=full_image, bg="#202020")
        image_label.image = full_image
        image_label.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Button(window, text="Κλείσιμο", command=window.destroy).pack(pady=(0, 10))
        window.update_idletasks()
        width = min(max_w, image.width + 30)
        height = min(max_h, image.height + 70)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.bind("<Escape>", lambda _e: window.destroy())

    def current_filters(self):
        return {
            "name": "",
            "code": "",
            "storage_position": self.filter_vars["storage_position"].get(),
            "material_type": self.filter_vars["material_type"].get(),
            "warehouse": self.filter_vars["warehouse"].get(),
        }

    def refresh(self):
        rows = self.db.query(self.current_filters(), self.search_var.get())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert("", "end", iid=str(row["id"]), values=(
                row["name"], row["code"], row["storage_position"], row["material_type"],
                row["warehouse"], "Ναι" if row["photo_path"] else "Όχι",
            ))
        self._refresh_combo_values()
        self.stats_label.config(text=f"Εμφάνιση: {len(rows)}  |  Σύνολο: {self.db.count()}")

    def _refresh_combo_values(self):
        for key in ("material_type", "warehouse", "storage_position"):
            values = self.db.distinct(key)
            combo = getattr(self, f"combo_{key}")
            combo["values"] = values
            current_filter = self.filter_vars[key].get()
            self.filter_combos[key]["values"] = [""] + values
            if current_filter and current_filter not in values:
                self.filter_vars[key].set("")

    def clear_filters(self):
        self.search_var.set("")
        for var in self.filter_vars.values():
            var.set("")
        self.refresh()

    def on_tree_select(self, _event=None):
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        rows = self.db.get_many(ids)
        if not rows:
            return
        row = rows[0]
        self.selected_id = row["id"]
        for key in self.vars:
            self.vars[key].set(row[key])
        self.photo_path = row["photo_path"] or ""
        self.show_photo_preview(self.photo_path)

    def sort_tree(self, column: str, reverse: bool):
        data = [(self.tree.set(item, column).casefold(), item) for item in self.tree.get_children("")]
        data.sort(reverse=reverse)
        for index, (_value, item) in enumerate(data):
            self.tree.move(item, "", index)
        self.tree.heading(column, command=lambda: self.sort_tree(column, not reverse))

    def filtered_rows(self):
        return self.db.query(self.current_filters(), self.search_var.get())

    def print_filtered(self):
        self.open_print_report(self.filtered_rows(), "Κατάσταση υλικών - ενεργά φίλτρα")

    def print_selected(self):
        ids = self.selected_ids()
        if not ids:
            messagebox.showinfo(APP_NAME, "Επίλεξε τις γραμμές που θέλεις να εκτυπώσεις.")
            return
        self.open_print_report(self.db.get_many(ids), "Κατάσταση επιλεγμένων υλικών")

    def open_print_report(self, rows, title: str):
        if not rows:
            messagebox.showinfo(APP_NAME, "Δεν υπάρχουν εγγραφές για εκτύπωση.")
            return
        generated = datetime.now().strftime("%d/%m/%Y %H:%M")
        trs = []
        for row in rows:
            photo = "Ναι" if row["photo_path"] else "Όχι"
            values = [row["name"], row["code"], row["storage_position"], row["material_type"], row["warehouse"], photo]
            cells = "".join(f"<td>{html.escape(str(value or ''))}</td>" for value in values)
            trs.append(f"<tr>{cells}</tr>")
        report = f"""<!doctype html>
<html lang="el"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;color:#111}}h1{{font-size:22px;margin-bottom:4px}} .meta{{color:#555;margin-bottom:18px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #bbb;padding:7px;text-align:left;vertical-align:top}}th{{background:#eee}} .toolbar{{margin-bottom:16px}}button{{font-size:14px;padding:8px 14px}}@media print{{.toolbar{{display:none}} body{{margin:0}}}}</style></head>
<body><div class="toolbar"><button onclick="window.print()">Εκτύπωση</button></div><h1>{html.escape(APP_NAME)} — {html.escape(title)}</h1><div class="meta">Ημερομηνία: {generated} &nbsp;|&nbsp; Εγγραφές: {len(rows)}</div><table><thead><tr><th>Ονομασία υλικού</th><th>Κωδικός</th><th>Θέση αποθήκευσης</th><th>Είδος υλικού</th><th>Αποθήκη</th><th>Φωτογραφία</th></tr></thead><tbody>{''.join(trs)}</tbody></table></body></html>"""
        fd, path = tempfile.mkstemp(prefix="dwrean_apothiki_", suffix=".html")
        os.close(fd)
        Path(path).write_text(report, encoding="utf-8")
        webbrowser.open(Path(path).as_uri())

    def export_csv(self):
        rows = self.filtered_rows()
        if not rows:
            messagebox.showinfo(APP_NAME, "Δεν υπάρχουν εγγραφές για εξαγωγή.")
            return
        path = filedialog.asksaveasfilename(title="Εξαγωγή CSV", defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile=f"dwrean-apothiki-{datetime.now().strftime('%Y%m%d')}.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Ονομασία υλικού", "Κωδικός", "Θέση αποθήκευσης", "Είδος υλικού", "Αποθήκη", "Φωτογραφία"])
            for row in rows:
                writer.writerow([row["name"], row["code"], row["storage_position"], row["material_type"], row["warehouse"], row["photo_path"]])
        messagebox.showinfo(APP_NAME, "Η εξαγωγή ολοκληρώθηκε.")

    def create_backup(self):
        default_name = f"dwrean-apothiki-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.zip"
        output = filedialog.asksaveasfilename(title="Δημιουργία Backup", defaultextension=".zip", filetypes=[("Αρχείο ZIP", "*.zip")], initialfile=default_name)
        if not output:
            return
        try:
            self.db.conn.commit()
            with tempfile.TemporaryDirectory(prefix="dwrean_apothiki_backup_") as temp_dir:
                temp_root = Path(temp_dir)
                temp_data = temp_root / "data"
                temp_images = temp_data / "images"
                temp_images.mkdir(parents=True, exist_ok=True)
                backup_db_path = temp_data / "apothiki.db"
                backup_conn = sqlite3.connect(backup_db_path)
                try:
                    self.db.conn.backup(backup_conn)
                finally:
                    backup_conn.close()
                if IMAGES_DIR.exists():
                    for image_path in IMAGES_DIR.iterdir():
                        if image_path.is_file():
                            shutil.copy2(image_path, temp_images / image_path.name)
                info = f"{APP_NAME} {APP_VERSION}\nΗμερομηνία backup: {datetime.now().strftime('%d/%m/%Y %H:%M')}\nΕγγραφές: {self.db.count()}\n"
                (temp_root / "backup_info.txt").write_text(info, encoding="utf-8")
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for item in temp_root.rglob("*"):
                        if item.is_file():
                            archive.write(item, item.relative_to(temp_root))
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Το Backup δεν ολοκληρώθηκε.\n\n{exc}")
            return
        messagebox.showinfo(APP_NAME, f"Το Backup δημιουργήθηκε επιτυχώς.\n\n{output}")

    def restore_backup(self):
        source = filedialog.askopenfilename(title="Επαναφορά από Backup", filetypes=[("Αρχείο ZIP", "*.zip"), ("Όλα τα αρχεία", "*.*")])
        if not source:
            return
        if not messagebox.askyesno(APP_NAME, "Η επαναφορά θα αντικαταστήσει την τρέχουσα βάση και τις φωτογραφίες.\n\nΣυνιστάται να δημιουργήσεις πρώτα νέο Backup.\n\nΝα συνεχίσω;"):
            return
        emergency_dir = Path(tempfile.mkdtemp(prefix="dwrean_apothiki_before_restore_"))
        emergency_data = emergency_dir / "data"
        try:
            with zipfile.ZipFile(source, "r") as archive:
                names = set(archive.namelist())
                if "data/apothiki.db" not in names:
                    raise ValueError("Το αρχείο δεν είναι έγκυρο Backup της εφαρμογής.")
                extracted_root = Path(tempfile.mkdtemp(prefix="dwrean_apothiki_restore_"))
                try:
                    archive.extractall(extracted_root)
                    restored_db = extracted_root / "data" / "apothiki.db"
                    test_conn = sqlite3.connect(restored_db)
                    try:
                        table = test_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='materials'").fetchone()
                        if not table:
                            raise ValueError("Η βάση του Backup δεν περιέχει τα απαραίτητα δεδομένα.")
                    finally:
                        test_conn.close()
                    self.db.close()
                    if DATA_DIR.exists():
                        shutil.copytree(DATA_DIR, emergency_data, dirs_exist_ok=True)
                    DATA_DIR.mkdir(parents=True, exist_ok=True)
                    if DB_PATH.exists():
                        DB_PATH.unlink()
                    if IMAGES_DIR.exists():
                        shutil.rmtree(IMAGES_DIR)
                    shutil.copy2(restored_db, DB_PATH)
                    restored_images = extracted_root / "data" / "images"
                    if restored_images.exists():
                        shutil.copytree(restored_images, IMAGES_DIR, dirs_exist_ok=True)
                    else:
                        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                finally:
                    shutil.rmtree(extracted_root, ignore_errors=True)
            self.db = InventoryDB(DB_PATH)
            self.clear_form()
            self.clear_filters()
        except Exception as exc:
            try:
                try:
                    self.db.close()
                except Exception:
                    pass
                if emergency_data.exists():
                    if DATA_DIR.exists():
                        shutil.rmtree(DATA_DIR, ignore_errors=True)
                    shutil.copytree(emergency_data, DATA_DIR, dirs_exist_ok=True)
                self.db = InventoryDB(DB_PATH)
                self.refresh()
            except Exception:
                pass
            messagebox.showerror(APP_NAME, f"Η επαναφορά δεν ολοκληρώθηκε.\n\n{exc}")
            shutil.rmtree(emergency_dir, ignore_errors=True)
            return
        shutil.rmtree(emergency_dir, ignore_errors=True)
        messagebox.showinfo(APP_NAME, "Η επαναφορά του Backup ολοκληρώθηκε επιτυχώς.")

    def show_help(self):
        window = tk.Toplevel(self)
        window.title(f"Βοήθεια - {APP_NAME}")
        window.geometry("650x540")
        window.minsize(560, 460)
        window.transient(self)
        outer = ttk.Frame(window, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Οδηγίες χρήσης", style="Header.TLabel").pack(anchor="w", pady=(0, 12))
        text = tk.Text(outer, wrap="word", font=("Segoe UI", 10), relief="solid", borderwidth=1, padx=12, pady=12)
        text.pack(fill="both", expand=True)
        help_text = (
            "Καταχώριση υλικού\nΣυμπλήρωσε την ονομασία και τον κωδικό. Προαιρετικά πρόσθεσε θέση αποθήκευσης, είδος υλικού, αποθήκη και φωτογραφία. Πάτησε «Αποθήκευση».\n\n"
            "Επεξεργασία\nΚάνε κλικ σε μία γραμμή του πίνακα, άλλαξε τα στοιχεία και πάτησε «Αποθήκευση».\n\n"
            "Φωτογραφία\nΠάτησε «Επιλογή φωτογραφίας» για να συνδέσεις εικόνα με το υλικό. Κάνε κλικ πάνω στη μικρογραφία για να τη δεις μεγαλύτερη.\n\n"
            "Αναζήτηση και φίλτρα\nΧρησιμοποίησε τη γενική αναζήτηση ή τα φίλτρα Είδος υλικού, Αποθήκη και Θέση. Οι εκτυπώσεις μπορούν να βασιστούν στα ενεργά φίλτρα.\n\n"
            "Εκτύπωση\nΗ «Εκτύπωση φίλτρου» δημιουργεί κατάσταση με ό,τι εμφανίζεται μετά τα φίλτρα. Η «Εκτύπωση επιλεγμένων» χρησιμοποιεί μόνο τις γραμμές που έχεις επιλέξει.\n\n"
            "Backup\nΑπό Αρχείο → Δημιουργία Backup αποθηκεύεις τη βάση και όλες τις φωτογραφίες σε ένα ZIP. Από Αρχείο → Επαναφορά από Backup επαναφέρεις ένα προηγούμενο αντίγραφο."
        )
        text.insert("1.0", help_text)
        text.configure(state="disabled")
        ttk.Button(outer, text="Κλείσιμο", command=window.destroy).pack(anchor="e", pady=(10, 0))

    def show_about(self):
        window = tk.Toplevel(self)
        window.title(f"Πληροφορίες - {APP_NAME}")
        window.resizable(False, False)
        window.transient(self)
        outer = ttk.Frame(window, padding=24)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=APP_NAME, style="Header.TLabel").pack(anchor="center")
        ttk.Label(outer, text=f"Έκδοση {APP_VERSION}", style="Muted.TLabel").pack(anchor="center", pady=(2, 18))
        ttk.Label(outer, text="Portable εφαρμογή διαχείρισης αποθήκης για Windows.", justify="center").pack(anchor="center", pady=(0, 14))
        ttk.Label(outer, text=f"Δημιουργία: {APP_CREATOR}").pack(anchor="center")
        ttk.Label(outer, text="dwrean.net").pack(anchor="center", pady=(2, 8))
        link = ttk.Label(outer, text=APP_WEBSITE, style="Link.TLabel", cursor="hand2")
        link.pack(anchor="center")
        link.bind("<Button-1>", lambda _e: webbrowser.open(APP_WEBSITE))
        ttk.Label(outer, text="Δωρεάν εφαρμογή", style="Muted.TLabel").pack(anchor="center", pady=(18, 12))
        ttk.Button(outer, text="Κλείσιμο", command=window.destroy).pack(anchor="center")

    def on_close(self):
        self.db.close()
        self.destroy()


if __name__ == "__main__":
    app = InventoryApp()
    app.mainloop()
