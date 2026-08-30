import csv
import html
import os
import sqlite3
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import app as core

core.APP_VERSION = "1.1.5"


class InventoryDB(core.InventoryDB):
    """Database extension for quantity support with automatic migration."""

    def __init__(self, path: Path):
        super().__init__(path)
        self._ensure_column("quantity", "INTEGER NOT NULL DEFAULT 1")
        self.conn.commit()

    def add(self, values: dict[str, str]):
        cur = self.conn.execute(
            """
            INSERT INTO materials(
                name, code, quantity, storage_position, material_type, warehouse, photo_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["name"],
                values["code"],
                int(values["quantity"]),
                values["storage_position"],
                values["material_type"],
                values["warehouse"],
                values.get("photo_path", ""),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def update(self, item_id: int, values: dict[str, str]):
        self.conn.execute(
            """
            UPDATE materials
            SET name=?, code=?, quantity=?, storage_position=?, material_type=?, warehouse=?, photo_path=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                values["name"],
                values["code"],
                int(values["quantity"]),
                values["storage_position"],
                values["material_type"],
                values["warehouse"],
                values.get("photo_path", ""),
                item_id,
            ),
        )
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
            where.append(
                "(name LIKE ? OR code LIKE ? OR CAST(quantity AS TEXT) LIKE ? OR "
                "storage_position LIKE ? OR material_type LIKE ? OR warehouse LIKE ?)"
            )
            params.extend([like] * 6)

        sql = "SELECT * FROM materials"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY name COLLATE NOCASE, code COLLATE NOCASE"
        return self.conn.execute(sql, params).fetchall()


# The inherited application constructor resolves InventoryDB from app.py at runtime.
# Replacing it here keeps old portable databases compatible and upgrades them automatically.
core.InventoryDB = InventoryDB


class InventoryApp(core.InventoryApp):
    COLUMNS = (
        "name",
        "code",
        "quantity",
        "storage_position",
        "material_type",
        "warehouse",
        "photo",
    )

    def _bind_text_shortcuts(self, widget):
        """Enable Windows-style clipboard shortcuts, including with Greek keyboard layout."""
        widget.bind("<Control-KeyPress>", self._handle_text_shortcut, add="+")

    def _handle_text_shortcut(self, event):
        widget = event.widget
        keycode = getattr(event, "keycode", 0)
        keysym = str(getattr(event, "keysym", "")).lower()

        action = None
        if keycode == 67 or keysym == "c":
            action = "copy"
        elif keycode == 86 or keysym == "v":
            action = "paste"
        elif keycode == 88 or keysym == "x":
            action = "cut"
        elif keycode == 65 or keysym == "a":
            action = "select_all"

        if action is None:
            return None

        if action == "select_all":
            try:
                widget.selection_range(0, tk.END)
                widget.icursor(tk.END)
            except (tk.TclError, AttributeError):
                pass
            return "break"

        try:
            first = widget.index("sel.first")
            last = widget.index("sel.last")
            has_selection = first != last
        except (tk.TclError, AttributeError):
            first = last = None
            has_selection = False

        if action == "copy":
            if has_selection:
                try:
                    value = widget.get()
                    selected_text = value[first:last]
                    self.clipboard_clear()
                    self.clipboard_append(selected_text)
                    self.update_idletasks()
                except (tk.TclError, AttributeError):
                    pass
            return "break"

        try:
            state = str(widget.cget("state"))
        except (tk.TclError, AttributeError):
            state = "normal"
        if state in {"disabled", "readonly"}:
            return "break"

        if action == "cut":
            if has_selection:
                try:
                    value = widget.get()
                    selected_text = value[first:last]
                    self.clipboard_clear()
                    self.clipboard_append(selected_text)
                    widget.delete(first, last)
                    self.update_idletasks()
                except (tk.TclError, AttributeError):
                    pass
            return "break"

        if action == "paste":
            try:
                pasted_text = self.clipboard_get()
            except tk.TclError:
                return "break"
            try:
                if has_selection:
                    widget.delete(first, last)
                widget.insert(widget.index(tk.INSERT), pasted_text)
            except (tk.TclError, AttributeError):
                pass
            return "break"

        return None

    def _build_brand_title(self, parent):
        """Text-only dwrean.net style branding: black 'dwrean', red 'Αποθήκη'."""
        brand = ttk.Frame(parent)
        brand.pack(side="left")
        brand_font = ("Arial Black", 22)
        ttk.Label(
            brand,
            text="dwrean",
            font=brand_font,
            foreground="#111111",
        ).pack(side="left")
        ttk.Label(
            brand,
            text=" Αποθήκη",
            font=brand_font,
            foreground="#c71920",
        ).pack(side="left")

    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._build_brand_title(header)
        self.stats_label = ttk.Label(header, text="", style="Muted.TLabel")
        self.stats_label.pack(side="right", padx=4)

        editor = ttk.LabelFrame(outer, text=" Στοιχεία υλικού ", padding=10)
        editor.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        form = ttk.Frame(editor)
        form.pack(side="left", fill="both", expand=True)

        photo_box = ttk.Frame(editor, width=210, height=315)
        photo_box.pack(side="right", padx=(14, 0), anchor="n")
        photo_box.pack_propagate(False)

        self.vars = {
            "name": tk.StringVar(),
            "code": tk.StringVar(),
            "quantity": tk.StringVar(value="1"),
            "storage_position": tk.StringVar(),
            "material_type": tk.StringVar(),
            "warehouse": tk.StringVar(),
        }
        labels = [
            ("Ονομασία υλικού", "name"),
            ("Κωδικός αριθμός", "code"),
            ("Ποσότητα", "quantity"),
            ("Θέση αποθήκευσης", "storage_position"),
            ("Είδος υλικού", "material_type"),
            ("Αποθήκη", "warehouse"),
        ]

        for col, (label, key) in enumerate(labels):
            ttk.Label(form, text=label).grid(row=0, column=col, sticky="w", padx=4, pady=(0, 4))
            if key in {"material_type", "warehouse", "storage_position"}:
                widget = ttk.Combobox(form, textvariable=self.vars[key])
                setattr(self, f"combo_{key}", widget)
            elif key == "quantity":
                widget = ttk.Entry(form, textvariable=self.vars[key], width=9)
            else:
                widget = ttk.Entry(form, textvariable=self.vars[key])
            widget.grid(row=1, column=col, sticky="ew", padx=4)
            self._bind_text_shortcuts(widget)
            form.columnconfigure(col, weight=0 if key == "quantity" else 1)

        actions = ttk.Frame(form)
        actions.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(10, 0), padx=4)
        ttk.Button(actions, text="Νέα καταχώριση", command=self.clear_form).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Αποθήκευση", command=self.save_item).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Διαγραφή", command=self.delete_selected).pack(side="left")

        ttk.Label(photo_box, text="Φωτογραφία υλικού").pack(anchor="w", pady=(0, 5))
        preview_frame = tk.Frame(photo_box, width=185, height=185, bd=1, relief="solid", bg="white")
        preview_frame.pack(anchor="center", pady=(0, 7))
        preview_frame.pack_propagate(False)

        self.photo_label = tk.Label(
            preview_frame,
            text="Χωρίς φωτογραφία",
            anchor="center",
            justify="center",
            bg="white",
        )
        self.photo_label.pack(fill="both", expand=True)
        self.photo_label.bind("<Button-1>", self.open_full_photo)

        ttk.Button(
            photo_box,
            text="Επιλογή φωτογραφίας",
            command=self.choose_photo,
        ).pack(fill="x", padx=2, pady=(0, 5))
        ttk.Button(
            photo_box,
            text="Αφαίρεση φωτογραφίας",
            command=self.remove_photo,
        ).pack(fill="x", padx=2)

        filters = ttk.LabelFrame(outer, text=" Αναζήτηση και φίλτρα ", padding=10)
        filters.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        self.search_var = tk.StringVar()
        ttk.Label(filters, text="Γενική αναζήτηση").grid(row=0, column=0, sticky="w", padx=4)
        search_entry = ttk.Entry(filters, textvariable=self.search_var)
        search_entry.grid(row=1, column=0, sticky="ew", padx=4)
        self._bind_text_shortcuts(search_entry)
        search_entry.bind("<KeyRelease>", lambda _e: self.refresh())

        self.filter_vars = {
            "material_type": tk.StringVar(),
            "warehouse": tk.StringVar(),
            "storage_position": tk.StringVar(),
        }
        filter_defs = [
            ("Είδος υλικού", "material_type"),
            ("Αποθήκη", "warehouse"),
            ("Θέση", "storage_position"),
        ]
        self.filter_combos = {}
        for i, (label, key) in enumerate(filter_defs, start=1):
            ttk.Label(filters, text=label).grid(row=0, column=i, sticky="w", padx=4)
            combo = ttk.Combobox(filters, textvariable=self.filter_vars[key], state="readonly")
            combo.grid(row=1, column=i, sticky="ew", padx=4)
            self._bind_text_shortcuts(combo)
            combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
            self.filter_combos[key] = combo

        ttk.Button(filters, text="Καθαρισμός φίλτρων", command=self.clear_filters).grid(
            row=1, column=4, sticky="ew", padx=4
        )
        for i in range(5):
            filters.columnconfigure(i, weight=1 if i < 4 else 0)

        table_frame = ttk.Frame(outer)
        table_frame.grid(row=3, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        headings = {
            "name": "Ονομασία υλικού",
            "code": "Κωδικός",
            "quantity": "Ποσότητα",
            "storage_position": "Θέση αποθήκευσης",
            "material_type": "Είδος υλικού",
            "warehouse": "Αποθήκη",
            "photo": "Φωτογραφία",
        }
        self.tree = ttk.Treeview(
            table_frame,
            columns=self.COLUMNS,
            show="headings",
            selectmode="extended",
        )
        for col in self.COLUMNS:
            self.tree.heading(col, text=headings[col], command=lambda c=col: self.sort_tree(c, False))
            if col == "name":
                width = 225
            elif col in {"quantity", "photo"}:
                width = 90
            else:
                width = 150
            self.tree.column(col, width=width, minwidth=70, anchor="center" if col == "quantity" else "w")

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.on_tree_select)

        bottom = ttk.Frame(outer)
        bottom.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(bottom, text="Εκτύπωση φίλτρου", command=self.print_filtered).pack(side="left", padx=(0, 6))
        ttk.Button(bottom, text="Εκτύπωση επιλεγμένων", command=self.print_selected).pack(side="left", padx=(0, 6))
        ttk.Button(bottom, text="Εξαγωγή CSV", command=self.export_csv).pack(side="left")
        ttk.Label(bottom, text=f"Βάση: {core.DB_PATH}", style="Muted.TLabel").pack(side="right")

    def validate_form(self, values: dict[str, str]):
        if not core.InventoryApp.validate_form(self, values):
            return False
        quantity = values.get("quantity", "").strip()
        if not quantity:
            messagebox.showwarning(core.APP_NAME, "Συμπλήρωσε την ποσότητα του υλικού.")
            return False
        try:
            number = int(quantity)
        except ValueError:
            messagebox.showwarning(core.APP_NAME, "Η ποσότητα πρέπει να είναι ακέραιος αριθμός.")
            return False
        if number < 0:
            messagebox.showwarning(core.APP_NAME, "Η ποσότητα δεν μπορεί να είναι αρνητική.")
            return False
        return True

    def clear_form(self):
        core.InventoryApp.clear_form(self)
        self.vars["quantity"].set("1")

    def refresh(self):
        rows = self.db.query(self.current_filters(), self.search_var.get())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["name"],
                    row["code"],
                    row["quantity"],
                    row["storage_position"],
                    row["material_type"],
                    row["warehouse"],
                    "Ναι" if row["photo_path"] else "Όχι",
                ),
            )
        self._refresh_combo_values()
        self.stats_label.config(text=f"Εμφάνιση: {len(rows)}  |  Σύνολο: {self.db.count()}")

    def sort_tree(self, column: str, reverse: bool):
        if column == "quantity":
            data = []
            for item in self.tree.get_children(""):
                try:
                    value = int(self.tree.set(item, column))
                except ValueError:
                    value = 0
                data.append((value, item))
        else:
            data = [(self.tree.set(item, column).casefold(), item) for item in self.tree.get_children("")]
        data.sort(reverse=reverse)
        for index, (_value, item) in enumerate(data):
            self.tree.move(item, "", index)
        self.tree.heading(column, command=lambda: self.sort_tree(column, not reverse))

    def open_print_report(self, rows, title: str):
        if not rows:
            messagebox.showinfo(core.APP_NAME, "Δεν υπάρχουν εγγραφές για εκτύπωση.")
            return

        generated = datetime.now().strftime("%d/%m/%Y %H:%M")
        trs = []
        for row in rows:
            photo = "Ναι" if row["photo_path"] else "Όχι"
            values = [
                row["name"],
                row["code"],
                row["quantity"],
                row["storage_position"],
                row["material_type"],
                row["warehouse"],
                photo,
            ]
            cells = "".join(f"<td>{html.escape(str(value if value is not None else ''))}</td>" for value in values)
            trs.append(f"<tr>{cells}</tr>")

        report = f"""<!doctype html>
<html lang="el"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;color:#111}}h1{{font-size:22px;margin-bottom:4px}} .meta{{color:#555;margin-bottom:18px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #bbb;padding:7px;text-align:left;vertical-align:top}}th{{background:#eee}} .toolbar{{margin-bottom:16px}}button{{font-size:14px;padding:8px 14px}}@media print{{.toolbar{{display:none}} body{{margin:0}}}}</style></head>
<body><div class="toolbar"><button onclick="window.print()">Εκτύπωση</button></div><h1>{html.escape(core.APP_NAME)} — {html.escape(title)}</h1><div class="meta">Ημερομηνία: {generated} &nbsp;|&nbsp; Εγγραφές: {len(rows)}</div><table><thead><tr><th>Ονομασία υλικού</th><th>Κωδικός</th><th>Ποσότητα</th><th>Θέση αποθήκευσης</th><th>Είδος υλικού</th><th>Αποθήκη</th><th>Φωτογραφία</th></tr></thead><tbody>{''.join(trs)}</tbody></table></body></html>"""
        fd, path = tempfile.mkstemp(prefix="dwrean_apothiki_", suffix=".html")
        os.close(fd)
        Path(path).write_text(report, encoding="utf-8")
        webbrowser.open(Path(path).as_uri())

    def export_csv(self):
        rows = self.filtered_rows()
        if not rows:
            messagebox.showinfo(core.APP_NAME, "Δεν υπάρχουν εγγραφές για εξαγωγή.")
            return

        path = filedialog.asksaveasfilename(
            title="Εξαγωγή CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"dwrean-apothiki-{datetime.now().strftime('%Y%m%d')}.csv",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                "Ονομασία υλικού",
                "Κωδικός",
                "Ποσότητα",
                "Θέση αποθήκευσης",
                "Είδος υλικού",
                "Αποθήκη",
                "Φωτογραφία",
            ])
            for row in rows:
                writer.writerow([
                    row["name"],
                    row["code"],
                    row["quantity"],
                    row["storage_position"],
                    row["material_type"],
                    row["warehouse"],
                    row["photo_path"],
                ])
        messagebox.showinfo(core.APP_NAME, "Η εξαγωγή ολοκληρώθηκε.")

    def show_help(self):
        window = tk.Toplevel(self)
        window.title(f"Βοήθεια - {core.APP_NAME}")
        window.geometry("650x560")
        window.minsize(560, 460)
        window.transient(self)
        outer = ttk.Frame(window, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Οδηγίες χρήσης", style="Header.TLabel").pack(anchor="w", pady=(0, 12))
        text = tk.Text(outer, wrap="word", font=("Segoe UI", 10), relief="solid", borderwidth=1, padx=12, pady=12)
        text.pack(fill="both", expand=True)
        help_text = (
            "Καταχώριση υλικού\nΣυμπλήρωσε την ονομασία, τον κωδικό και την ποσότητα. Προαιρετικά πρόσθεσε θέση αποθήκευσης, είδος υλικού, αποθήκη και φωτογραφία. Πάτησε «Αποθήκευση».\n\n"
            "Ποσότητα\nΗ ποσότητα είναι ακέραιος αριθμός από 0 και πάνω. Η προεπιλεγμένη τιμή σε νέα καταχώριση είναι 1.\n\n"
            "Επεξεργασία\nΚάνε κλικ σε μία γραμμή του πίνακα, άλλαξε τα στοιχεία ή την ποσότητα και πάτησε «Αποθήκευση».\n\n"
            "Φωτογραφία\nΠάτησε «Επιλογή φωτογραφίας» για να συνδέσεις εικόνα με το υλικό. Κάνε κλικ πάνω στη μικρογραφία για να τη δεις μεγαλύτερη.\n\n"
            "Αναζήτηση και φίλτρα\nΧρησιμοποίησε τη γενική αναζήτηση ή τα φίλτρα Είδος υλικού, Αποθήκη και Θέση.\n\n"
            "Εκτύπωση\nΗ «Εκτύπωση φίλτρου» δημιουργεί κατάσταση με ό,τι εμφανίζεται μετά τα φίλτρα. Η «Εκτύπωση επιλεγμένων» χρησιμοποιεί μόνο τις γραμμές που έχεις επιλέξει.\n\n"
            "Backup\nΑπό Αρχείο → Δημιουργία Backup αποθηκεύεις τη βάση και όλες τις φωτογραφίες σε ένα ZIP. Από Αρχείο → Επαναφορά από Backup επαναφέρεις ένα προηγούμενο αντίγραφο."
        )
        text.insert("1.0", help_text)
        text.configure(state="disabled")
        ttk.Button(outer, text="Κλείσιμο", command=window.destroy).pack(anchor="e", pady=(10, 0))


if __name__ == "__main__":
    app = InventoryApp()
    app.mainloop()
