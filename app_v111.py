import tkinter as tk
from tkinter import ttk
import app as core

core.APP_VERSION = "1.1.1"


class InventoryApp(core.InventoryApp):
    def _build_ui(self):
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text=core.APP_NAME, style="Header.TLabel").pack(side="left")
        self.stats_label = ttk.Label(header, text="", style="Muted.TLabel")
        self.stats_label.pack(side="right", padx=4)

        editor = ttk.LabelFrame(outer, text=" Στοιχεία υλικού ", padding=10)
        editor.pack(fill="x", pady=(0, 10))

        form = ttk.Frame(editor)
        form.pack(side="left", fill="both", expand=True)

        # Σταθερό ύψος ώστε η φωτογραφία να μην συμπιέζεται
        photo_box = ttk.Frame(editor, width=210, height=275)
        photo_box.pack(side="right", padx=(14, 0), anchor="n")
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
            combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
            self.filter_combos[key] = combo

        ttk.Button(filters, text="Καθαρισμός φίλτρων", command=self.clear_filters).grid(
            row=1, column=4, sticky="ew", padx=4
        )
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
        self.tree = ttk.Treeview(
            table_frame,
            columns=self.COLUMNS,
            show="headings",
            selectmode="extended",
        )
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
        ttk.Label(bottom, text=f"Βάση: {core.DB_PATH}", style="Muted.TLabel").pack(side="right")


if __name__ == "__main__":
    app = InventoryApp()
    app.mainloop()
