import tkinter as tk
from tkinter import ttk
import app as core

core.APP_VERSION = "1.1.4"


class InventoryApp(core.InventoryApp):
    def _bind_text_shortcuts(self, widget):
        """Enable Windows-style clipboard shortcuts, including with Greek keyboard layout."""
        widget.bind("<Control-KeyPress>", self._handle_text_shortcut, add="+")

    def _handle_text_shortcut(self, event):
        widget = event.widget
        keycode = getattr(event, "keycode", 0)
        keysym = str(getattr(event, "keysym", "")).lower()

        # Windows virtual key codes keep working even when the active layout is Greek.
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
        # Grid layout: οι σταθερές ενότητες μένουν πάντα ορατές και
        # μόνο ο πίνακας αυξομειώνεται όταν αλλάζει το ύψος του παραθύρου.
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

        # Extra height guarantees that both photo buttons remain fully visible.
        photo_box = ttk.Frame(editor, width=210, height=315)
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
            self._bind_text_shortcuts(widget)
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
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.on_tree_select)

        # Σταθερό κάτω toolbar: δεν κρύβεται όταν το παράθυρο δεν είναι maximized.
        bottom = ttk.Frame(outer)
        bottom.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(bottom, text="Εκτύπωση φίλτρου", command=self.print_filtered).pack(side="left", padx=(0, 6))
        ttk.Button(bottom, text="Εκτύπωση επιλεγμένων", command=self.print_selected).pack(side="left", padx=(0, 6))
        ttk.Button(bottom, text="Εξαγωγή CSV", command=self.export_csv).pack(side="left")
        ttk.Label(bottom, text=f"Βάση: {core.DB_PATH}", style="Muted.TLabel").pack(side="right")


if __name__ == "__main__":
    app = InventoryApp()
    app.mainloop()
