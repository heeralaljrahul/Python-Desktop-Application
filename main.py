import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import shutil
import random
import re
import sqlite3
import calendar
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

APP_NAME = "RENUS AUTHENTIC DELIGHTS"
APP_LOCATION = "Pretoria, South Africa"
APP_TAGLINE = "Gourmet Pretoria curries & spices"
STATUSES = ["Pending", "Preparing", "Ready", "Completed"]
THEME_COLOR = "#2CC985"
ACCENT = "#FBC02D"


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")


def currency(val: float) -> str:
    return f"R {val:,.2f}"


def valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def ensure_positive_number(value: str, allow_zero: bool = False) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num < 0 or (not allow_zero and num == 0):
        return None
    return num


def validate_numeric_input(action: str, value_if_allowed: str) -> bool:
    if action == "0":
        return True
    try:
        float(value_if_allowed)
        return True
    except ValueError:
        return False


def validate_int_input(action: str, value_if_allowed: str) -> bool:
    if action == "0":
        return True
    return value_if_allowed.isdigit()


def validate_city_name(city: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z\s\-'.]*$", city)) if city else True


def validate_phone(phone: str) -> bool:
    return bool(re.match(r"^\+?[0-9\s-]{7,16}$", phone)) if phone else True


class DBManager:
    def __init__(self, db_name: str = "renus_system.db"):
        self.conn = sqlite3.connect(db_name)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.init_db()

    def init_db(self) -> None:
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER DEFAULT 0,
                image_path TEXT
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                address TEXT,
                city TEXT,
                phone TEXT
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                surname TEXT,
                role TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                total REAL NOT NULL DEFAULT 0,
                notes TEXT,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS order_items (
                order_id INTEGER,
                item_id INTEGER,
                quantity INTEGER,
                subtotal REAL,
                FOREIGN KEY(order_id) REFERENCES orders(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            )
            """
        )
        # Safety migrations
        self._ensure_column("customers", "address", "TEXT")
        self._ensure_column("customers", "city", "TEXT")
        self._ensure_column("customers", "phone", "TEXT")
        self._ensure_column("orders", "notes", "TEXT")
        self._ensure_column("users", "surname", "TEXT")
        self._ensure_column("items", "item_code", "TEXT")
        self._ensure_column("users", "user_code", "TEXT")
        self._ensure_column("orders", "order_code", "TEXT")
        self._ensure_index("items", "item_code")
        self._ensure_index("users", "user_code")
        self._ensure_index("orders", "order_code")
        self.conn.commit()
        self.seed_data()
        self.ensure_codes()

    def _ensure_column(self, table: str, column: str, col_type: str) -> None:
        self.cursor.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in self.cursor.fetchall()]
        if column not in cols:
            self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def _ensure_index(self, table: str, column: str) -> None:
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql LIKE ?",
            (table, f"%({column})%"),
        )
        if not self.cursor.fetchone():
            try:
                self.cursor.execute(f"CREATE UNIQUE INDEX idx_{table}_{column} ON {table}({column})")
            except sqlite3.OperationalError:
                # Ignore if the column allows duplicates currently
                pass

    def _ensure_codes_for_table(self, table: str, column: str, prefix: str) -> None:
        rows = self.fetch(f"SELECT id, {column} FROM {table}")
        for row in rows:
            current = row[column]
            if not current:
                code = self.generate_code(prefix, row["id"])
                # Guarantee uniqueness even on reused IDs across databases
                counter = 1
                while self.fetch(f"SELECT 1 FROM {table} WHERE {column}=?", (code,)):
                    code = f"{prefix}{row['id']:05d}-{counter}"
                    counter += 1
                self.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (code, row["id"]))

    def ensure_codes(self) -> None:
        self._ensure_codes_for_table("items", "item_code", "ITM-")
        self._ensure_codes_for_table("users", "user_code", "USR-")
        self._ensure_codes_for_table("orders", "order_code", "ORD-")

    @staticmethod
    def generate_code(prefix: str, record_id: int) -> str:
        return f"{prefix}{record_id:05d}"

    def ensure_row_code(self, table: str, column: str, prefix: str, row_id: int) -> str:
        res = self.fetch(f"SELECT {column} FROM {table} WHERE id=?", (row_id,))
        current = res[0][0] if res else None
        if current:
            return current
        code = self.generate_code(prefix, row_id)
        counter = 1
        while self.fetch(f"SELECT 1 FROM {table} WHERE {column}=?", (code,)):
            code = f"{prefix}{row_id:05d}-{counter}"
            counter += 1
        self.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (code, row_id))
        return code

    def seed_data(self) -> None:
        if not os.path.exists("assets"):
            os.makedirs("assets")
        self._create_placeholder_assets()

        if self.fetch("SELECT COUNT(*) FROM items")[0][0] == 0:
            img_path = os.path.abspath("assets/placeholder.png")
            items = [
                ("Lamb Breyani", "Menu", 130.00),
                ("Chicken Breyani", "Menu", 100.00),
                ("Lamb Curry (Boneless)", "Menu", 140.00),
                ("Chicken Curry", "Menu", 95.00),
                ("Bunny Chow (Lamb)", "Menu", 90.00),
                ("Bunny Chow (Beans)", "Menu", 55.00),
                ("Roti Roll (Chicken)", "Menu", 50.00),
                ("Samoosas (Mince - Dozen)", "Snack", 70.00),
                ("Samoosas (Potato - Dozen)", "Snack", 50.00),
                ("Chilli Bites (Daltjies)", "Snack", 40.00),
                ("Mother-in-Law Masala (1kg)", "Spice", 150.00),
                ("Kashmiri Chilli (1kg)", "Spice", 180.00),
                ("Turmeric / Borrie (1kg)", "Spice", 90.00),
                ("Jeera Powder (1kg)", "Spice", 120.00),
                ("Dhania Powder (1kg)", "Spice", 100.00),
                ("Garam Masala (500g)", "Spice", 85.00),
                ("Cinnamon Sticks (100g)", "Spice", 35.00),
                ("Elachi / Cardamom (100g)", "Spice", 60.00),
                ("Leaf Masala (200g)", "Spice", 45.00),
                ("Biryani Mix (Pack)", "Spice", 55.00),
            ]
            for n, c, p in items:
                iid = self.execute(
                    "INSERT INTO items (name, category, price, stock, image_path) VALUES (?, ?, ?, 50, ?)",
                    (n, c, p, img_path),
                )
                self.ensure_row_code("items", "item_code", "ITM-", iid)

        # Backfill surnames for existing users if column was added later
        missing = self.fetch("SELECT id, full_name FROM users WHERE surname IS NULL OR surname = ''")
        for row in missing:
            parts = row[1].split()
            surname = parts[-1] if len(parts) > 1 else ""
            self.execute("UPDATE users SET surname=? WHERE id=?", (surname, row[0]))

        if self.fetch("SELECT COUNT(*) FROM customers")[0][0] == 0:
            names = [
                "Rahul Heeralal",
                "Thabo Mbeki",
                "Keshav Naidoo",
                "Precious Dlamini",
                "Johan van der Merwe",
                "Yusuf Patel",
                "Fatima Jaffer",
                "Sipho Nkosi",
                "Kyle Abrahams",
                "Nadia Govender",
                "Zainab Osman",
                "Charl Venter",
                "Bongiwe Zungu",
                "Mohammed Ally",
                "Priya Singh",
                "Lebo Molefe",
                "Wayne Smith",
                "Aisha Khan",
                "Devan Pillay",
                "Bianca Botha",
            ]
            for n in names:
                self.execute(
                    "INSERT INTO customers (name, email, address, city, phone) VALUES (?, ?, ?, ?, ?)",
                    (n, n.lower().replace(" ", ".") + "@mail.com", "42 Spice Route", "Durban", "+27 31 555 1234"),
                )

        if self.fetch("SELECT COUNT(*) FROM users")[0][0] == 0:
            staff = [
                ("Renu", "Naidoo", "Owner", "renu@delights.co.za", "+27 82 000 1111"),
                ("Sibusiso", "Mkhize", "Manager", "sbu@delights.co.za", "+27 83 123 9876"),
                ("Priya", "Moodley", "Cashier", "priya@delights.co.za", "+27 74 222 1111"),
            ]
            for first, surname, role, email, phone in staff:
                full = f"{first} {surname}".strip()
                uid = self.execute(
                    "INSERT INTO users (full_name, surname, role, email, phone) VALUES (?, ?, ?, ?, ?)",
                    (full, surname, role, email, phone),
                )
                self.ensure_row_code("users", "user_code", "USR-", uid)

        if self.fetch("SELECT COUNT(*) FROM orders")[0][0] == 0:
            i_ids = [row[0] for row in self.fetch("SELECT id FROM items")]
            c_ids = [row[0] for row in self.fetch("SELECT id FROM customers")]
            for _ in range(30):
                cid = random.choice(c_ids)
                date = (datetime.now() - timedelta(days=random.randint(0, 60))).strftime("%Y-%m-%d %H:%M:%S")
                status = random.choice(STATUSES[:-1])
                oid = self.execute(
                    "INSERT INTO orders (customer_id, date, status, total) VALUES (?, ?, ?, 0)",
                    (cid, date, status),
                )
                self.ensure_row_code("orders", "order_code", "ORD-", oid)
                total = 0
                for _ in range(random.randint(1, 4)):
                    iid = random.choice(i_ids)
                    qty = random.randint(1, 3)
                    price = self.fetch("SELECT price FROM items WHERE id=?", (iid,))[0][0]
                    subtotal = price * qty
                    total += subtotal
                    self.execute(
                        "INSERT INTO order_items (order_id, item_id, quantity, subtotal) VALUES (?, ?, ?, ?)",
                        (oid, iid, qty, subtotal),
                    )
                self.execute("UPDATE orders SET total=? WHERE id=?", (total, oid))

    def _create_placeholder_assets(self) -> None:
        logo_path = "assets/logo.png"
        if not os.path.exists(logo_path):
            img = Image.new("RGB", (120, 120), THEME_COLOR)
            draw = ImageDraw.Draw(img)
            draw.text((28, 40), "RA", fill="white")
            img.save(logo_path)
        ph_path = "assets/placeholder.png"
        if not os.path.exists(ph_path):
            img = Image.new("RGB", (120, 120), "#4a4a4a")
            draw = ImageDraw.Draw(img)
            draw.text((28, 45), "SA", fill="white")
            img.save(ph_path)

    def fetch(self, query: str, params: Tuple = ()) -> List[sqlite3.Row]:
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def execute(self, query: str, params: Tuple = ()) -> int:
        self.cursor.execute(query, params)
        self.conn.commit()
        return self.cursor.lastrowid

    def status_for_order(self, oid: int) -> str:
        res = self.fetch("SELECT status FROM orders WHERE id=?", (oid,))
        return res[0][0] if res else ""

    def normalize_status(self, status: str) -> str:
        if status.lower() == "delivered":
            return "Completed"
        return status if status in STATUSES else "Pending"

    def monthly_report(self, year: int, month: Optional[int]) -> Dict:
        if month:
            start = datetime(year, month, 1)
            if month == 12:
                end = datetime(year + 1, 1, 1)
            else:
                end = datetime(year, month + 1, 1)
        else:
            start = datetime(year, 1, 1)
            end = datetime(year + 1, 1, 1)

        orders = self.fetch(
            "SELECT id, date, status, total FROM orders WHERE date >= ? AND date < ?",
            (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")),
        )
        total_revenue = sum(row[3] for row in orders)
        status_counts: Dict[str, int] = {s: 0 for s in STATUSES}
        for row in orders:
            status_counts[self.normalize_status(row[2])] = status_counts.get(self.normalize_status(row[2]), 0) + 1

        top_items = self.fetch(
            """
            SELECT i.name, SUM(oi.quantity) as qty
            FROM order_items oi
            JOIN items i ON oi.item_id = i.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.date >= ? AND o.date < ?
            GROUP BY i.name
            ORDER BY qty DESC
            LIMIT 5
            """,
            (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")),
        )
        return {
            "orders": orders,
            "total_revenue": total_revenue,
            "status_counts": status_counts,
            "top_items": top_items,
            "start": start,
            "end": end,
        }


db = DBManager()


class RenusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} | Manager")
        self.geometry("1500x950")
        self.logo_img = ctk.CTkImage(Image.open("assets/logo.png"), size=(44, 44))
        self.cart: Dict[int, Dict] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.create_sidebar()
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "gray10"))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.show_new_order()

    # ---------- LAYOUT HELPERS ----------
    def create_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=230, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(sidebar, text="", image=self.logo_img).grid(row=0, column=0, pady=(30, 10))
        ctk.CTkLabel(sidebar, text=APP_NAME.upper(), font=("Arial", 18, "bold"), justify="center").grid(
            row=1, column=0, pady=(0, 20)
        )

        buttons = [
            ("New Order", self.show_new_order),
            ("Order History", self.show_history),
            ("Items", self.show_menu),
            ("Customers", self.show_customers),
            ("Users", self.show_users),
            ("Reports", self.show_reports),
        ]
        for idx, (text, cmd) in enumerate(buttons, start=2):
            ctk.CTkButton(
                sidebar,
                text=text,
                command=cmd,
                fg_color="transparent",
                border_width=1,
                height=42,
                hover_color="#1f6aa5",
                text_color=("gray10", "gray90"),
            ).grid(row=idx, column=0, padx=15, pady=6, sticky="ew")

        switch = ctk.CTkSwitch(
            sidebar,
            text="Dark Mode",
            command=lambda: ctk.set_appearance_mode("Dark" if switch.get() else "Light"),
        )
        switch.select()
        switch.grid(row=11, column=0, pady=20)

    def clear_content(self) -> None:
        for widget in self.content.winfo_children():
            widget.destroy()

    def add_header(self, title: str, subtitle: Optional[str] = None) -> None:
        head = ctk.CTkFrame(self.content, height=80, fg_color=("white", "#1f1f1f"))
        head.pack(fill="x")
        ctk.CTkLabel(head, text="", image=self.logo_img).pack(side="left", padx=20, pady=10)
        text_frame = ctk.CTkFrame(head, fg_color="transparent")
        text_frame.pack(side="left", pady=10)
        ctk.CTkLabel(text_frame, text=title, font=("Arial", 26, "bold")).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(text_frame, text=subtitle, font=("Arial", 14), text_color="gray").pack(anchor="w")
        ctk.CTkLabel(head, text=f"{APP_LOCATION}", font=("Arial", 12), text_color="gray").pack(side="right", padx=20)

    # ---------- NEW ORDER ----------
    def show_new_order(self) -> None:
        self.clear_content()
        self.add_header("New Order", "Capture orders professionally with validation")

        split = ctk.CTkFrame(self.content, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=20, pady=20)

        # Left: Menu grid
        menu_frame = ctk.CTkFrame(split, fg_color="transparent")
        menu_frame.pack(side="left", fill="both", expand=True, padx=(0, 18))

        filter_row = ctk.CTkFrame(menu_frame, fg_color="transparent")
        filter_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(filter_row, text="Filter", font=("Arial", 14, "bold")).pack(side="left", padx=8)
        self.cat_var = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(filter_row, variable=self.cat_var, values=["All", "Menu", "Spice", "Snack"], width=120,
                          command=lambda _: self.load_grid(scroll)).pack(side="left", padx=8)
        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(filter_row, placeholder_text="Search item", textvariable=self.search_var)
        search_entry.pack(side="left", padx=8, fill="x", expand=True)
        search_entry.bind("<KeyRelease>", lambda _e: self.load_grid(scroll))
        ctk.CTkButton(filter_row, text="✕", width=28, command=lambda: self.clear_menu_filter(scroll)).pack(side="left", padx=4)

        scroll = ctk.CTkScrollableFrame(menu_frame)
        scroll.pack(fill="both", expand=True)
        self.load_grid(scroll)

        # Right: Cart
        cart = ctk.CTkFrame(split, width=520, fg_color=("white", "#2b2b2b"))
        cart.pack(side="right", fill="y")
        ctk.CTkLabel(cart, text="Current Order", font=("Arial", 18, "bold")).pack(pady=15)

        custs = db.fetch("SELECT id, name FROM customers ORDER BY name")
        customer_values = [f"{c['id']} - {c['name']}" for c in custs]
        self.cust_var = ctk.StringVar(value=customer_values[0] if customer_values else "")
        ctk.CTkOptionMenu(cart, variable=self.cust_var, values=customer_values or ["No customers"],
                          state="normal" if customer_values else "disabled").pack(fill="x", padx=20)

        self.cart_frame = ctk.CTkScrollableFrame(cart, fg_color="transparent")
        self.cart_frame.pack(fill="both", expand=True, padx=10, pady=10)

        foot = ctk.CTkFrame(cart, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=15)
        self.total_lbl = ctk.CTkLabel(foot, text="Total: R 0.00", font=("Arial", 22, "bold"))
        self.total_lbl.pack(pady=10)
        ctk.CTkButton(
            foot,
            text="CONFIRM ORDER",
            height=52,
            fg_color=THEME_COLOR,
            font=("Arial", 16, "bold"),
            command=self.checkout,
        ).pack(fill="x")
        self.update_cart()

    def clear_menu_filter(self, target: ctk.CTkScrollableFrame) -> None:
        self.cat_var.set("All")
        self.search_var.set("")
        self.load_grid(target)

    def load_grid(self, parent: ctk.CTkScrollableFrame) -> None:
        for w in parent.winfo_children():
            w.destroy()
        cat = self.cat_var.get()
        keyword = self.search_var.get().lower()
        q = "SELECT * FROM items"
        params: Tuple = ()
        if cat != "All":
            q += " WHERE category=?"
            params = (cat,)
        items = db.fetch(q, params)
        r = c = 0
        for item in items:
            if keyword and keyword not in item[1].lower():
                continue
            card = ctk.CTkFrame(parent, border_width=1, border_color="gray40", corner_radius=10)
            card.grid(row=r, column=c, padx=10, pady=8, sticky="ew")
            try:
                img = ctk.CTkImage(Image.open(item[5]), size=(70, 70)) if item[5] else None
                if img:
                    ctk.CTkLabel(card, text="", image=img).pack(side="left", padx=10, pady=10)
            except Exception:
                pass
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", padx=5)
            ctk.CTkLabel(info, text=item[1], font=("Arial", 14, "bold"), wraplength=150).pack(anchor="w")
            ctk.CTkLabel(info, text=currency(item[3]), font=("Arial", 12)).pack(anchor="w")
            ctk.CTkLabel(info, text=f"Stock: {item[4]}", font=("Arial", 10), text_color="gray").pack(anchor="w")
            ctk.CTkButton(
                card,
                text="Add",
                width=60,
                fg_color=THEME_COLOR,
                command=lambda x=item: self.add_cart(x),
            ).pack(side="right", padx=10)
            c += 1
            if c > 2:
                c = 0
                r += 1

    def add_cart(self, item: sqlite3.Row) -> None:
        if item[0] in self.cart:
            self.cart[item[0]]["qty"] += 1
        else:
            self.cart[item[0]] = {"name": item[1], "price": item[3], "qty": 1}
        self.update_cart()

    def rem_cart(self, iid: int) -> None:
        self.cart.pop(iid, None)
        self.update_cart()

    def change_cart_qty(self, iid: int, delta: int) -> None:
        if iid not in self.cart:
            return
        self.cart[iid]["qty"] += delta
        if self.cart[iid]["qty"] <= 0:
            self.cart.pop(iid, None)
        self.update_cart()

    def update_cart(self) -> None:
        if not hasattr(self, "cart_frame") or not self.cart_frame.winfo_exists():
            return
        for w in self.cart_frame.winfo_children():
            w.destroy()
        self.cart_frame.grid_columnconfigure(0, weight=1)
        self.cart_frame.grid_columnconfigure(1, weight=1)
        total = 0
        for idx, (iid, data) in enumerate(self.cart.items()):
            subtotal = data["price"] * data["qty"]
            total += subtotal
            card = ctk.CTkFrame(self.cart_frame, fg_color=("gray95", "#333"), corner_radius=10)
            card.grid(row=idx // 2, column=idx % 2, padx=8, pady=6, sticky="nsew")
            card.grid_columnconfigure(0, weight=1)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.grid(row=0, column=0, sticky="ew", pady=(6, 0), padx=8)
            header.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                header, text=data["name"], anchor="w", wraplength=200, font=("Arial", 13, "bold")
            ).grid(row=0, column=0, sticky="w")
            ctk.CTkButton(
                header, text="x", width=26, fg_color="red", command=lambda x=iid: self.rem_cart(x)
            ).grid(row=0, column=1, padx=(8, 0))

            controls = ctk.CTkFrame(card, fg_color="transparent")
            controls.grid(row=1, column=0, sticky="w", padx=8, pady=(6, 4))
            ctk.CTkButton(controls, text="-", width=30, command=lambda x=iid: self.change_cart_qty(x, -1)).pack(
                side="left", padx=2
            )
            ctk.CTkLabel(controls, text=str(data["qty"]), width=34, anchor="center").pack(side="left", padx=2)
            ctk.CTkButton(controls, text="+", width=30, command=lambda x=iid: self.change_cart_qty(x, 1)).pack(
                side="left", padx=2
            )
            ctk.CTkLabel(
                card, text=currency(subtotal), anchor="e", font=("Arial", 12, "bold")
            ).grid(row=2, column=0, sticky="e", padx=12, pady=(0, 8))
        self.total_lbl.configure(text=f"Total: {currency(total)}")

    def checkout(self) -> None:
        if not self.cart:
            messagebox.showwarning("Cart Empty", "Add items before confirming the order.")
            return
        if not self.cust_var.get():
            messagebox.showwarning("No Customer", "Select a customer before checking out.")
            return
        cid = int(self.cust_var.get().split(" - ")[0])
        total = sum(d["price"] * d["qty"] for d in self.cart.values())
        oid = db.execute(
            "INSERT INTO orders (customer_id, date, total, status) VALUES (?, ?, ?, 'Pending')",
            (cid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total),
        )
        db.ensure_row_code("orders", "order_code", "ORD-", oid)
        for iid, d in self.cart.items():
            db.execute(
                "INSERT INTO order_items (order_id, item_id, quantity, subtotal) VALUES (?, ?, ?, ?)",
                (oid, iid, d["qty"], d["price"] * d["qty"]),
            )
        messagebox.showinfo("Success", f"Order #{oid} placed successfully")
        self.cart = {}
        self.update_cart()
        self.show_history()

    # ---------- ORDER HISTORY ----------
    def show_history(self) -> None:
        self.clear_content()
        self.add_header("Order Management", "View, update and export orders")
        main = ctk.CTkFrame(self.content, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        filter_row_top = ctk.CTkFrame(main, fg_color="transparent")
        filter_row_top.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(filter_row_top, text="Status", font=("Arial", 12, "bold")).pack(side="left", padx=5)
        self.status_filter = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(
            filter_row_top,
            variable=self.status_filter,
            values=["All"] + STATUSES,
            width=120,
            command=lambda _: self.load_orders(),
        ).pack(side="left", padx=5)
        ctk.CTkLabel(filter_row_top, text="Month", font=("Arial", 12, "bold")).pack(side="left", padx=5)
        self.month_filter = ctk.StringVar(value="All")
        months = ["All"] + [datetime(2024, m, 1).strftime("%b") for m in range(1, 13)]
        ctk.CTkOptionMenu(
            filter_row_top,
            variable=self.month_filter,
            values=months,
            width=100,
            command=lambda _: self.load_orders(),
        ).pack(side="left", padx=5)
        self.order_search_var = ctk.StringVar()
        search = ctk.CTkEntry(
            filter_row_top,
            placeholder_text="Search by ID, customer, status, item...",
            textvariable=self.order_search_var,
        )
        search.pack(side="left", padx=6, fill="x", expand=True)
        search.bind("<KeyRelease>", lambda _e: self.load_orders())
        ctk.CTkButton(filter_row_top, text="✕", width=28, command=self.clear_order_filters).pack(side="left", padx=4)

        filter_row_dates = ctk.CTkFrame(main, fg_color="transparent")
        filter_row_dates.pack(fill="x", pady=(0, 8))
        self.date_from_var = ctk.StringVar()
        self.date_to_var = ctk.StringVar()

        def build_date_field(label_text: str, variable: tk.StringVar) -> Tuple[ctk.CTkFrame, ctk.CTkEntry]:
            wrapper = ctk.CTkFrame(filter_row_dates, fg_color="transparent")
            ctk.CTkLabel(wrapper, text=label_text, font=("Arial", 12, "bold")).pack(side="left", padx=(0, 5))
            entry = ctk.CTkEntry(wrapper, width=140, placeholder_text="YYYY-MM-DD", textvariable=variable)
            entry.pack(side="left")
            entry.bind("<KeyRelease>", lambda _e: self.load_orders())
            ctk.CTkButton(
                wrapper,
                text="📅",
                width=32,
                command=lambda v=variable, e=entry: self._open_date_picker(v, e),
            ).pack(side="left", padx=(6, 0))
            return wrapper, entry

        from_field, self.date_from_entry = build_date_field("Date From", self.date_from_var)
        to_field, self.date_to_entry = build_date_field("To", self.date_to_var)
        from_field.pack(side="left", padx=5)
        to_field.pack(side="left", padx=5)

        self.order_list_frame = ctk.CTkScrollableFrame(main)
        self.order_list_frame.pack(fill="both", expand=True)

        self.load_orders()

    def load_orders(self) -> None:
        if not hasattr(self, "order_list_frame") or not self.order_list_frame.winfo_exists():
            return
        parent = self.order_list_frame
        for w in parent.winfo_children():
            w.destroy()

        month_val = self.month_filter.get()
        status_val = self.status_filter.get()
        month_num = None
        if month_val != "All":
            month_num = datetime.strptime(month_val, "%b").month

        query = (
            "SELECT o.id, o.order_code, c.name, o.date, o.status, o.total, "
            "GROUP_CONCAT(i.name, ', ') as items "
            "FROM orders o "
            "JOIN customers c ON o.customer_id = c.id "
            "LEFT JOIN order_items oi ON oi.order_id = o.id "
            "LEFT JOIN items i ON oi.item_id = i.id"
        )
        params: List = []
        filters: List[str] = []
        if status_val != "All":
            filters.append("o.status = ?")
            params.append(status_val)
        if month_num:
            filters.append("strftime('%m', o.date) = ?")
            params.append(f"{month_num:02d}")
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " GROUP BY o.id ORDER BY o.id DESC"
        rows = db.fetch(query, tuple(params))

        header = ctk.CTkFrame(parent, height=40, fg_color="transparent")
        header.pack(fill="x", pady=5)
        for text, width in [("ID", 100), ("Customer", 170), ("Date", 160), ("Status", 120), ("Total", 100)]:
            ctk.CTkLabel(header, text=text, width=width, anchor="w", font=("Arial", 12, "bold")).pack(
                side="left", padx=6
            )

        keyword = self.order_search_var.get().strip().lower()
        date_from = self._parse_date(self.date_from_var.get().strip())
        date_to = self._parse_date(self.date_to_var.get().strip())

        color_map = {"Pending": "#F57C00", "Preparing": "#1f6aa5", "Ready": THEME_COLOR, "Completed": "#757575"}
        filtered = []
        for row in rows:
            order_date = self._parse_datetime(row[3])
            if date_from and (not order_date or order_date.date() < date_from.date()):
                continue
            if date_to and (not order_date or order_date.date() > date_to.date()):
                continue
            items_text = row[6] or ""
            if keyword:
                haystack = " ".join(
                    [
                        str(row[0]),
                        row[1] or "",
                        row[2] or "",
                        row[3] or "",
                        row[4] or "",
                        items_text,
                    ]
                ).lower()
                if keyword not in haystack:
                    continue
            filtered.append((row, items_text))

        if not filtered:
            ctk.CTkLabel(parent, text="No orders found. Adjust filters or add a new order.", text_color="gray").pack(
                pady=20
            )
            return

        for row, items_text in filtered:
            status = db.normalize_status(row[4])
            display = ctk.CTkFrame(parent, fg_color=("gray90", "#333"), corner_radius=8)
            display.pack(fill="x", pady=4, padx=5)
            order_code = row[1] or db.generate_code("ORD-", row[0])
            id_label = ctk.CTkLabel(display, text=f"{order_code}\n#{row[0]}", width=100, anchor="w")
            id_label.pack(side="left", padx=6, pady=8)
            id_label.bind("<Button-1>", lambda _e, code=order_code: self.set_order_search(code))
            ctk.CTkLabel(display, text=row[2], width=170, anchor="w").pack(side="left", padx=6)
            date_lbl = ctk.CTkLabel(display, text=row[3][:16], width=160, anchor="w")
            date_lbl.pack(side="left", padx=6)
            date_lbl.bind("<Button-1>", lambda _e, date_val=row[3][:10]: self.set_date_filter(date_val))
            status_lbl = ctk.CTkLabel(
                display,
                text=status,
                text_color="white",
                fg_color=color_map.get(status, "gray"),
                corner_radius=8,
                width=120,
            )
            status_lbl.pack(side="left", padx=6)
            status_lbl.bind("<Button-1>", lambda _e, s=status: self.set_status_filter(s))
            ctk.CTkLabel(display, text=currency(row[5]), width=100, anchor="e", font=("Arial", 12, "bold")).pack(
                side="left", padx=6
            )
            ctk.CTkButton(
                display,
                text="View",
                width=60,
                height=28,
                command=lambda oid=row[0]: self.order_details_popup(oid),
            ).pack(side="right", padx=6)
            if items_text:
                ctk.CTkLabel(display, text=f"Items: {items_text}", anchor="w", text_color="gray").pack(
                    fill="x", padx=12, pady=(0, 6)
                )

    @staticmethod
    def _parse_date(value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _parse_datetime(value: str) -> Optional[datetime]:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return None

    def _open_date_picker(self, target_var: tk.StringVar, anchor_widget: tk.Widget) -> None:
        current = self._parse_date(target_var.get()) or datetime.now()
        month_var = tk.IntVar(value=current.month)
        year_var = tk.IntVar(value=current.year)

        picker = ctk.CTkToplevel(self)
        picker.title("Select Date")
        picker.resizable(False, False)
        try:
            x = anchor_widget.winfo_rootx()
            y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
            picker.geometry(f"+{x}+{y}")
        except Exception:
            picker.geometry("+200+200")
        picker.grab_set()

        header = ctk.CTkFrame(picker, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))
        title_lbl = ctk.CTkLabel(header, text="", font=("Arial", 13, "bold"))
        title_lbl.pack(side="left", expand=True)

        def change_month(delta: int) -> None:
            m = month_var.get() + delta
            y_val = year_var.get()
            if m < 1:
                m = 12
                y_val -= 1
            elif m > 12:
                m = 1
                y_val += 1
            month_var.set(m)
            year_var.set(y_val)
            render_days()

        ctk.CTkButton(header, text="◀", width=32, command=lambda: change_month(-1)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(header, text="▶", width=32, command=lambda: change_month(1)).pack(side="right", padx=(6, 0))

        grid = ctk.CTkFrame(picker, fg_color="transparent")
        grid.pack(padx=10, pady=(0, 10))

        def select_day(day: int) -> None:
            selected = datetime(year_var.get(), month_var.get(), day)
            target_var.set(selected.strftime("%Y-%m-%d"))
            picker.destroy()
            self.load_orders()

        def render_days() -> None:
            for w in grid.winfo_children():
                w.destroy()
            title_lbl.configure(text=f"{calendar.month_name[month_var.get()]} {year_var.get()}")
            for idx, name in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
                ctk.CTkLabel(grid, text=name, width=32, anchor="center").grid(row=0, column=idx, pady=(0, 6))
            start_day, days_in_month = calendar.monthrange(year_var.get(), month_var.get())
            row = 1
            col = start_day
            for day in range(1, days_in_month + 1):
                btn = ctk.CTkButton(
                    grid,
                    text=str(day),
                    width=32,
                    height=28,
                    command=lambda d=day: select_day(d),
                )
                btn.grid(row=row, column=col, padx=2, pady=2)
                col += 1
                if col > 6:
                    col = 0
                    row += 1

        render_days()

    def clear_order_filters(self) -> None:
        self.status_filter.set("All")
        self.month_filter.set("All")
        self.date_from_var.set("")
        self.date_to_var.set("")
        if hasattr(self, "date_from_entry"):
            self.date_from_entry.delete(0, "end")
        if hasattr(self, "date_to_entry"):
            self.date_to_entry.delete(0, "end")
        self.order_search_var.set("")
        self.load_orders()

    def set_status_filter(self, status: str) -> None:
        self.status_filter.set(status)
        self.load_orders()

    def set_date_filter(self, date_val: str) -> None:
        self.date_from_var.set(date_val)
        self.date_to_var.set(date_val)
        self.load_orders()

    def set_order_search(self, term: str) -> None:
        self.order_search_var.set(term)
        self.load_orders()

    def refresh_order_list(self) -> None:
        if hasattr(self, "order_list_frame") and self.order_list_frame.winfo_exists():
            self.load_orders()
        else:
            self.show_history()

    def order_details_popup(self, oid: int) -> None:
        status = db.normalize_status(db.status_for_order(oid))
        order_code = db.ensure_row_code("orders", "order_code", "ORD-", oid)
        t = ctk.CTkToplevel(self)
        t.title(f"Order {order_code} Details")
        t.geometry("640x760")
        t.grab_set()

        ctk.CTkLabel(t, text=f"Order {order_code}\nID: {oid}", font=("Arial", 20, "bold")).pack(pady=6)
        detail_frame = ctk.CTkScrollableFrame(t, fg_color="transparent", height=420)
        detail_frame.pack(fill="both", expand=True, padx=14, pady=10)
        detail_frame.grid_columnconfigure(0, weight=1)
        detail_frame.grid_columnconfigure(1, weight=1)

        items = db.fetch(
            "SELECT i.name, oi.quantity, oi.subtotal FROM order_items oi JOIN items i ON oi.item_id = i.id WHERE oi.order_id=?",
            (oid,),
        )
        total = 0
        for idx, (name, qty, subtotal) in enumerate(items):
            total += subtotal
            card = ctk.CTkFrame(detail_frame, fg_color=("gray95", "#333"), corner_radius=8)
            card.grid(row=idx // 2, column=idx % 2, padx=8, pady=6, sticky="nsew")
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=name, anchor="w", wraplength=210, font=("Arial", 13, "bold")).grid(
                row=0, column=0, sticky="w", padx=10, pady=(8, 2)
            )
            ctk.CTkLabel(card, text=f"Qty: {qty}", anchor="w").grid(row=1, column=0, sticky="w", padx=10, pady=2)
            ctk.CTkLabel(card, text=currency(subtotal), anchor="e", font=("Arial", 12, "bold")).grid(
                row=2, column=0, sticky="e", padx=10, pady=(2, 8)
            )

        ctk.CTkLabel(t, text=f"Total: {currency(total)}", font=("Arial", 15, "bold")).pack(pady=6)

        status_var = ctk.StringVar(value=status)
        status_row = ctk.CTkFrame(t, fg_color="transparent")
        status_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(status_row, text="Status", width=80).pack(side="left")
        status_menu = ctk.CTkOptionMenu(status_row, variable=status_var, values=STATUSES, width=140)
        status_menu.configure(state="normal" if status != "Completed" else "disabled")
        status_menu.pack(side="left")

        def update_status() -> None:
            current = db.normalize_status(db.status_for_order(oid))
            new_status = status_var.get()
            if current == "Completed":
                messagebox.showerror("Locked", "Completed orders cannot be edited.")
                return
            db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, oid))
            messagebox.showinfo("Updated", f"Order {order_code} status set to {new_status}")
            t.destroy()
            self.refresh_order_list()

        ctk.CTkButton(
            t,
            text="Update Status",
            fg_color=ACCENT,
            text_color="black",
            command=update_status,
            state="normal" if status != "Completed" else "disabled",
        ).pack(fill="x", padx=12, pady=6)

        ctk.CTkButton(
            t,
            text="Download PDF Invoice",
            fg_color=THEME_COLOR,
            command=lambda: self.gen_pdf(oid),
        ).pack(fill="x", padx=12, pady=4)

        ctk.CTkButton(
            t,
            text="Edit Items",
            fg_color="#1f6aa5",
            state="normal" if status != "Completed" else "disabled",
            command=lambda: [t.destroy(), self.edit_order_popup(oid)],
        ).pack(fill="x", padx=12, pady=6)

    def edit_order_popup(self, oid: Optional[int]) -> None:
        if not oid:
            return
        status = db.normalize_status(db.status_for_order(oid))
        if status == "Completed":
            messagebox.showerror("Locked", "Completed orders cannot be edited.")
            return

        order_code = db.ensure_row_code("orders", "order_code", "ORD-", oid)

        t = ctk.CTkToplevel(self)
        t.geometry("640x640")
        t.title(f"Edit Order {order_code}")
        t.grab_set()

        self.edit_cart: Dict[int, Dict] = {}
        existing = db.fetch(
            "SELECT oi.item_id, i.name, i.price, oi.quantity FROM order_items oi JOIN items i ON oi.item_id = i.id WHERE oi.order_id=?",
            (oid,),
        )
        for iid, name, price, qty in existing:
            self.edit_cart[iid] = {"name": name, "price": price, "qty": qty}

        ctk.CTkLabel(t, text=f"Editing {order_code}\nInternal ID: {oid}", font=("Arial", 20, "bold")).pack(pady=10)
        add_f = ctk.CTkFrame(t)
        add_f.pack(fill="x", padx=20, pady=10)
        all_items = db.fetch("SELECT id, name, price FROM items")
        item_map = {f"{i['name']} ({currency(i['price'])})": i for i in all_items}
        if item_map:
            sel_var = ctk.StringVar(value=list(item_map.keys())[0])
            ctk.CTkOptionMenu(add_f, variable=sel_var, values=list(item_map.keys())).pack(
                side="left", padx=10, expand=True, fill="x"
            )
        else:
            sel_var = ctk.StringVar(value="No items available")
            ctk.CTkLabel(add_f, text="Add menu items first", text_color="gray").pack(
                side="left", padx=10, expand=True, fill="x"
            )

        def add_new() -> None:
            if not item_map:
                messagebox.showerror("No Items", "Create menu items before editing orders.")
                return
            raw = item_map[sel_var.get()]
            if raw["id"] in self.edit_cart:
                self.edit_cart[raw["id"]]["qty"] += 1
            else:
                self.edit_cart[raw["id"]] = {"name": raw["name"], "price": raw["price"], "qty": 1}
            refresh_list()

        ctk.CTkButton(
            add_f,
            text="Add Item",
            width=90,
            command=add_new,
            fg_color=THEME_COLOR,
            state="normal" if item_map else "disabled",
        ).pack(side="right", padx=10)

        list_f = ctk.CTkScrollableFrame(t)
        list_f.pack(fill="both", expand=True, padx=20, pady=10)

        def change_qty(iid: int, delta: int) -> None:
            self.edit_cart[iid]["qty"] += delta
            if self.edit_cart[iid]["qty"] <= 0:
                del self.edit_cart[iid]
            refresh_list()

        def refresh_list() -> None:
            for w in list_f.winfo_children():
                w.destroy()
            grand = 0
            for iid, data in self.edit_cart.items():
                sub = data["qty"] * data["price"]
                grand += sub
                row = ctk.CTkFrame(list_f, fg_color=("gray90", "#333"))
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=data["name"], anchor="w", width=240).pack(side="left", padx=10)
                ctk.CTkLabel(row, text=currency(data["price"]), width=80).pack(side="left")
                ctrl = ctk.CTkFrame(row, fg_color="transparent")
                ctrl.pack(side="right", padx=10)
                ctk.CTkButton(ctrl, text="-", width=30, command=lambda x=iid: change_qty(x, -1)).pack(side="left")
                ctk.CTkLabel(ctrl, text=str(data["qty"]), width=30).pack(side="left")
                ctk.CTkButton(ctrl, text="+", width=30, command=lambda x=iid: change_qty(x, 1)).pack(side="left")
            lbl_total.configure(text=f"New Total: {currency(grand)}")

        lbl_total = ctk.CTkLabel(t, text="New Total: R 0.00", font=("Arial", 18, "bold"))
        lbl_total.pack(pady=8)

        def save_changes() -> None:
            if not self.edit_cart:
                messagebox.showerror("Validation", "An order must have at least one item.")
                return
            total = sum(d["qty"] * d["price"] for d in self.edit_cart.values())
            db.execute("DELETE FROM order_items WHERE order_id=?", (oid,))
            for iid, data in self.edit_cart.items():
                db.execute(
                    "INSERT INTO order_items (order_id, item_id, quantity, subtotal) VALUES (?, ?, ?, ?)",
                    (oid, iid, data["qty"], data["qty"] * data["price"]),
                )
            db.execute("UPDATE orders SET total=?, status=? WHERE id=?", (total, "Preparing", oid))
            messagebox.showinfo("Saved", f"Order {order_code} updated and moved to Preparing")
            t.destroy()
            self.refresh_order_list()

        ctk.CTkButton(t, text="SAVE CHANGES", fg_color=THEME_COLOR, height=44, command=save_changes).pack(
            fill="x", padx=20, pady=16
        )
        refresh_list()

    def gen_pdf(self, oid: Optional[int]) -> None:
        if not oid:
            return
        file = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"Invoice_Order_{oid}.pdf")
        if not file:
            return
        data = db.fetch(
            "SELECT o.id, o.order_code, c.name, o.date, o.total, c.address, c.city, c.email, o.status FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id=?",
            (oid,),
        )[0]
        order_code = data["order_code"] or db.ensure_row_code("orders", "order_code", "ORD-", oid)
        items = db.fetch(
            "SELECT i.name, oi.quantity, i.price, oi.subtotal FROM order_items oi JOIN items i ON oi.item_id = i.id WHERE oi.order_id=?",
            (oid,),
        )

        c = canvas.Canvas(file, pagesize=letter)
        c.setFillColor(colors.HexColor(THEME_COLOR))
        c.rect(0, 742, 612, 100, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(40, 800, APP_NAME)
        c.setFont("Helvetica", 12)
        c.drawString(40, 780, APP_LOCATION)
        c.drawString(40, 762, APP_TAGLINE)

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, 730, f"Invoice {order_code} (ID {data['id']})")
        c.setFont("Helvetica", 12)
        c.drawString(40, 712, f"Customer: {data['name']}")
        c.drawString(40, 694, f"Email: {data['email']}")
        c.drawString(40, 676, f"Address: {data['address'] or 'Not provided'}, {data['city'] or ''}")
        c.drawString(40, 658, f"Date: {data['date']}")
        c.drawString(40, 640, f"Status: {db.normalize_status(data['status'])}")

        y = 610
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Item")
        c.drawString(300, y, "Qty")
        c.drawString(360, y, "Price")
        c.drawString(460, y, "Total")
        c.line(40, y - 5, 540, y - 5)
        y -= 20
        c.setFont("Helvetica", 11)
        for name, qty, price, sub in items:
            c.drawString(40, y, name[:35])
            c.drawString(300, y, str(qty))
            c.drawString(360, y, currency(price))
            c.drawString(460, y, currency(sub))
            y -= 18
            if y < 120:
                c.showPage()
                y = 700
        c.line(40, y - 5, 540, y - 5)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(360, y - 24, "Grand Total:")
        c.drawString(460, y - 24, currency(data["total"]))
        c.setFont("Helvetica", 12)
        c.drawString(40, y - 48, "Thank you for your order!")
        c.drawString(40, y - 64, "For any issues or queries, email renusdelights@gmail.com")
        c.save()
        messagebox.showinfo("Saved", "Invoice PDF generated")

    # ---------- ITEMS ----------
    def show_menu(self) -> None:
        self.clear_content()
        self.add_header("Menu / Items", "Maintain your Durban favourites")
        main = ctk.CTkFrame(self.content, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=20)
        controls = ctk.CTkFrame(main, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 10))
        self.item_category_var = ctk.StringVar(value="All")
        self.item_search_var = ctk.StringVar()
        ctk.CTkLabel(controls, text="Category", font=("Arial", 12, "bold")).pack(side="left", padx=6)
        ctk.CTkOptionMenu(
            controls,
            variable=self.item_category_var,
            values=["All", "Menu", "Spice", "Snack"],
            width=120,
            command=lambda _: self.render_item_cards(),
        ).pack(side="left", padx=4)
        search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Search by name, code or category",
            textvariable=self.item_search_var,
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=6)
        search_entry.bind("<KeyRelease>", lambda _e: self.render_item_cards())
        ctk.CTkButton(controls, text="✕", width=28, command=self.clear_item_filters).pack(side="left", padx=4)
        ctk.CTkButton(
            controls,
            text="+ Add New Item",
            width=180,
            height=40,
            font=("Arial", 14, "bold"),
            command=lambda: self.item_popup(None),
            fg_color=THEME_COLOR,
        ).pack(side="right", padx=6)

        self.item_list_frame = ctk.CTkScrollableFrame(main)
        self.item_list_frame.pack(fill="both", expand=True)
        self.render_item_cards()

    def render_item_cards(self) -> None:
        if not hasattr(self, "item_list_frame") or not self.item_list_frame.winfo_exists():
            return
        for w in self.item_list_frame.winfo_children():
            w.destroy()
        cat = self.item_category_var.get()
        keyword = self.item_search_var.get().strip().lower()
        items = db.fetch("SELECT id, name, category, price, stock, item_code FROM items ORDER BY id DESC")
        found = False
        for r in items:
            if cat != "All" and r["category"] != cat:
                continue
            code = r["item_code"] or db.generate_code("ITM-", r["id"])
            haystack = f"{r['name']} {r['category']} {code}".lower()
            if keyword and keyword not in haystack:
                continue
            found = True
            card = ctk.CTkFrame(self.item_list_frame, fg_color=("gray90", "#333"), corner_radius=8)
            card.pack(fill="x", pady=5, padx=5)
            ctk.CTkLabel(card, text=f"{r['name']}\n{code} (ID {r['id']})", font=("Arial", 14, "bold"), width=250, anchor="w").pack(
                side="left", padx=20, pady=15
            )
            ctk.CTkLabel(card, text=r["category"], width=100, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(card, text=currency(r["price"]), font=("Arial", 14, "bold"), width=100, anchor="w").pack(
                side="left", padx=10
            )
            ctk.CTkLabel(card, text=f"Stock: {r['stock']}").pack(side="left", padx=10)
            ctk.CTkButton(card, text="Delete", fg_color="#E53935", width=70, command=lambda i=r["id"]: self.del_item(i)).pack(
                side="right", padx=10
            )
            ctk.CTkButton(
                card,
                text="Edit",
                fg_color=ACCENT,
                text_color="black",
                width=70,
                command=lambda i=r["id"]: self.item_popup(i),
            ).pack(side="right", padx=5)
        if not found:
            ctk.CTkLabel(self.item_list_frame, text="No items match your filters.", text_color="gray").pack(pady=16)

    def clear_item_filters(self) -> None:
        self.item_category_var.set("All")
        self.item_search_var.set("")
        self.render_item_cards()

    def item_popup(self, iid: Optional[int]) -> None:
        t = ctk.CTkToplevel(self)
        t.geometry("420x620")
        t.title("Item Details")
        t.grab_set()

        vcmd_float = (t.register(validate_numeric_input), "%d", "%P")
        vcmd_int = (t.register(validate_int_input), "%d", "%P")

        code_label = ctk.CTkLabel(t, text="Item code will be generated on save", text_color="gray")
        code_label.pack(pady=(8, 2))
        ctk.CTkLabel(t, text="Name").pack(pady=6)
        name_e = ctk.CTkEntry(t)
        name_e.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Category").pack(pady=6)
        cat_var = ctk.StringVar(value="Menu")
        ctk.CTkOptionMenu(t, variable=cat_var, values=["Menu", "Spice", "Snack"]).pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Price (R)").pack(pady=6)
        price_e = ctk.CTkEntry(t, validate="key", validatecommand=vcmd_float)
        price_e.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Stock").pack(pady=6)
        stock_e = ctk.CTkEntry(t, validate="key", validatecommand=vcmd_int)
        stock_e.pack(fill="x", padx=20)

        img_frame = ctk.CTkFrame(t, fg_color="transparent")
        img_frame.pack(pady=8, padx=20, fill="x")
        ctk.CTkLabel(img_frame, text="Image").pack(anchor="w")
        preview_label = ctk.CTkLabel(img_frame, text="No image", anchor="w")
        preview_label.pack(fill="x", pady=4)
        selected_image_path = os.path.abspath("assets/placeholder.png")

        def set_preview(path: str) -> None:
            nonlocal selected_image_path
            selected_image_path = path
            try:
                img = ctk.CTkImage(Image.open(path), size=(80, 80))
                preview_label.configure(text="", image=img)
                preview_label.image = img
            except Exception:
                preview_label.configure(text=os.path.basename(path), image=None)

        def upload_image() -> None:
            file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.gif")])
            if not file_path:
                return
            try:
                dest_dir = "assets"
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, os.path.basename(file_path))
                base, ext = os.path.splitext(dest_path)
                counter = 1
                while os.path.exists(dest_path):
                    dest_path = f"{base}_{counter}{ext}"
                    counter += 1
                shutil.copyfile(file_path, dest_path)
                set_preview(os.path.abspath(dest_path))
            except Exception as exc:
                messagebox.showerror("Image", f"Failed to add image: {exc}")

        ctk.CTkButton(img_frame, text="Upload Image", fg_color=THEME_COLOR, command=upload_image).pack(fill="x")

        if iid:
            d = db.fetch("SELECT name, category, price, stock, image_path, item_code FROM items WHERE id=?", (iid,))[0]
            name_e.insert(0, d[0])
            cat_var.set(d[1])
            price_e.insert(0, str(d[2]))
            stock_e.insert(0, str(d[3]))
            code_label.configure(text=f"Item Code: {d['item_code'] or db.generate_code('ITM-', iid)} | ID: {iid}")
            if d[4]:
                set_preview(d[4])
        else:
            stock_e.insert(0, "50")
            set_preview(selected_image_path)

        def save() -> None:
            name = name_e.get().strip()
            price = ensure_positive_number(price_e.get())
            stock_val = ensure_positive_number(stock_e.get(), allow_zero=True)
            if not name:
                messagebox.showerror("Validation", "Name is required")
                return
            if price is None:
                messagebox.showerror("Validation", "Enter a valid price")
                return
            if stock_val is None:
                messagebox.showerror("Validation", "Enter a valid stock number")
                return
            path = selected_image_path or os.path.abspath("assets/placeholder.png")
            if iid:
                db.execute(
                    "UPDATE items SET name=?, category=?, price=?, stock=?, image_path=? WHERE id=?",
                    (name, cat_var.get(), price, int(stock_val), path, iid),
                )
            else:
                new_id = db.execute(
                    "INSERT INTO items (name, category, price, stock, image_path) VALUES (?, ?, ?, ?, ?)",
                    (name, cat_var.get(), price, int(stock_val), path),
                )
                db.ensure_row_code("items", "item_code", "ITM-", new_id)
            t.destroy()
            self.show_menu()

        ctk.CTkButton(t, text="Save Item", command=save, fg_color=THEME_COLOR).pack(pady=20, fill="x", padx=20)

    def del_item(self, iid: int) -> None:
        if messagebox.askyesno("Confirm", "Delete item?"):
            db.execute("DELETE FROM items WHERE id=?", (iid,))
            self.show_menu()

    # ---------- CUSTOMERS ----------
    def show_customers(self) -> None:
        self.clear_content()
        self.add_header("Customers", "Manage your South African foodies")
        main = ctk.CTkFrame(self.content, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=20)
        controls = ctk.CTkFrame(main, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 10))
        self.customer_search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Search by name, email, city or phone",
            textvariable=self.customer_search_var,
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=6)
        search_entry.bind("<KeyRelease>", lambda _e: self.render_customer_cards())
        ctk.CTkButton(controls, text="✕", width=28, command=self.clear_customer_filters).pack(side="left", padx=4)
        ctk.CTkButton(
            controls,
            text="+ Add Customer",
            width=200,
            height=40,
            font=("Arial", 14, "bold"),
            command=lambda: self.cust_popup(None),
            fg_color=THEME_COLOR,
        ).pack(side="right", padx=6)
        self.customer_list_frame = ctk.CTkScrollableFrame(main)
        self.customer_list_frame.pack(fill="both", expand=True)
        self.render_customer_cards()

    def render_customer_cards(self) -> None:
        if not hasattr(self, "customer_list_frame") or not self.customer_list_frame.winfo_exists():
            return
        for w in self.customer_list_frame.winfo_children():
            w.destroy()
        keyword = (self.customer_search_var.get() if hasattr(self, "customer_search_var") else "").strip().lower()
        records = db.fetch("SELECT id, name, email, address, city, phone FROM customers ORDER BY name")
        found = False
        for r in records:
            haystack = f"{r['name']} {r['email']} {r['city'] or ''} {r['phone'] or ''} {r['address'] or ''}".lower()
            if keyword and keyword not in haystack:
                continue
            found = True
            card = ctk.CTkFrame(self.customer_list_frame, fg_color=("gray90", "#333"), corner_radius=8)
            card.pack(fill="x", pady=5, padx=5)
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", padx=20, pady=10)
            ctk.CTkLabel(info, text=f"{r['name']} (ID {r['id']})", font=("Arial", 14, "bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=r["email"], font=("Arial", 12), text_color="gray", anchor="w").pack(anchor="w")
            addr = ctk.CTkFrame(card, fg_color="transparent")
            addr.pack(side="left", padx=20)
            ctk.CTkLabel(addr, text=r["city"] or "No City", font=("Arial", 12, "bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(addr, text=r["address"] or "No Address", font=("Arial", 11), text_color="gray", anchor="w").pack(
                anchor="w"
            )
            ctk.CTkLabel(addr, text=r["phone"] or "", font=("Arial", 11)).pack(anchor="w")
            ctk.CTkButton(card, text="Delete", fg_color="#E53935", width=70, command=lambda i=r["id"]: self.del_cust(i)).pack(
                side="right", padx=10
            )
            ctk.CTkButton(
                card,
                text="Edit",
                fg_color=ACCENT,
                text_color="black",
                width=70,
                command=lambda i=r["id"]: self.cust_popup(i),
            ).pack(side="right", padx=5)
        if not found:
            ctk.CTkLabel(self.customer_list_frame, text="No customers match your filters.", text_color="gray").pack(
                pady=16
            )

    def clear_customer_filters(self) -> None:
        if hasattr(self, "customer_search_var"):
            self.customer_search_var.set("")
        self.render_customer_cards()

    def cust_popup(self, cid: Optional[int]) -> None:
        t = ctk.CTkToplevel(self)
        t.geometry("360x480")
        t.title("Customer Details")
        t.grab_set()

        ctk.CTkLabel(t, text="Name").pack(pady=4)
        e1 = ctk.CTkEntry(t)
        e1.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Email").pack(pady=4)
        e2 = ctk.CTkEntry(t)
        e2.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Address").pack(pady=4)
        e3 = ctk.CTkEntry(t)
        e3.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="City").pack(pady=4)
        e4 = ctk.CTkEntry(t)
        e4.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Phone").pack(pady=4)
        e5 = ctk.CTkEntry(t)
        e5.pack(fill="x", padx=20)

        if cid:
            d = db.fetch("SELECT name, email, address, city, phone FROM customers WHERE id=?", (cid,))[0]
            e1.insert(0, d[0])
            e2.insert(0, d[1])
            e3.insert(0, d[2] or "")
            e4.insert(0, d[3] or "")
            e5.insert(0, d[4] or "")

        def save() -> None:
            name = e1.get().strip()
            email = e2.get().strip()
            if not name or not email:
                messagebox.showerror("Validation", "Name and email are required")
                return
            if not valid_email(email):
                messagebox.showerror("Validation", "Enter a valid email address")
                return
            if e4.get().strip() and not validate_city_name(e4.get().strip()):
                messagebox.showerror("Validation", "Enter a valid city name")
                return
            if e5.get().strip() and not validate_phone(e5.get().strip()):
                messagebox.showerror("Validation", "Enter a valid phone number")
                return
            if cid:
                db.execute(
                    "UPDATE customers SET name=?, email=?, address=?, city=?, phone=? WHERE id=?",
                    (name, email, e3.get().strip(), e4.get().strip(), e5.get().strip(), cid),
                )
            else:
                db.execute(
                    "INSERT INTO customers (name, email, address, city, phone) VALUES (?, ?, ?, ?, ?)",
                    (name, email, e3.get().strip(), e4.get().strip(), e5.get().strip()),
                )
            t.destroy()
            self.show_customers()

        ctk.CTkButton(t, text="Save", command=save, fg_color=THEME_COLOR).pack(pady=20, fill="x", padx=20)

    def del_cust(self, cid: int) -> None:
        if messagebox.askyesno("Confirm", "Delete customer?"):
            db.execute("DELETE FROM customers WHERE id=?", (cid,))
            self.show_customers()

    # ---------- USERS ----------
    def show_users(self) -> None:
        self.clear_content()
        self.add_header("Users", "Manage staff access")
        main = ctk.CTkFrame(self.content, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=20)
        controls = ctk.CTkFrame(main, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 10))
        self.user_role_filter = ctk.StringVar(value="All")
        self.user_search_var = ctk.StringVar()
        ctk.CTkLabel(controls, text="Role", font=("Arial", 12, "bold")).pack(side="left", padx=6)
        roles = ["All", "Owner", "Manager", "Cashier", "Kitchen"]
        ctk.CTkOptionMenu(
            controls,
            variable=self.user_role_filter,
            values=roles,
            width=140,
            command=lambda _: self.render_user_cards(),
        ).pack(side="left", padx=4)
        search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Search by name, code, email or phone",
            textvariable=self.user_search_var,
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=6)
        search_entry.bind("<KeyRelease>", lambda _e: self.render_user_cards())
        ctk.CTkButton(controls, text="✕", width=28, command=self.clear_user_filters).pack(side="left", padx=4)
        ctk.CTkButton(
            controls,
            text="+ Add User",
            width=200,
            height=40,
            font=("Arial", 14, "bold"),
            command=lambda: self.user_popup(None),
            fg_color=THEME_COLOR,
        ).pack(side="right", padx=6)
        self.user_list_frame = ctk.CTkScrollableFrame(main)
        self.user_list_frame.pack(fill="both", expand=True)
        self.render_user_cards()

    def render_user_cards(self) -> None:
        if not hasattr(self, "user_list_frame") or not self.user_list_frame.winfo_exists():
            return
        for w in self.user_list_frame.winfo_children():
            w.destroy()
        role_filter = self.user_role_filter.get() if hasattr(self, "user_role_filter") else "All"
        keyword = (self.user_search_var.get() if hasattr(self, "user_search_var") else "").strip().lower()
        users = db.fetch("SELECT id, full_name, role, email, phone, user_code FROM users ORDER BY id DESC")
        found = False
        for r in users:
            if role_filter != "All" and r["role"] != role_filter:
                continue
            code = r["user_code"] or db.generate_code("USR-", r["id"])
            haystack = f"{r['full_name']} {code} {r['email']} {r['phone'] or ''} {r['role']}".lower()
            if keyword and keyword not in haystack:
                continue
            found = True
            card = ctk.CTkFrame(self.user_list_frame, fg_color=("gray90", "#333"), corner_radius=8)
            card.pack(fill="x", pady=5, padx=5)
            ctk.CTkLabel(card, text=f"{r['full_name']}\n{code} (ID {r['id']})", font=("Arial", 14, "bold"), width=220, anchor="w").pack(
                side="left", padx=20, pady=12
            )
            ctk.CTkLabel(card, text=r["role"], width=120, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(card, text=r["email"], width=220, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(card, text=r["phone"] or "").pack(side="left", padx=10)
            ctk.CTkButton(card, text="Delete", fg_color="#E53935", width=70, command=lambda i=r["id"]: self.del_user(i)).pack(
                side="right", padx=10
            )
            ctk.CTkButton(
                card,
                text="Edit",
                fg_color=ACCENT,
                text_color="black",
                width=70,
                command=lambda i=r["id"]: self.user_popup(i),
            ).pack(side="right", padx=5)
        if not found:
            ctk.CTkLabel(self.user_list_frame, text="No users match your filters.", text_color="gray").pack(pady=16)

    def clear_user_filters(self) -> None:
        if hasattr(self, "user_role_filter"):
            self.user_role_filter.set("All")
        if hasattr(self, "user_search_var"):
            self.user_search_var.set("")
        self.render_user_cards()

    def user_popup(self, uid: Optional[int]) -> None:
        t = ctk.CTkToplevel(self)
        t.geometry("360x420")
        t.title("User Details")
        t.grab_set()

        code_label = ctk.CTkLabel(t, text="User code will be generated on save", text_color="gray")
        code_label.pack(pady=(8, 2))
        ctk.CTkLabel(t, text="Full Name").pack(pady=4)
        e1 = ctk.CTkEntry(t)
        e1.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Surname").pack(pady=4)
        e_surname = ctk.CTkEntry(t)
        e_surname.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Role").pack(pady=4)
        role_var = ctk.StringVar(value="Manager")
        ctk.CTkOptionMenu(t, variable=role_var, values=["Owner", "Manager", "Cashier", "Kitchen"]).pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Email").pack(pady=4)
        e3 = ctk.CTkEntry(t)
        e3.pack(fill="x", padx=20)
        ctk.CTkLabel(t, text="Phone").pack(pady=4)
        e4 = ctk.CTkEntry(t)
        e4.pack(fill="x", padx=20)

        if uid:
            d = db.fetch("SELECT full_name, surname, role, email, phone, user_code FROM users WHERE id=?", (uid,))[0]
            e1.insert(0, d[0])
            e_surname.insert(0, d[1] or "")
            role_var.set(d[2])
            e3.insert(0, d[3])
            e4.insert(0, d[4] or "")
            code_label.configure(text=f"User Code: {d['user_code'] or db.generate_code('USR-', uid)} | ID: {uid}")

        def save() -> None:
            name = e1.get().strip()
            surname = e_surname.get().strip()
            email = e3.get().strip()
            if not name or not surname or not email:
                messagebox.showerror("Validation", "Name, surname and email are required")
                return
            if not valid_email(email):
                messagebox.showerror("Validation", "Enter a valid email address")
                return
            if e4.get().strip() and not validate_phone(e4.get().strip()):
                messagebox.showerror("Validation", "Enter a valid phone number")
                return
            full = f"{name} {surname}".strip()
            if uid:
                db.execute(
                    "UPDATE users SET full_name=?, surname=?, role=?, email=?, phone=? WHERE id=?",
                    (full, surname, role_var.get(), email, e4.get().strip(), uid),
                )
            else:
                new_uid = db.execute(
                    "INSERT INTO users (full_name, surname, role, email, phone) VALUES (?, ?, ?, ?, ?)",
                    (full, surname, role_var.get(), email, e4.get().strip()),
                )
                db.ensure_row_code("users", "user_code", "USR-", new_uid)
            t.destroy()
            self.show_users()

        ctk.CTkButton(t, text="Save User", command=save, fg_color=THEME_COLOR).pack(pady=20, fill="x", padx=20)

    def del_user(self, uid: int) -> None:
        if messagebox.askyesno("Confirm", "Delete user?"):
            db.execute("DELETE FROM users WHERE id=?", (uid,))
            self.show_users()

    # ---------- REPORTS ----------
    def show_reports(self) -> None:
        self.clear_content()
        self.add_header("Reports", "Export revenue and order performance")

        wrap = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=20, pady=20)

        filter_row = ctk.CTkFrame(wrap, fg_color=("white", "#2b2b2b"))
        filter_row.pack(fill="x", pady=10)
        ctk.CTkLabel(filter_row, text="Month", width=80).pack(side="left", padx=10, pady=12)
        self.report_month = ctk.StringVar(value="All")
        month_values = ["All"] + [datetime(2024, m, 1).strftime("%B") for m in range(1, 13)]
        ctk.CTkOptionMenu(filter_row, variable=self.report_month, values=month_values, width=160,
                          command=lambda _=None: self.refresh_report()).pack(side="left", padx=6)
        ctk.CTkLabel(filter_row, text="Year", width=60).pack(side="left")
        current_year = datetime.now().year
        years = [str(y) for y in range(current_year - 3, current_year + 1)]
        self.report_year = ctk.StringVar(value=str(current_year))
        ctk.CTkOptionMenu(filter_row, variable=self.report_year, values=years, width=120,
                          command=lambda _=None: self.refresh_report()).pack(side="left", padx=6)
        ctk.CTkButton(
            filter_row,
            text="Download PDF",
            fg_color=THEME_COLOR,
            command=self.download_report_pdf,
        ).pack(side="right", padx=10)

        self.report_body = ctk.CTkFrame(wrap, fg_color="transparent")
        self.report_body.pack(fill="both", expand=True, pady=10)
        self.refresh_report()

    def refresh_report(self) -> None:
        for w in self.report_body.winfo_children():
            w.destroy()
        month_val = self.report_month.get()
        year_val = int(self.report_year.get())
        month_num = None
        if month_val != "All":
            month_num = datetime.strptime(month_val, "%B").month
        report = db.monthly_report(year_val, month_num)
        cards = ctk.CTkFrame(self.report_body, fg_color="transparent")
        cards.pack(fill="x", pady=8)
        for title, value in [
            ("Revenue", currency(report["total_revenue"])),
            ("Orders", str(len(report["orders"]))),
            ("Completed", str(report["status_counts"].get("Completed", 0))),
        ]:
            card = ctk.CTkFrame(cards, fg_color=("white", "#2b2b2b"), corner_radius=12)
            card.pack(side="left", expand=True, fill="x", padx=6)
            ctk.CTkLabel(card, text=title, font=("Arial", 13), text_color="gray").pack(pady=(12, 2))
            ctk.CTkLabel(card, text=value, font=("Arial", 20, "bold")).pack(pady=(0, 12))

        detail = ctk.CTkFrame(self.report_body, fg_color=("white", "#2b2b2b"), corner_radius=12)
        detail.pack(fill="both", expand=True, pady=10)
        ctk.CTkLabel(detail, text="Top Items", font=("Arial", 15, "bold")).pack(anchor="w", padx=14, pady=8)
        if report["top_items"]:
            for name, qty in report["top_items"]:
                row = ctk.CTkFrame(detail, fg_color="transparent")
                row.pack(fill="x", padx=14, pady=2)
                ctk.CTkLabel(row, text=name, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=f"Qty: {qty}", anchor="e").pack(side="right")
        else:
            ctk.CTkLabel(detail, text="No sales in this period", text_color="gray").pack(pady=10)

        status_frame = ctk.CTkFrame(self.report_body, fg_color="transparent")
        status_frame.pack(fill="x", pady=6)
        for s in STATUSES:
            val = report["status_counts"].get(s, 0)
            chip = ctk.CTkFrame(status_frame, fg_color=("white", "#2b2b2b"), corner_radius=12)
            chip.pack(side="left", expand=True, fill="x", padx=5)
            ctk.CTkLabel(chip, text=s, font=("Arial", 12, "bold")).pack(pady=(8, 2))
            ctk.CTkLabel(chip, text=str(val), font=("Arial", 14)).pack(pady=(0, 8))

        self.current_report = report

    def download_report_pdf(self) -> None:
        report = getattr(self, "current_report", None)
        if not report:
            return
        month_val = self.report_month.get()
        year_val = self.report_year.get()
        period = f"{month_val} {year_val}" if month_val != "All" else f"Year {year_val}"
        file = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"Report_{period.replace(' ', '_')}.pdf")
        if not file:
            return
        c = canvas.Canvas(file, pagesize=A4)
        width, height = A4
        c.setFillColor(colors.HexColor(THEME_COLOR))
        c.rect(0, height - 70, width, 70, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(20 * mm, height - 30, f"{APP_NAME} Report")
        c.setFont("Helvetica", 12)
        c.drawString(20 * mm, height - 48, f"Period: {period}")
        c.drawString(120 * mm, height - 48, APP_LOCATION)

        c.setFillColor(colors.black)
        y = height - 90
        c.setFont("Helvetica-Bold", 14)
        c.drawString(20 * mm, y, "Summary")
        y -= 14
        c.setFont("Helvetica", 12)
        c.drawString(20 * mm, y, f"Revenue: {currency(report['total_revenue'])}")
        y -= 16
        c.drawString(20 * mm, y, f"Orders: {len(report['orders'])}")
        y -= 16
        for s in STATUSES:
            c.drawString(20 * mm, y, f"{s}: {report['status_counts'].get(s, 0)}")
            y -= 16

        y -= 6
        c.setFont("Helvetica-Bold", 14)
        c.drawString(20 * mm, y, "Top Items")
        y -= 14
        c.setFont("Helvetica", 12)
        for name, qty in report["top_items"] or []:
            c.drawString(20 * mm, y, f"{name} - {qty} sold")
            y -= 14
        c.save()
        messagebox.showinfo("Saved", "Report PDF generated")


if __name__ == "__main__":
    app = RenusApp()
    app.mainloop()
