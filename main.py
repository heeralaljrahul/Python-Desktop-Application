import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import shutil
import random
import re
import sqlite3
import calendar
import logging
import weakref
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from functools import lru_cache

# Chart libraries
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('renus_app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== APP CONFIGURATION ====================
APP_NAME = "RENUS AUTHENTIC DELIGHTS"
APP_LOCATION = "Pretoria, South Africa"
APP_TAGLINE = "Gourmet Pretoria curries & spices"
STATUSES = ["Pending", "Preparing", "Ready", "Completed"]

# ==================== THEME CONSTANTS ====================
class Theme:
    """Centralized theme configuration for consistent styling"""
    # Primary colors
    PRIMARY = "#2CC985"
    ACCENT = "#FBC02D"
    ERROR = "#E53935"
    WARNING = "#F57C00"
    INFO = "#1f6aa5"
    SUCCESS = "#2CC985"
    MUTED = "#757575"

    # Status colors
    STATUS_COLORS = {
        "Pending": "#F57C00",
        "Preparing": "#1f6aa5",
        "Ready": "#2CC985",
        "Completed": "#757575"
    }

    # Card colors (light, dark)
    CARD_BG = ("gray90", "#333")
    CARD_BG_ALT = ("gray95", "#333")
    HEADER_BG = ("white", "#1f1f1f")
    CONTENT_BG = ("gray92", "gray10")

    # Spacing
    PADDING_SM = 6
    PADDING_MD = 12
    PADDING_LG = 20

    # Font sizes
    FONT_SM = 10
    FONT_MD = 12
    FONT_LG = 14
    FONT_XL = 18
    FONT_XXL = 26

    # Dimensions
    SIDEBAR_WIDTH = 230
    BUTTON_HEIGHT = 42
    CARD_RADIUS = 8

# Backward compatibility aliases
THEME_COLOR = Theme.PRIMARY
ACCENT = Theme.ACCENT

# ==================== IMAGE CACHE ====================
class ImageCache:
    """Cache for PIL images to improve performance"""
    _cache: Dict[str, Any] = {}
    _max_size = 100

    @classmethod
    def get(cls, path: str, size: Tuple[int, int] = (70, 70)) -> Optional[ctk.CTkImage]:
        """Get cached image or load and cache it"""
        cache_key = f"{path}_{size[0]}x{size[1]}"

        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            if not os.path.exists(path):
                return None
            pil_img = Image.open(path)
            ctk_img = ctk.CTkImage(pil_img, size=size)

            # Evict oldest if cache is full
            if len(cls._cache) >= cls._max_size:
                oldest_key = next(iter(cls._cache))
                del cls._cache[oldest_key]

            cls._cache[cache_key] = ctk_img
            return ctk_img
        except Exception as e:
            logger.warning(f"Failed to load image {path}: {e}")
            return None

    @classmethod
    def clear(cls) -> None:
        """Clear the image cache"""
        cls._cache.clear()

# ==================== DEBOUNCE UTILITY ====================
class Debouncer:
    """Debounce utility for search inputs"""
    def __init__(self, widget: tk.Widget, delay_ms: int = 300):
        self.widget = widget
        self.delay_ms = delay_ms
        self._job_id: Optional[str] = None

    def debounce(self, callback) -> None:
        """Cancel previous job and schedule new one"""
        if self._job_id:
            self.widget.after_cancel(self._job_id)
        self._job_id = self.widget.after(self.delay_ms, callback)


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")


def currency(val: float) -> str:
    return f"R {val:,.2f}"


# ==================== VALIDATION FUNCTIONS ====================
class Validators:
    """Centralized validation utilities with error messages"""

    @staticmethod
    def email(email: str) -> Tuple[bool, str]:
        """Validate email address"""
        if not email:
            return False, "Email is required"
        email = email.strip()
        if len(email) > 254:
            return False, "Email is too long"
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, email):
            return False, "Enter a valid email address"
        return True, ""

    @staticmethod
    def phone(phone: str) -> Tuple[bool, str]:
        """Validate phone number (supports SA formats)"""
        if not phone:
            return True, ""  # Phone is optional
        phone = phone.strip()
        # Remove spaces and hyphens for validation
        clean_phone = re.sub(r'[\s-]', '', phone)
        if not re.match(r'^\+?[0-9]{7,15}$', clean_phone):
            return False, "Enter a valid phone number (7-15 digits)"
        return True, ""

    @staticmethod
    def city(city: str) -> Tuple[bool, str]:
        """Validate city name"""
        if not city:
            return True, ""  # City is optional
        city = city.strip()
        if len(city) < 2:
            return False, "City name is too short"
        if len(city) > 100:
            return False, "City name is too long"
        if not re.match(r"^[A-Za-z][A-Za-z\s\-'.,]*$", city):
            return False, "City name contains invalid characters"
        return True, ""

    @staticmethod
    def name(name: str, field_name: str = "Name") -> Tuple[bool, str]:
        """Validate a name field"""
        if not name:
            return False, f"{field_name} is required"
        name = name.strip()
        if len(name) < 2:
            return False, f"{field_name} is too short"
        if len(name) > 100:
            return False, f"{field_name} is too long"
        return True, ""

    @staticmethod
    def price(value: str) -> Tuple[bool, str, Optional[float]]:
        """Validate price value"""
        if not value:
            return False, "Price is required", None
        try:
            num = float(value)
            if num < 0:
                return False, "Price cannot be negative", None
            if num == 0:
                return False, "Price must be greater than 0", None
            if num > 999999:
                return False, "Price is too high", None
            return True, "", num
        except (TypeError, ValueError):
            return False, "Enter a valid price", None

    @staticmethod
    def stock(value: str, allow_zero: bool = True) -> Tuple[bool, str, Optional[int]]:
        """Validate stock quantity"""
        if not value:
            return False, "Stock quantity is required", None
        try:
            num = int(float(value))
            if num < 0:
                return False, "Stock cannot be negative", None
            if not allow_zero and num == 0:
                return False, "Stock must be greater than 0", None
            if num > 999999:
                return False, "Stock quantity is too high", None
            return True, "", num
        except (TypeError, ValueError):
            return False, "Enter a valid stock number", None

    @staticmethod
    def quantity(value: int, available_stock: int, item_name: str = "item") -> Tuple[bool, str]:
        """Validate order quantity against available stock"""
        if value <= 0:
            return False, f"Quantity must be at least 1"
        if value > available_stock:
            return False, f"Only {available_stock} of '{item_name}' available in stock"
        return True, ""


# Backward compatible functions
def valid_email(email: str) -> bool:
    valid, _ = Validators.email(email)
    return valid


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
    if not value_if_allowed:
        return True
    try:
        # Allow partial input like "1." or ".5"
        if value_if_allowed in (".", "-", "-.", "-."):
            return True
        float(value_if_allowed)
        return True
    except ValueError:
        return False


def validate_int_input(action: str, value_if_allowed: str) -> bool:
    if action == "0":
        return True
    if not value_if_allowed:
        return True
    return value_if_allowed.isdigit()


def validate_city_name(city: str) -> bool:
    valid, _ = Validators.city(city)
    return valid


def validate_phone(phone: str) -> bool:
    valid, _ = Validators.phone(phone)
    return valid


class DBManager:
    def __init__(self, db_name: str = "renus_system.db"):
        try:
            self.conn = sqlite3.connect(db_name, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            # Enable foreign key constraints
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.cursor = self.conn.cursor()
            self.init_db()
            logger.info(f"Database initialized: {db_name}")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise

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
        try:
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Database fetch error: {e}, Query: {query[:100]}")
            raise

    def execute(self, query: str, params: Tuple = ()) -> int:
        try:
            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database execute error: {e}, Query: {query[:100]}")
            self.conn.rollback()
            raise

    def execute_transaction(self, operations: List[Tuple[str, Tuple]]) -> bool:
        """Execute multiple operations in a single transaction"""
        try:
            for query, params in operations:
                self.cursor.execute(query, params)
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Transaction error: {e}")
            self.conn.rollback()
            raise

    def is_email_unique(self, email: str, table: str, exclude_id: Optional[int] = None) -> bool:
        """Check if email is unique in the specified table"""
        if table not in ("customers", "users"):
            raise ValueError(f"Invalid table: {table}")
        query = f"SELECT id FROM {table} WHERE LOWER(email) = LOWER(?)"
        params: List = [email]
        if exclude_id:
            query += " AND id != ?"
            params.append(exclude_id)
        result = self.fetch(query, tuple(params))
        return len(result) == 0

    def check_stock_availability(self, cart: Dict[int, Dict]) -> List[Tuple[str, int, int]]:
        """Check stock availability for items in cart. Returns list of (item_name, requested, available) for insufficient stock"""
        insufficient = []
        for item_id, data in cart.items():
            result = self.fetch("SELECT name, stock FROM items WHERE id = ?", (item_id,))
            if result:
                name, stock = result[0]["name"], result[0]["stock"]
                if data["qty"] > stock:
                    insufficient.append((name, data["qty"], stock))
        return insufficient

    def get_item_stock(self, item_id: int) -> Optional[int]:
        """Get current stock for an item"""
        result = self.fetch("SELECT stock FROM items WHERE id = ?", (item_id,))
        return result[0]["stock"] if result else None

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
        self.after(100, self._maximize_window)
        self.logo_img = ctk.CTkImage(Image.open("assets/logo.png"), size=(44, 44))
        self.cart: Dict[int, Dict] = {}
        self.date_picker_win: Optional[ctk.CTkToplevel] = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.create_sidebar()
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "gray10"))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.show_new_order()

    def _maximize_window(self) -> None:
        try:
            self.state("zoomed")
        except tk.TclError:
            self.attributes("-fullscreen", True)

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
        split.grid_columnconfigure(0, weight=1, uniform="split")
        split.grid_columnconfigure(1, weight=1, uniform="split")
        split.grid_rowconfigure(0, weight=1)

        # Left: Menu grid
        menu_frame = ctk.CTkFrame(split, fg_color="transparent")
        menu_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        filter_row = ctk.CTkFrame(menu_frame, fg_color="transparent")
        filter_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(filter_row, text="Filter", font=("Arial", Theme.FONT_LG, "bold")).pack(side="left", padx=8)
        self.cat_var = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(filter_row, variable=self.cat_var, values=["All", "Menu", "Spice", "Snack"], width=120,
                          command=lambda _: self.load_grid(scroll)).pack(side="left", padx=8)
        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(filter_row, placeholder_text="Search item", textvariable=self.search_var)
        search_entry.pack(side="left", padx=8, fill="x", expand=True)

        # Debounced search for better performance
        menu_debouncer = Debouncer(search_entry, 250)
        search_entry.bind("<KeyRelease>", lambda _e: menu_debouncer.debounce(lambda: self.load_grid(scroll)))

        ctk.CTkButton(filter_row, text="✕", width=28, command=lambda: self.clear_menu_filter(scroll)).pack(side="left", padx=4)

        scroll = ctk.CTkScrollableFrame(menu_frame)
        scroll.pack(fill="both", expand=True)
        self.load_grid(scroll)

        # Right: Cart
        cart = ctk.CTkFrame(split, fg_color=("white", "#2b2b2b"))
        cart.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        cart.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(cart, text="Current Order", font=("Arial", 18, "bold")).pack(pady=15)

        custs = db.fetch("SELECT id, name FROM customers ORDER BY name")
        customer_values = [f"{c['id']} - {c['name']}" for c in custs]
        self.cust_var = ctk.StringVar(value=customer_values[0] if customer_values else "")
        self.all_customer_values = customer_values
        search_holder = ctk.CTkFrame(cart, fg_color="transparent")
        search_holder.pack(fill="x", padx=20)
        self.customer_search_var = ctk.StringVar()
        search_box = ctk.CTkEntry(
            search_holder,
            placeholder_text="Search customer",
            textvariable=self.customer_search_var,
        )
        search_box.pack(side="left", fill="x", expand=True, pady=(0, 6))
        search_box.bind("<KeyRelease>", lambda _e: self.filter_customers())
        ctk.CTkButton(search_holder, text="✕", width=32, command=self.clear_customer_search).pack(
            side="left", padx=(6, 0), pady=(0, 6)
        )

        self.customer_box = ctk.CTkComboBox(
            cart,
            variable=self.cust_var,
            values=customer_values or ["No customers"],
            state="readonly" if customer_values else "disabled",
        )
        self.customer_box.pack(fill="x", padx=20)

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

    def filter_customers(self) -> None:
        if not hasattr(self, "customer_box"):
            return
        query = self.customer_search_var.get().lower().strip()
        if not self.all_customer_values:
            self.customer_box.configure(values=["No customers"], state="disabled")
            self.cust_var.set("")
            return
        filtered = [v for v in self.all_customer_values if query in v.lower()]
        if filtered:
            self.customer_box.configure(values=filtered, state="readonly")
            current = self.cust_var.get()
            if current in filtered:
                self.cust_var.set(current)
            elif current:
                self.cust_var.set(filtered[0])
            else:
                self.cust_var.set("")
        else:
            self.customer_box.configure(values=["No matches"], state="disabled")
            self.cust_var.set("")

    def clear_customer_search(self) -> None:
        if not hasattr(self, "customer_box"):
            return
        self.customer_search_var.set("")
        if self.all_customer_values:
            self.customer_box.configure(values=self.all_customer_values, state="readonly")
            self.cust_var.set("")
        else:
            self.customer_box.configure(values=["No customers"], state="disabled")
            self.cust_var.set("")

    def load_grid(self, parent: ctk.CTkScrollableFrame) -> None:
        for w in parent.winfo_children():
            w.destroy()
        cat = self.cat_var.get()
        keyword = self.search_var.get().lower().strip()

        # SQL-based filtering for better performance
        query = "SELECT * FROM items WHERE 1=1"
        params: List = []
        if cat != "All":
            query += " AND category = ?"
            params.append(cat)
        if keyword:
            query += " AND (LOWER(name) LIKE ? OR LOWER(item_code) LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        query += " ORDER BY name"

        items = db.fetch(query, tuple(params))
        max_cols = 2
        for col in range(max_cols):
            parent.grid_columnconfigure(col, weight=1)

        if not items:
            ctk.CTkLabel(parent, text="No items found matching your criteria.", text_color="gray").grid(
                row=0, column=0, columnspan=2, pady=20
            )
            return

        r = c = 0
        for item in items:
            card = ctk.CTkFrame(parent, border_width=1, border_color="gray40", corner_radius=Theme.CARD_RADIUS)
            card.grid(row=r, column=c, padx=10, pady=8, sticky="ew")

            # Use image cache for better performance
            if item[5]:
                img = ImageCache.get(item[5], (70, 70))
                if img:
                    ctk.CTkLabel(card, text="", image=img).pack(side="left", padx=10, pady=10)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", padx=5)
            ctk.CTkLabel(info, text=item[1], font=("Arial", Theme.FONT_LG, "bold"), wraplength=150).pack(anchor="w")
            ctk.CTkLabel(info, text=currency(item[3]), font=("Arial", Theme.FONT_MD)).pack(anchor="w")

            # Show stock with color coding
            stock = item[4]
            stock_color = Theme.MUTED if stock > 10 else (Theme.WARNING if stock > 0 else Theme.ERROR)
            stock_text = f"Stock: {stock}" if stock > 0 else "Out of Stock"
            ctk.CTkLabel(info, text=stock_text, font=("Arial", Theme.FONT_SM), text_color=stock_color).pack(anchor="w")

            # Disable add button if out of stock
            add_btn = ctk.CTkButton(
                card,
                text="Add",
                width=60,
                fg_color=Theme.PRIMARY if stock > 0 else Theme.MUTED,
                state="normal" if stock > 0 else "disabled",
                command=lambda x=item: self.add_cart(x),
            )
            add_btn.pack(side="right", padx=10)

            c += 1
            if c >= max_cols:
                c = 0
                r += 1

    def add_cart(self, item: sqlite3.Row) -> None:
        item_id = item[0]
        item_name = item[1]
        current_stock = db.get_item_stock(item_id)

        if current_stock is None or current_stock <= 0:
            messagebox.showwarning("Out of Stock", f"'{item_name}' is currently out of stock.")
            return

        current_qty = self.cart.get(item_id, {}).get("qty", 0)
        if current_qty >= current_stock:
            messagebox.showwarning(
                "Stock Limit",
                f"Cannot add more '{item_name}'. Only {current_stock} available in stock."
            )
            return

        if item_id in self.cart:
            self.cart[item_id]["qty"] += 1
        else:
            self.cart[item_id] = {"name": item_name, "price": item[3], "qty": 1, "stock": current_stock}
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
        total = 0
        for idx, (iid, data) in enumerate(self.cart.items()):
            subtotal = data["price"] * data["qty"]
            total += subtotal
            card = ctk.CTkFrame(self.cart_frame, fg_color=("gray95", "#333"), corner_radius=10)
            card.grid(row=idx, column=0, padx=8, pady=6, sticky="nsew")
            card.grid_columnconfigure(0, weight=1)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.grid(row=0, column=0, sticky="ew", pady=(6, 0), padx=8)
            header.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                header, text=data["name"], anchor="w", wraplength=260, font=("Arial", 13, "bold")
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

        # Validate customer selection
        try:
            cid = int(self.cust_var.get().split(" - ")[0])
        except (ValueError, IndexError):
            messagebox.showerror("Invalid Customer", "Please select a valid customer.")
            return

        # Check stock availability before checkout
        insufficient = db.check_stock_availability(self.cart)
        if insufficient:
            error_msg = "The following items have insufficient stock:\n\n"
            for name, requested, available in insufficient:
                error_msg += f"• {name}: Requested {requested}, Available {available}\n"
            error_msg += "\nPlease adjust quantities before checkout."
            messagebox.showerror("Insufficient Stock", error_msg)
            return

        total = sum(d["price"] * d["qty"] for d in self.cart.values())

        # Validate minimum order
        if total <= 0:
            messagebox.showerror("Invalid Order", "Order total must be greater than 0.")
            return

        try:
            # Use transaction for atomic order creation
            order_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Create order
            oid = db.execute(
                "INSERT INTO orders (customer_id, date, total, status) VALUES (?, ?, ?, 'Pending')",
                (cid, order_date, total),
            )
            db.ensure_row_code("orders", "order_code", "ORD-", oid)

            # Insert order items and update stock
            for iid, d in self.cart.items():
                db.execute(
                    "INSERT INTO order_items (order_id, item_id, quantity, subtotal) VALUES (?, ?, ?, ?)",
                    (oid, iid, d["qty"], d["price"] * d["qty"]),
                )
                # Deduct from stock
                db.execute(
                    "UPDATE items SET stock = stock - ? WHERE id = ?",
                    (d["qty"], iid),
                )

            logger.info(f"Order {oid} created successfully for customer {cid}, total: {total}")
            messagebox.showinfo("Success", f"Order #{oid} placed successfully!\n\nTotal: {currency(total)}")

            self.cart = {}
            self.update_cart()
            self.show_history()

        except sqlite3.Error as e:
            logger.error(f"Checkout failed: {e}")
            messagebox.showerror("Order Failed", "Failed to create order. Please try again.")

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
        months = ["All"] + [datetime(datetime.now().year, m, 1).strftime("%b") for m in range(1, 13)]
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

        # Debounced search for better performance
        order_debouncer = Debouncer(search, 300)
        search.bind("<KeyRelease>", lambda _e: order_debouncer.debounce(self.load_orders))

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

        color_map = Theme.STATUS_COLORS
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
        if self.date_picker_win and self.date_picker_win.winfo_exists():
            self.date_picker_win.focus_set()
            return
        current = self._parse_date(target_var.get()) or datetime.now()
        month_var = tk.IntVar(value=current.month)
        year_var = tk.IntVar(value=current.year)

        picker = ctk.CTkToplevel(self)
        self.date_picker_win = picker
        picker.title("Select Date")
        picker.resizable(False, False)
        try:
            x = anchor_widget.winfo_rootx()
            y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
            picker.geometry(f"+{x}+{y}")
        except Exception:
            picker.geometry("+200+200")
        picker.grab_set()

        def close_picker() -> None:
            if picker.winfo_exists():
                picker.destroy()
            self.date_picker_win = None

        picker.protocol("WM_DELETE_WINDOW", close_picker)

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
            close_picker()
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

        picker.bind("<Destroy>", lambda _e: setattr(self, "date_picker_win", None))
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
        t.geometry("680x700")
        t.title(f"Edit Order {order_code}")
        t.grab_set()

        # Store original quantities for inventory adjustment
        self.edit_cart: Dict[int, Dict] = {}
        self.original_cart: Dict[int, int] = {}  # item_id -> original_qty
        existing = db.fetch(
            "SELECT oi.item_id, i.name, i.price, oi.quantity FROM order_items oi JOIN items i ON oi.item_id = i.id WHERE oi.order_id=?",
            (oid,),
        )
        for iid, name, price, qty in existing:
            self.edit_cart[iid] = {"name": name, "price": price, "qty": qty}
            self.original_cart[iid] = qty

        ctk.CTkLabel(t, text=f"Editing {order_code}\nInternal ID: {oid}", font=("Arial", 20, "bold")).pack(pady=10)

        # Info label about inventory
        ctk.CTkLabel(
            t,
            text="Note: Inventory will be automatically adjusted when you save changes",
            font=("Arial", 11),
            text_color="gray"
        ).pack(pady=(0, 10))

        add_f = ctk.CTkFrame(t)
        add_f.pack(fill="x", padx=20, pady=10)
        all_items = db.fetch("SELECT id, name, price, stock FROM items")
        item_map = {f"{i['name']} ({currency(i['price'])}) - Stock: {i['stock']}": i for i in all_items}
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
            item_id = raw["id"]
            current_stock = raw["stock"]

            # Calculate available stock (current stock + what was originally ordered)
            original_qty = self.original_cart.get(item_id, 0)
            current_edit_qty = self.edit_cart.get(item_id, {}).get("qty", 0)
            available = current_stock + original_qty

            if current_edit_qty >= available:
                messagebox.showwarning(
                    "Stock Limit",
                    f"Cannot add more '{raw['name']}'. Only {available} available (including already ordered)."
                )
                return

            if item_id in self.edit_cart:
                self.edit_cart[item_id]["qty"] += 1
            else:
                self.edit_cart[item_id] = {"name": raw["name"], "price": raw["price"], "qty": 1}
            refresh_list()

        ctk.CTkButton(
            add_f,
            text="Add Item",
            width=90,
            command=add_new,
            fg_color=Theme.PRIMARY,
            state="normal" if item_map else "disabled",
        ).pack(side="right", padx=10)

        list_f = ctk.CTkScrollableFrame(t)
        list_f.pack(fill="both", expand=True, padx=20, pady=10)

        def change_qty(iid: int, delta: int) -> None:
            if delta > 0:
                # Check stock when increasing
                current_stock = db.get_item_stock(iid) or 0
                original_qty = self.original_cart.get(iid, 0)
                current_edit_qty = self.edit_cart[iid]["qty"]
                available = current_stock + original_qty

                if current_edit_qty >= available:
                    messagebox.showwarning("Stock Limit", f"No more stock available for this item.")
                    return

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

                # Calculate change from original
                original_qty = self.original_cart.get(iid, 0)
                diff = data["qty"] - original_qty
                diff_text = ""
                diff_color = "gray"
                if diff > 0:
                    diff_text = f" (+{diff})"
                    diff_color = Theme.WARNING
                elif diff < 0:
                    diff_text = f" ({diff})"
                    diff_color = Theme.SUCCESS  # Returning to inventory

                row = ctk.CTkFrame(list_f, fg_color=Theme.CARD_BG)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=data["name"], anchor="w", width=200).pack(side="left", padx=10)
                ctk.CTkLabel(row, text=currency(data["price"]), width=80).pack(side="left")

                # Show quantity with change indicator
                qty_frame = ctk.CTkFrame(row, fg_color="transparent")
                qty_frame.pack(side="left", padx=5)
                ctk.CTkLabel(qty_frame, text=str(data["qty"]), width=30).pack(side="left")
                if diff_text:
                    ctk.CTkLabel(qty_frame, text=diff_text, text_color=diff_color, font=("Arial", 10)).pack(side="left")

                ctrl = ctk.CTkFrame(row, fg_color="transparent")
                ctrl.pack(side="right", padx=10)
                ctk.CTkButton(ctrl, text="-", width=30, command=lambda x=iid: change_qty(x, -1)).pack(side="left")
                ctk.CTkButton(ctrl, text="+", width=30, command=lambda x=iid: change_qty(x, 1)).pack(side="left")

            # Show items being returned to inventory
            returned_items = []
            for iid, orig_qty in self.original_cart.items():
                if iid not in self.edit_cart:
                    item_name = db.fetch("SELECT name FROM items WHERE id=?", (iid,))
                    if item_name:
                        returned_items.append(f"{item_name[0][0]} x{orig_qty}")

            if returned_items:
                ctk.CTkLabel(
                    list_f,
                    text=f"Returning to inventory: {', '.join(returned_items)}",
                    text_color=Theme.SUCCESS,
                    font=("Arial", 11)
                ).pack(pady=5)

            lbl_total.configure(text=f"New Total: {currency(grand)}")

        lbl_total = ctk.CTkLabel(t, text="New Total: R 0.00", font=("Arial", 18, "bold"))
        lbl_total.pack(pady=8)

        def save_changes() -> None:
            if not self.edit_cart:
                messagebox.showerror("Validation", "An order must have at least one item.")
                return

            try:
                # Calculate inventory adjustments
                for iid, orig_qty in self.original_cart.items():
                    new_qty = self.edit_cart.get(iid, {}).get("qty", 0)
                    diff = orig_qty - new_qty  # Positive = return to stock, Negative = take from stock

                    if diff != 0:
                        db.execute("UPDATE items SET stock = stock + ? WHERE id = ?", (diff, iid))
                        logger.info(f"Order {oid} edit: Item {iid} stock adjusted by {diff}")

                # Handle new items not in original order
                for iid, data in self.edit_cart.items():
                    if iid not in self.original_cart:
                        # New item added - deduct from stock
                        db.execute("UPDATE items SET stock = stock - ? WHERE id = ?", (data["qty"], iid))
                        logger.info(f"Order {oid} edit: New item {iid} deducted {data['qty']} from stock")

                total = sum(d["qty"] * d["price"] for d in self.edit_cart.values())
                db.execute("DELETE FROM order_items WHERE order_id=?", (oid,))
                for iid, data in self.edit_cart.items():
                    db.execute(
                        "INSERT INTO order_items (order_id, item_id, quantity, subtotal) VALUES (?, ?, ?, ?)",
                        (oid, iid, data["qty"], data["qty"] * data["price"]),
                    )
                db.execute("UPDATE orders SET total=?, status=? WHERE id=?", (total, "Preparing", oid))
                messagebox.showinfo("Saved", f"Order {order_code} updated and inventory adjusted")
                t.destroy()
                self.refresh_order_list()

            except sqlite3.Error as e:
                logger.error(f"Failed to update order {oid}: {e}")
                messagebox.showerror("Error", "Failed to save changes. Please try again.")

        ctk.CTkButton(t, text="SAVE CHANGES", fg_color=Theme.PRIMARY, height=44, command=save_changes).pack(
            fill="x", padx=20, pady=16
        )
        refresh_list()

    def gen_pdf(self, oid: Optional[int]) -> None:
        """Generate a professional formal invoice PDF"""
        if not oid:
            return
        file = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"Invoice_{oid}.pdf")
        if not file:
            return

        data = db.fetch(
            """SELECT o.id, o.order_code, c.name, o.date, o.total, c.address, c.city, c.email, c.phone, o.status
               FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id=?""",
            (oid,),
        )[0]
        order_code = data["order_code"] or db.ensure_row_code("orders", "order_code", "ORD-", oid)
        items = db.fetch(
            "SELECT i.name, oi.quantity, i.price, oi.subtotal FROM order_items oi JOIN items i ON oi.item_id = i.id WHERE oi.order_id=?",
            (oid,),
        )

        c = canvas.Canvas(file, pagesize=A4)
        width, height = A4

        # ===== HEADER SECTION =====
        # Company logo area (green banner)
        c.setFillColor(colors.HexColor(Theme.PRIMARY))
        c.rect(0, height - 100, width, 100, fill=True, stroke=False)

        # Company name and details
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(25 * mm, height - 35, APP_NAME)
        c.setFont("Helvetica", 11)
        c.drawString(25 * mm, height - 50, APP_TAGLINE)
        c.drawString(25 * mm, height - 65, f"{APP_LOCATION}")
        c.drawString(25 * mm, height - 80, "Tel: +27 12 XXX XXXX  |  Email: info@renusdelights.co.za")

        # INVOICE title on the right
        c.setFont("Helvetica-Bold", 32)
        c.drawRightString(width - 25 * mm, height - 45, "INVOICE")
        c.setFont("Helvetica", 12)
        c.drawRightString(width - 25 * mm, height - 62, f"#{order_code}")

        # ===== INVOICE DETAILS BOX =====
        y = height - 130

        # Invoice info box (right side)
        c.setFillColor(colors.HexColor("#f8f8f8"))
        c.roundRect(width - 85 * mm, y - 55, 70 * mm, 60, 3, fill=True, stroke=False)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(width - 82 * mm, y - 8, "Invoice Number:")
        c.drawString(width - 82 * mm, y - 22, "Invoice Date:")
        c.drawString(width - 82 * mm, y - 36, "Due Date:")
        c.drawString(width - 82 * mm, y - 50, "Status:")

        c.setFont("Helvetica", 10)
        c.drawRightString(width - 18 * mm, y - 8, order_code)
        invoice_date = datetime.strptime(data['date'], "%Y-%m-%d %H:%M:%S") if data['date'] else datetime.now()
        c.drawRightString(width - 18 * mm, y - 22, invoice_date.strftime("%d %B %Y"))
        c.drawRightString(width - 18 * mm, y - 36, "Due on Receipt")
        status = db.normalize_status(data['status'])
        status_color = Theme.STATUS_COLORS.get(status, Theme.MUTED)
        c.setFillColor(colors.HexColor(status_color))
        c.drawRightString(width - 18 * mm, y - 50, status)

        # ===== BILL TO SECTION =====
        c.setFillColor(colors.HexColor(Theme.PRIMARY))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(25 * mm, y, "BILL TO:")
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(25 * mm, y - 15, data['name'])
        c.setFont("Helvetica", 10)
        y_bill = y - 28
        if data['email']:
            c.drawString(25 * mm, y_bill, data['email'])
            y_bill -= 12
        if data.get('phone'):
            c.drawString(25 * mm, y_bill, data['phone'])
            y_bill -= 12
        if data['address'] or data['city']:
            address_line = f"{data['address'] or ''}"
            if data['city']:
                address_line += f", {data['city']}"
            c.drawString(25 * mm, y_bill, address_line.strip(", "))

        # ===== ITEMS TABLE =====
        y = height - 220

        # Table header
        c.setFillColor(colors.HexColor(Theme.PRIMARY))
        c.rect(20 * mm, y - 5, width - 40 * mm, 20, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(25 * mm, y + 2, "DESCRIPTION")
        c.drawString(105 * mm, y + 2, "QTY")
        c.drawString(125 * mm, y + 2, "UNIT PRICE")
        c.drawRightString(width - 25 * mm, y + 2, "AMOUNT")

        y -= 22
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 10)

        subtotal = 0
        row_alt = False
        for name, qty, price, sub in items:
            # Alternating row background
            if row_alt:
                c.setFillColor(colors.HexColor("#f9f9f9"))
                c.rect(20 * mm, y - 3, width - 40 * mm, 16, fill=True, stroke=False)
            row_alt = not row_alt

            c.setFillColor(colors.black)
            c.drawString(25 * mm, y, name[:45])
            c.drawString(108 * mm, y, str(qty))
            c.drawString(125 * mm, y, currency(price))
            c.drawRightString(width - 25 * mm, y, currency(sub))
            subtotal += sub
            y -= 18

            if y < 80 * mm:
                c.showPage()
                y = height - 50 * mm

        # Table bottom line
        c.setStrokeColor(colors.HexColor("#cccccc"))
        c.line(20 * mm, y + 5, width - 20 * mm, y + 5)

        # ===== TOTALS SECTION =====
        y -= 15

        # Subtotal
        c.setFont("Helvetica", 11)
        c.drawString(125 * mm, y, "Subtotal:")
        c.drawRightString(width - 25 * mm, y, currency(subtotal))
        y -= 16

        # VAT (15% for South Africa)
        vat = subtotal * 0.15
        c.drawString(125 * mm, y, "VAT (15%):")
        c.drawRightString(width - 25 * mm, y, currency(vat))
        y -= 20

        # Grand Total box
        c.setFillColor(colors.HexColor(Theme.PRIMARY))
        c.roundRect(120 * mm, y - 8, width - 145 * mm, 25, 3, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(125 * mm, y, "TOTAL DUE:")
        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(width - 25 * mm, y, currency(data["total"]))

        # ===== PAYMENT DETAILS =====
        y -= 50
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(25 * mm, y, "PAYMENT INFORMATION")
        y -= 15
        c.setFont("Helvetica", 10)
        c.drawString(25 * mm, y, "Bank: First National Bank (FNB)")
        y -= 12
        c.drawString(25 * mm, y, "Account Name: Renus Authentic Delights")
        y -= 12
        c.drawString(25 * mm, y, "Account Number: XXXX XXXX XXXX")
        y -= 12
        c.drawString(25 * mm, y, "Branch Code: 250655")
        y -= 12
        c.drawString(25 * mm, y, f"Reference: {order_code}")

        # ===== TERMS & NOTES =====
        y -= 30
        c.setFont("Helvetica-Bold", 11)
        c.drawString(25 * mm, y, "TERMS & CONDITIONS")
        y -= 15
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(25 * mm, y, "1. Payment is due upon receipt of this invoice.")
        y -= 11
        c.drawString(25 * mm, y, "2. Please use the invoice number as payment reference.")
        y -= 11
        c.drawString(25 * mm, y, "3. For queries, contact us at info@renusdelights.co.za or +27 12 XXX XXXX")

        # ===== FOOTER =====
        c.setFillColor(colors.HexColor(Theme.PRIMARY))
        c.rect(0, 0, width, 25, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 9)
        c.drawCentredString(width / 2, 10, "Thank you for your business!  |  www.renusdelights.co.za  |  Pretoria, South Africa")

        c.save()
        logger.info(f"Invoice generated for order {oid}: {file}")
        messagebox.showinfo("Invoice Generated", f"Professional invoice saved to:\n{file}")

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

        # Debounced search for better performance
        item_debouncer = Debouncer(search_entry, 250)
        search_entry.bind("<KeyRelease>", lambda _e: item_debouncer.debounce(self.render_item_cards))

        ctk.CTkButton(controls, text="✕", width=28, command=self.clear_item_filters).pack(side="left", padx=4)
        ctk.CTkButton(
            controls,
            text="+ Add New Item",
            width=180,
            height=40,
            font=("Arial", Theme.FONT_LG, "bold"),
            command=lambda: self.item_popup(None),
            fg_color=Theme.PRIMARY,
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

        # SQL-based filtering for better performance (include image_path)
        query = "SELECT id, name, category, price, stock, item_code, image_path FROM items WHERE 1=1"
        params: List = []
        if cat != "All":
            query += " AND category = ?"
            params.append(cat)
        if keyword:
            query += " AND (LOWER(name) LIKE ? OR LOWER(item_code) LIKE ? OR LOWER(category) LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        query += " ORDER BY id DESC"

        items = db.fetch(query, tuple(params))

        if not items:
            ctk.CTkLabel(self.item_list_frame, text="No items match your filters.", text_color="gray").pack(pady=16)
            return

        for r in items:
            code = r["item_code"] or db.generate_code("ITM-", r["id"])
            card = ctk.CTkFrame(self.item_list_frame, fg_color=Theme.CARD_BG, corner_radius=Theme.CARD_RADIUS)
            card.pack(fill="x", pady=6, padx=5)

            # Display image if available
            image_path = r["image_path"]
            if image_path:
                img = ImageCache.get(image_path, (60, 60))
                if img:
                    ctk.CTkLabel(card, text="", image=img).pack(side="left", padx=(15, 10), pady=10)

            # Item info frame
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", padx=10, pady=10, fill="y")

            ctk.CTkLabel(
                info_frame,
                text=r['name'],
                font=("Arial", Theme.FONT_LG, "bold"),
                anchor="w"
            ).pack(anchor="w")
            ctk.CTkLabel(
                info_frame,
                text=f"{code} (ID {r['id']})",
                font=("Arial", Theme.FONT_SM),
                text_color="gray",
                anchor="w"
            ).pack(anchor="w")

            # Category badge
            cat_color = Theme.INFO if r["category"] == "Menu" else (Theme.WARNING if r["category"] == "Spice" else Theme.MUTED)
            ctk.CTkLabel(
                card,
                text=r["category"],
                width=80,
                fg_color=cat_color,
                corner_radius=4,
                text_color="white"
            ).pack(side="left", padx=10)

            ctk.CTkLabel(
                card,
                text=currency(r["price"]),
                font=("Arial", Theme.FONT_LG, "bold"),
                width=100,
                anchor="w"
            ).pack(side="left", padx=10)

            # Color-coded stock display
            stock = r['stock']
            stock_color = Theme.MUTED if stock > 10 else (Theme.WARNING if stock > 0 else Theme.ERROR)
            stock_text = f"Stock: {stock}" if stock > 0 else "Out of Stock"
            ctk.CTkLabel(card, text=stock_text, text_color=stock_color).pack(side="left", padx=10)

            ctk.CTkButton(
                card,
                text="Delete",
                fg_color=Theme.ERROR,
                width=70,
                command=lambda i=r["id"]: self.del_item(i)
            ).pack(side="right", padx=10)
            ctk.CTkButton(
                card,
                text="Edit",
                fg_color=Theme.ACCENT,
                text_color="black",
                width=70,
                command=lambda i=r["id"]: self.item_popup(i),
            ).pack(side="right", padx=5)

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

        # Debounced search for better performance
        customer_debouncer = Debouncer(search_entry, 250)
        search_entry.bind("<KeyRelease>", lambda _e: customer_debouncer.debounce(self.render_customer_cards))

        ctk.CTkButton(controls, text="✕", width=28, command=self.clear_customer_filters).pack(side="left", padx=4)
        ctk.CTkButton(
            controls,
            text="+ Add Customer",
            width=200,
            height=40,
            font=("Arial", Theme.FONT_LG, "bold"),
            command=lambda: self.cust_popup(None),
            fg_color=Theme.PRIMARY,
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

        # SQL-based filtering for better performance
        query = "SELECT id, name, email, address, city, phone FROM customers WHERE 1=1"
        params: List = []
        if keyword:
            query += """ AND (LOWER(name) LIKE ? OR LOWER(email) LIKE ?
                        OR LOWER(COALESCE(city, '')) LIKE ? OR LOWER(COALESCE(phone, '')) LIKE ?
                        OR LOWER(COALESCE(address, '')) LIKE ?)"""
            params.extend([f"%{keyword}%"] * 5)
        query += " ORDER BY name"

        records = db.fetch(query, tuple(params))

        if not records:
            ctk.CTkLabel(
                self.customer_list_frame,
                text="No customers match your filters.",
                text_color="gray"
            ).pack(pady=16)
            return

        for r in records:
            card = ctk.CTkFrame(self.customer_list_frame, fg_color=Theme.CARD_BG, corner_radius=Theme.CARD_RADIUS)
            card.pack(fill="x", pady=5, padx=5)
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", padx=20, pady=10)
            ctk.CTkLabel(
                info,
                text=f"{r['name']} (ID {r['id']})",
                font=("Arial", Theme.FONT_LG, "bold"),
                anchor="w"
            ).pack(anchor="w")
            ctk.CTkLabel(
                info,
                text=r["email"],
                font=("Arial", Theme.FONT_MD),
                text_color="gray",
                anchor="w"
            ).pack(anchor="w")
            addr = ctk.CTkFrame(card, fg_color="transparent")
            addr.pack(side="left", padx=20)
            ctk.CTkLabel(
                addr,
                text=r["city"] or "No City",
                font=("Arial", Theme.FONT_MD, "bold"),
                anchor="w"
            ).pack(anchor="w")
            ctk.CTkLabel(
                addr,
                text=r["address"] or "No Address",
                font=("Arial", 11),
                text_color="gray",
                anchor="w"
            ).pack(anchor="w")
            ctk.CTkLabel(addr, text=r["phone"] or "", font=("Arial", 11)).pack(anchor="w")
            ctk.CTkButton(
                card,
                text="Delete",
                fg_color=Theme.ERROR,
                width=70,
                command=lambda i=r["id"]: self.del_cust(i)
            ).pack(side="right", padx=10)
            ctk.CTkButton(
                card,
                text="Edit",
                fg_color=Theme.ACCENT,
                text_color="black",
                width=70,
                command=lambda i=r["id"]: self.cust_popup(i),
            ).pack(side="right", padx=5)

    def clear_customer_filters(self) -> None:
        if hasattr(self, "customer_search_var"):
            self.customer_search_var.set("")
        self.render_customer_cards()

    def cust_popup(self, cid: Optional[int]) -> None:
        t = ctk.CTkToplevel(self)
        t.geometry("400x560")
        t.title("Customer Details")
        t.grab_set()

        # Error label for inline validation feedback
        error_label = ctk.CTkLabel(t, text="", text_color=Theme.ERROR, wraplength=350)
        error_label.pack(pady=(10, 0))

        ctk.CTkLabel(t, text="Name *", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e1 = ctk.CTkEntry(t, placeholder_text="Enter customer name")
        e1.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="Email *", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e2 = ctk.CTkEntry(t, placeholder_text="customer@example.com")
        e2.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="Address", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e3 = ctk.CTkEntry(t, placeholder_text="Street address")
        e3.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="City", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e4 = ctk.CTkEntry(t, placeholder_text="City name")
        e4.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="Phone", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e5 = ctk.CTkEntry(t, placeholder_text="+27 XX XXX XXXX")
        e5.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="* Required fields", font=("Arial", Theme.FONT_SM), text_color="gray").pack(pady=6)

        if cid:
            d = db.fetch("SELECT name, email, address, city, phone FROM customers WHERE id=?", (cid,))[0]
            e1.insert(0, d[0])
            e2.insert(0, d[1])
            e3.insert(0, d[2] or "")
            e4.insert(0, d[3] or "")
            e5.insert(0, d[4] or "")

        def validate_and_save() -> None:
            error_label.configure(text="")

            # Validate name
            valid, msg = Validators.name(e1.get(), "Name")
            if not valid:
                error_label.configure(text=msg)
                e1.focus_set()
                return

            # Validate email
            valid, msg = Validators.email(e2.get())
            if not valid:
                error_label.configure(text=msg)
                e2.focus_set()
                return

            # Check email uniqueness
            email = e2.get().strip()
            if not db.is_email_unique(email, "customers", cid):
                error_label.configure(text="This email is already registered to another customer")
                e2.focus_set()
                return

            # Validate city (optional)
            valid, msg = Validators.city(e4.get())
            if not valid:
                error_label.configure(text=msg)
                e4.focus_set()
                return

            # Validate phone (optional)
            valid, msg = Validators.phone(e5.get())
            if not valid:
                error_label.configure(text=msg)
                e5.focus_set()
                return

            try:
                name = e1.get().strip()
                if cid:
                    db.execute(
                        "UPDATE customers SET name=?, email=?, address=?, city=?, phone=? WHERE id=?",
                        (name, email, e3.get().strip(), e4.get().strip(), e5.get().strip(), cid),
                    )
                    logger.info(f"Customer {cid} updated: {name}")
                else:
                    new_id = db.execute(
                        "INSERT INTO customers (name, email, address, city, phone) VALUES (?, ?, ?, ?, ?)",
                        (name, email, e3.get().strip(), e4.get().strip(), e5.get().strip()),
                    )
                    logger.info(f"New customer created: ID {new_id}, {name}")
                t.destroy()
                self.show_customers()
            except sqlite3.Error as e:
                logger.error(f"Customer save error: {e}")
                error_label.configure(text="Failed to save customer. Please try again.")

        ctk.CTkButton(
            t,
            text="Save Customer",
            command=validate_and_save,
            fg_color=Theme.PRIMARY,
            height=40
        ).pack(pady=20, fill="x", padx=20)

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

        # Debounced search for better performance
        user_debouncer = Debouncer(search_entry, 250)
        search_entry.bind("<KeyRelease>", lambda _e: user_debouncer.debounce(self.render_user_cards))

        ctk.CTkButton(controls, text="✕", width=28, command=self.clear_user_filters).pack(side="left", padx=4)
        ctk.CTkButton(
            controls,
            text="+ Add User",
            width=200,
            height=40,
            font=("Arial", Theme.FONT_LG, "bold"),
            command=lambda: self.user_popup(None),
            fg_color=Theme.PRIMARY,
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

        # SQL-based filtering for better performance
        query = "SELECT id, full_name, role, email, phone, user_code FROM users WHERE 1=1"
        params: List = []
        if role_filter != "All":
            query += " AND role = ?"
            params.append(role_filter)
        if keyword:
            query += """ AND (LOWER(full_name) LIKE ? OR LOWER(email) LIKE ?
                        OR LOWER(COALESCE(user_code, '')) LIKE ? OR LOWER(COALESCE(phone, '')) LIKE ?
                        OR LOWER(role) LIKE ?)"""
            params.extend([f"%{keyword}%"] * 5)
        query += " ORDER BY id DESC"

        users = db.fetch(query, tuple(params))

        if not users:
            ctk.CTkLabel(self.user_list_frame, text="No users match your filters.", text_color="gray").pack(pady=16)
            return

        for r in users:
            code = r["user_code"] or db.generate_code("USR-", r["id"])
            card = ctk.CTkFrame(self.user_list_frame, fg_color=Theme.CARD_BG, corner_radius=Theme.CARD_RADIUS)
            card.pack(fill="x", pady=5, padx=5)
            ctk.CTkLabel(
                card,
                text=f"{r['full_name']}\n{code} (ID {r['id']})",
                font=("Arial", Theme.FONT_LG, "bold"),
                width=220,
                anchor="w"
            ).pack(side="left", padx=20, pady=12)
            ctk.CTkLabel(card, text=r["role"], width=120, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(card, text=r["email"], width=220, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(card, text=r["phone"] or "").pack(side="left", padx=10)
            ctk.CTkButton(
                card,
                text="Delete",
                fg_color=Theme.ERROR,
                width=70,
                command=lambda i=r["id"]: self.del_user(i)
            ).pack(side="right", padx=10)
            ctk.CTkButton(
                card,
                text="Edit",
                fg_color=Theme.ACCENT,
                text_color="black",
                width=70,
                command=lambda i=r["id"]: self.user_popup(i),
            ).pack(side="right", padx=5)

    def clear_user_filters(self) -> None:
        if hasattr(self, "user_role_filter"):
            self.user_role_filter.set("All")
        if hasattr(self, "user_search_var"):
            self.user_search_var.set("")
        self.render_user_cards()

    def user_popup(self, uid: Optional[int]) -> None:
        t = ctk.CTkToplevel(self)
        t.geometry("400x540")
        t.title("User Details")
        t.grab_set()

        # Error label for inline validation feedback
        error_label = ctk.CTkLabel(t, text="", text_color=Theme.ERROR, wraplength=350)
        error_label.pack(pady=(10, 0))

        code_label = ctk.CTkLabel(t, text="User code will be generated on save", text_color="gray")
        code_label.pack(pady=(8, 2))

        ctk.CTkLabel(t, text="First Name *", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e1 = ctk.CTkEntry(t, placeholder_text="Enter first name")
        e1.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="Surname *", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e_surname = ctk.CTkEntry(t, placeholder_text="Enter surname")
        e_surname.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="Role *", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        role_var = ctk.StringVar(value="Manager")
        ctk.CTkOptionMenu(t, variable=role_var, values=["Owner", "Manager", "Cashier", "Kitchen"]).pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="Email *", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e3 = ctk.CTkEntry(t, placeholder_text="user@example.com")
        e3.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="Phone", font=("Arial", Theme.FONT_MD)).pack(pady=4)
        e4 = ctk.CTkEntry(t, placeholder_text="+27 XX XXX XXXX")
        e4.pack(fill="x", padx=20)

        ctk.CTkLabel(t, text="* Required fields", font=("Arial", Theme.FONT_SM), text_color="gray").pack(pady=6)

        if uid:
            d = db.fetch("SELECT full_name, surname, role, email, phone, user_code FROM users WHERE id=?", (uid,))[0]
            # Extract first name from full_name (remove surname at end)
            full_name = d[0]
            surname = d[1] or ""
            first_name = full_name.replace(surname, "").strip() if surname else full_name
            e1.insert(0, first_name)
            e_surname.insert(0, surname)
            role_var.set(d[2])
            e3.insert(0, d[3])
            e4.insert(0, d[4] or "")
            code_label.configure(text=f"User Code: {d['user_code'] or db.generate_code('USR-', uid)} | ID: {uid}")

        def validate_and_save() -> None:
            error_label.configure(text="")

            # Validate first name
            valid, msg = Validators.name(e1.get(), "First name")
            if not valid:
                error_label.configure(text=msg)
                e1.focus_set()
                return

            # Validate surname
            valid, msg = Validators.name(e_surname.get(), "Surname")
            if not valid:
                error_label.configure(text=msg)
                e_surname.focus_set()
                return

            # Validate email
            valid, msg = Validators.email(e3.get())
            if not valid:
                error_label.configure(text=msg)
                e3.focus_set()
                return

            # Check email uniqueness
            email = e3.get().strip()
            if not db.is_email_unique(email, "users", uid):
                error_label.configure(text="This email is already registered to another user")
                e3.focus_set()
                return

            # Validate phone (optional)
            valid, msg = Validators.phone(e4.get())
            if not valid:
                error_label.configure(text=msg)
                e4.focus_set()
                return

            try:
                name = e1.get().strip()
                surname = e_surname.get().strip()
                full = f"{name} {surname}".strip()
                if uid:
                    db.execute(
                        "UPDATE users SET full_name=?, surname=?, role=?, email=?, phone=? WHERE id=?",
                        (full, surname, role_var.get(), email, e4.get().strip(), uid),
                    )
                    logger.info(f"User {uid} updated: {full}")
                else:
                    new_uid = db.execute(
                        "INSERT INTO users (full_name, surname, role, email, phone) VALUES (?, ?, ?, ?, ?)",
                        (full, surname, role_var.get(), email, e4.get().strip()),
                    )
                    db.ensure_row_code("users", "user_code", "USR-", new_uid)
                    logger.info(f"New user created: ID {new_uid}, {full}")
                t.destroy()
                self.show_users()
            except sqlite3.Error as e:
                logger.error(f"User save error: {e}")
                error_label.configure(text="Failed to save user. Please try again.")

        ctk.CTkButton(
            t,
            text="Save User",
            command=validate_and_save,
            fg_color=Theme.PRIMARY,
            height=40
        ).pack(pady=20, fill="x", padx=20)

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
        # Use current year for month names (any year works since we only need month names)
        month_values = ["All"] + [datetime(datetime.now().year, m, 1).strftime("%B") for m in range(1, 13)]
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

        # Summary cards
        cards = ctk.CTkFrame(self.report_body, fg_color="transparent")
        cards.pack(fill="x", pady=8)
        for title, value, color in [
            ("Revenue", currency(report["total_revenue"]), Theme.PRIMARY),
            ("Orders", str(len(report["orders"])), Theme.INFO),
            ("Completed", str(report["status_counts"].get("Completed", 0)), Theme.SUCCESS),
            ("Pending", str(report["status_counts"].get("Pending", 0)), Theme.WARNING),
        ]:
            card = ctk.CTkFrame(cards, fg_color=("white", "#2b2b2b"), corner_radius=12)
            card.pack(side="left", expand=True, fill="x", padx=6)
            ctk.CTkLabel(card, text=title, font=("Arial", 13), text_color="gray").pack(pady=(12, 2))
            ctk.CTkLabel(card, text=value, font=("Arial", 20, "bold"), text_color=color).pack(pady=(0, 12))

        # Charts section
        charts_frame = ctk.CTkFrame(self.report_body, fg_color="transparent")
        charts_frame.pack(fill="x", pady=10)
        charts_frame.grid_columnconfigure(0, weight=1)
        charts_frame.grid_columnconfigure(1, weight=1)

        # Create charts if there's data
        if report["orders"] or report["top_items"]:
            self._create_status_pie_chart(charts_frame, report, 0)
            self._create_top_items_bar_chart(charts_frame, report, 1)

        # Top Items list
        detail = ctk.CTkFrame(self.report_body, fg_color=("white", "#2b2b2b"), corner_radius=12)
        detail.pack(fill="both", expand=True, pady=10)
        ctk.CTkLabel(detail, text="Top Selling Items", font=("Arial", 15, "bold")).pack(anchor="w", padx=14, pady=8)
        if report["top_items"]:
            for idx, (name, qty) in enumerate(report["top_items"], 1):
                row = ctk.CTkFrame(detail, fg_color="transparent")
                row.pack(fill="x", padx=14, pady=2)
                ctk.CTkLabel(row, text=f"{idx}.", font=("Arial", 12, "bold"), width=25).pack(side="left")
                ctk.CTkLabel(row, text=name, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=f"{qty} sold", anchor="e", text_color=Theme.PRIMARY).pack(side="right")
        else:
            ctk.CTkLabel(detail, text="No sales in this period", text_color="gray").pack(pady=10)

        # Status chips
        status_frame = ctk.CTkFrame(self.report_body, fg_color="transparent")
        status_frame.pack(fill="x", pady=6)
        for s in STATUSES:
            val = report["status_counts"].get(s, 0)
            chip = ctk.CTkFrame(status_frame, fg_color=("white", "#2b2b2b"), corner_radius=12)
            chip.pack(side="left", expand=True, fill="x", padx=5)
            ctk.CTkLabel(chip, text=s, font=("Arial", 12, "bold")).pack(pady=(8, 2))
            color = Theme.STATUS_COLORS.get(s, Theme.MUTED)
            ctk.CTkLabel(chip, text=str(val), font=("Arial", 14), text_color=color).pack(pady=(0, 8))

        self.current_report = report

    def _create_status_pie_chart(self, parent: ctk.CTkFrame, report: Dict, col: int) -> None:
        """Create a pie chart showing order status distribution"""
        chart_frame = ctk.CTkFrame(parent, fg_color=("white", "#2b2b2b"), corner_radius=12)
        chart_frame.grid(row=0, column=col, padx=6, pady=6, sticky="nsew")

        ctk.CTkLabel(chart_frame, text="Order Status Distribution", font=("Arial", 13, "bold")).pack(pady=(10, 5))

        # Get status data
        status_data = report["status_counts"]
        labels = []
        sizes = []
        colors_list = []

        for status in STATUSES:
            count = status_data.get(status, 0)
            if count > 0:
                labels.append(status)
                sizes.append(count)
                colors_list.append(Theme.STATUS_COLORS.get(status, "#757575"))

        if not sizes:
            ctk.CTkLabel(chart_frame, text="No data", text_color="gray").pack(pady=20)
            return

        # Create figure
        fig = Figure(figsize=(3.5, 2.5), dpi=100)
        fig.patch.set_facecolor('#2b2b2b' if ctk.get_appearance_mode() == "Dark" else 'white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#2b2b2b' if ctk.get_appearance_mode() == "Dark" else 'white')

        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            colors=colors_list,
            autopct='%1.0f%%',
            startangle=90,
            textprops={'color': 'white' if ctk.get_appearance_mode() == "Dark" else 'black', 'fontsize': 8}
        )
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)

        ax.axis('equal')
        fig.tight_layout()

        # Embed in tkinter
        canvas_widget = FigureCanvasTkAgg(fig, master=chart_frame)
        canvas_widget.draw()
        canvas_widget.get_tk_widget().pack(pady=5, padx=10)

    def _create_top_items_bar_chart(self, parent: ctk.CTkFrame, report: Dict, col: int) -> None:
        """Create a bar chart showing top selling items"""
        chart_frame = ctk.CTkFrame(parent, fg_color=("white", "#2b2b2b"), corner_radius=12)
        chart_frame.grid(row=0, column=col, padx=6, pady=6, sticky="nsew")

        ctk.CTkLabel(chart_frame, text="Top Selling Items", font=("Arial", 13, "bold")).pack(pady=(10, 5))

        top_items = report.get("top_items", [])
        if not top_items:
            ctk.CTkLabel(chart_frame, text="No data", text_color="gray").pack(pady=20)
            return

        # Prepare data
        names = [item[0][:15] + "..." if len(item[0]) > 15 else item[0] for item in top_items]
        quantities = [item[1] for item in top_items]

        # Create figure
        fig = Figure(figsize=(3.5, 2.5), dpi=100)
        fig.patch.set_facecolor('#2b2b2b' if ctk.get_appearance_mode() == "Dark" else 'white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#2b2b2b' if ctk.get_appearance_mode() == "Dark" else 'white')

        bars = ax.barh(names, quantities, color=Theme.PRIMARY)
        ax.invert_yaxis()  # Top item at top

        # Style
        text_color = 'white' if ctk.get_appearance_mode() == "Dark" else 'black'
        ax.tick_params(axis='both', colors=text_color, labelsize=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color(text_color)
        ax.spines['left'].set_color(text_color)

        # Add value labels
        for bar, qty in zip(bars, quantities):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
                   str(qty), va='center', color=text_color, fontsize=8)

        fig.tight_layout()

        # Embed in tkinter
        canvas_widget = FigureCanvasTkAgg(fig, master=chart_frame)
        canvas_widget.draw()
        canvas_widget.get_tk_widget().pack(pady=5, padx=10)

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

        # Header
        c.setFillColor(colors.HexColor(Theme.PRIMARY))
        c.rect(0, height - 80, width, 80, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(20 * mm, height - 35, f"{APP_NAME}")
        c.setFont("Helvetica", 14)
        c.drawString(20 * mm, height - 52, "Business Performance Report")
        c.setFont("Helvetica", 11)
        c.drawString(20 * mm, height - 68, f"Period: {period}  |  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.drawString(140 * mm, height - 52, APP_LOCATION)

        y = height - 110

        # Summary Box
        c.setFillColor(colors.HexColor("#f5f5f5"))
        c.roundRect(15 * mm, y - 60, width - 30 * mm, 65, 5, fill=True, stroke=False)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(20 * mm, y, "Executive Summary")
        y -= 20

        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor(Theme.PRIMARY))
        c.drawString(25 * mm, y, f"Total Revenue: {currency(report['total_revenue'])}")
        c.setFillColor(colors.black)
        c.drawString(100 * mm, y, f"Total Orders: {len(report['orders'])}")
        y -= 18

        c.setFont("Helvetica", 11)
        completed = report['status_counts'].get('Completed', 0)
        pending = report['status_counts'].get('Pending', 0)
        c.drawString(25 * mm, y, f"Completed: {completed}  |  Pending: {pending}  |  Preparing: {report['status_counts'].get('Preparing', 0)}  |  Ready: {report['status_counts'].get('Ready', 0)}")

        y -= 50

        # Generate and embed pie chart
        if any(report["status_counts"].values()):
            c.setFont("Helvetica-Bold", 14)
            c.drawString(20 * mm, y, "Order Status Distribution")
            y -= 10

            # Create pie chart
            fig, ax = plt.subplots(figsize=(3, 3))
            status_data = report["status_counts"]
            labels = [s for s in STATUSES if status_data.get(s, 0) > 0]
            sizes = [status_data.get(s, 0) for s in labels]
            chart_colors = [Theme.STATUS_COLORS.get(s, "#757575") for s in labels]

            if sizes:
                ax.pie(sizes, labels=labels, colors=chart_colors, autopct='%1.0f%%', startangle=90)
                ax.axis('equal')

                # Save to buffer
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
                buf.seek(0)
                plt.close(fig)

                # Add to PDF
                from reportlab.lib.utils import ImageReader
                img = ImageReader(buf)
                c.drawImage(img, 20 * mm, y - 85 * mm, width=75 * mm, height=75 * mm)

        # Top Items chart on the right
        if report["top_items"]:
            c.setFont("Helvetica-Bold", 14)
            c.drawString(105 * mm, y, "Top Selling Items")
            y_chart = y - 10

            # Create bar chart
            fig, ax = plt.subplots(figsize=(3.5, 3))
            names = [item[0][:12] + "..." if len(item[0]) > 12 else item[0] for item in report["top_items"]]
            quantities = [item[1] for item in report["top_items"]]

            bars = ax.barh(names, quantities, color=Theme.PRIMARY)
            ax.invert_yaxis()
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.set_xlabel('Quantity Sold')

            for bar, qty in zip(bars, quantities):
                ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2, str(qty), va='center', fontsize=8)

            fig.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
            buf.seek(0)
            plt.close(fig)

            from reportlab.lib.utils import ImageReader
            img = ImageReader(buf)
            c.drawImage(img, 100 * mm, y_chart - 85 * mm, width=85 * mm, height=75 * mm)

        y -= 95 * mm

        # Top Items List
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(colors.black)
        c.drawString(20 * mm, y, "Detailed Item Performance")
        y -= 18

        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(20 * mm, y, "Rank")
        c.drawString(35 * mm, y, "Item Name")
        c.drawString(120 * mm, y, "Quantity Sold")
        y -= 5
        c.line(20 * mm, y, 180 * mm, y)
        y -= 12

        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        for idx, (name, qty) in enumerate(report["top_items"] or [], 1):
            c.drawString(23 * mm, y, f"#{idx}")
            c.drawString(35 * mm, y, name[:40])
            c.drawString(125 * mm, y, str(qty))
            y -= 14
            if y < 30 * mm:
                c.showPage()
                y = height - 30 * mm

        # Footer
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#999999"))
        c.drawString(20 * mm, 15 * mm, f"Report generated by {APP_NAME} | {APP_LOCATION}")
        c.drawString(150 * mm, 15 * mm, f"Page 1")

        c.save()
        messagebox.showinfo("Saved", "Report PDF with charts generated successfully!")


if __name__ == "__main__":
    app = RenusApp()
    app.mainloop()
