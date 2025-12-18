import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import sqlite3
import os
import random
from datetime import datetime, timedelta
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# --- CONFIGURATION ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

# --- DATABASE MANAGER ---
class DBManager:
    def __init__(self, db_name="renus_final.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.init_db()

    def init_db(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL, stock INTEGER, image_path TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT, address TEXT, city TEXT)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer_id INTEGER, date TEXT, status TEXT DEFAULT 'Pending', total REAL)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS order_items (order_id INTEGER, item_id INTEGER, quantity INTEGER, subtotal REAL)''')
        
        try: self.cursor.execute("SELECT address FROM customers LIMIT 1")
        except: 
            self.cursor.execute("ALTER TABLE customers ADD COLUMN address TEXT")
            self.cursor.execute("ALTER TABLE customers ADD COLUMN city TEXT")
        self.conn.commit()
        self.seed_data()

    def seed_data(self):
        if self.cursor.execute("SELECT count(*) FROM items").fetchone()[0] > 0: return
        if not os.path.exists("assets"): os.makedirs("assets")
        self.create_dummy_image("assets/logo.png", "RD", (80, 80), "#2CC985")
        self.create_dummy_image("assets/placeholder.png", "ITEM", (100, 100), "#4a4a4a")
        img_path = os.path.abspath("assets/placeholder.png")

        items = [
            ("Lamb Breyani", "Menu", 130.00), ("Chicken Breyani", "Menu", 100.00),
            ("Lamb Curry (Boneless)", "Menu", 140.00), ("Chicken Curry", "Menu", 95.00),
            ("Bunny Chow (Lamb)", "Menu", 90.00), ("Bunny Chow (Beans)", "Menu", 55.00),
            ("Roti Roll (Chicken)", "Menu", 50.00), ("Samoosas (Mince - Dozen)", "Snack", 70.00),
            ("Samoosas (Potato - Dozen)", "Snack", 50.00), ("Chilli Bites (Daltjies)", "Snack", 40.00),
            ("Mother-in-Law Masala (1kg)", "Spice", 150.00), ("Kashmiri Chilli (1kg)", "Spice", 180.00),
            ("Turmeric / Borrie (1kg)", "Spice", 90.00), ("Jeera Powder (1kg)", "Spice", 120.00),
            ("Dhania Powder (1kg)", "Spice", 100.00), ("Garam Masala (500g)", "Spice", 85.00),
            ("Cinnamon Sticks (100g)", "Spice", 35.00), ("Elachi / Cardamom (100g)", "Spice", 60.00),
            ("Leaf Masala (200g)", "Spice", 45.00), ("Biryani Mix (Pack)", "Spice", 55.00)
        ]
        for n, c, p in items: self.cursor.execute("INSERT INTO items (name, category, price, stock, image_path) VALUES (?, ?, ?, 50, ?)", (n, c, p, img_path))

        names = ["Rahul Heeralal", "Thabo Mbeki", "Keshav Naidoo", "Precious Dlamini", "Johan van der Merwe", "Yusuf Patel", "Fatima Jaffer", "Sipho Nkosi", "Kyle Abrahams", "Nadia Govender", "Zainab Osman", "Charl Venter", "Bongiwe Zungu", "Mohammed Ally", "Priya Singh", "Lebo Molefe", "Wayne Smith", "Aisha Khan", "Devan Pillay", "Bianca Botha"]
        for n in names: self.cursor.execute("INSERT INTO customers (name, email, address, city) VALUES (?, ?, ?, ?)", (n, n.lower().replace(" ", ".")+"@mail.com", "42 Spice Route", "Durban"))
        self.conn.commit()
        
        i_ids = [r[0] for r in self.cursor.execute("SELECT id FROM items").fetchall()]
        c_ids = [r[0] for r in self.cursor.execute("SELECT id FROM customers").fetchall()]
        for _ in range(30):
            cid = random.choice(c_ids)
            date = (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d %H:%M:%S")
            self.cursor.execute("INSERT INTO orders (customer_id, date, status, total) VALUES (?, ?, ?, 0)", (cid, date, random.choice(["Delivered", "Ready", "Pending"])))
            oid = self.cursor.lastrowid; tot = 0
            for _ in range(random.randint(1, 4)):
                iid = random.choice(i_ids); qty = random.randint(1, 3); p = self.cursor.execute("SELECT price FROM items WHERE id=?", (iid,)).fetchone()[0]
                self.cursor.execute("INSERT INTO order_items VALUES (?, ?, ?, ?)", (oid, iid, qty, p*qty)); tot += p*qty
            self.cursor.execute("UPDATE orders SET total=? WHERE id=?", (tot, oid))
        self.conn.commit()

    def create_dummy_image(self, path, text, size, color):
        if not os.path.exists(path):
            img = Image.new('RGB', size, color); ImageDraw.Draw(img).text((20, 30), text, fill="white"); img.save(path)

    def fetch(self, q, p=()): self.cursor.execute(q, p); return self.cursor.fetchall()
    def execute(self, q, p=()): self.cursor.execute(q, p); self.conn.commit(); return self.cursor.lastrowid

db = DBManager()

class RenusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Renus Authentic Delights - Pro Manager")
        self.geometry("1400x900")
        self.logo_img = ctk.CTkImage(Image.open("assets/logo.png"), size=(40, 40))
        self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)
        
        self.create_sidebar()
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "gray10"))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.cart = {}
        self.show_new_order()

    def create_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0); sidebar.grid(row=0, column=0, sticky="nsew"); sidebar.grid_rowconfigure(10, weight=1)
        ctk.CTkLabel(sidebar, text="", image=self.logo_img).grid(row=0, column=0, pady=(30, 10))
        ctk.CTkLabel(sidebar, text="RENUS\nAUTHENTIC", font=("Arial", 20, "bold")).grid(row=1, column=0, pady=(0, 20))
        btns = [("New Order", self.show_new_order), ("Order History", self.show_history), ("Menu / Items", self.show_menu), ("Customers", self.show_customers)]
        for i, (t, c) in enumerate(btns): ctk.CTkButton(sidebar, text=t, command=c, fg_color="transparent", border_width=1, text_color=("gray10", "gray90")).grid(row=i+2, column=0, padx=15, pady=8, sticky="ew")
        switch = ctk.CTkSwitch(sidebar, text="Dark Mode", command=lambda: ctk.set_appearance_mode("Dark" if switch.get() else "Light")); switch.select(); switch.grid(row=11, column=0, pady=20)

    def add_header(self, title):
        head = ctk.CTkFrame(self.content, height=70, fg_color=("white", "#1f1f1f")); head.pack(fill="x")
        ctk.CTkLabel(head, text="", image=self.logo_img).pack(side="left", padx=20, pady=10)
        ctk.CTkLabel(head, text=title, font=("Arial", 26, "bold")).pack(side="left", pady=10)

    # --- TAB 1: NEW ORDER ---
    def show_new_order(self):
        for w in self.content.winfo_children(): w.destroy()
        self.add_header("New Order Point")
        split = ctk.CTkFrame(self.content, fg_color="transparent"); split.pack(fill="both", expand=True, padx=20, pady=20)
        menu = ctk.CTkFrame(split, fg_color="transparent"); menu.pack(side="left", fill="both", expand=True, padx=(0, 20))
        
        cats = ctk.CTkFrame(menu, fg_color="transparent"); cats.pack(fill="x", pady=10)
        self.cat_var = ctk.StringVar(value="All")
        for c in ["All", "Menu", "Spice", "Snack"]: ctk.CTkRadioButton(cats, text=c, variable=self.cat_var, value=c, command=lambda: self.load_grid(scroll)).pack(side="left", padx=10)
        
        scroll = ctk.CTkScrollableFrame(menu); scroll.pack(fill="both", expand=True); self.load_grid(scroll)
        
        cart = ctk.CTkFrame(split, width=400, fg_color=("white", "#2b2b2b")); cart.pack(side="right", fill="y")
        ctk.CTkLabel(cart, text="Current Order", font=("Arial", 18, "bold")).pack(pady=20)
        custs = db.fetch("SELECT id, name FROM customers ORDER BY name")
        self.cust_var = ctk.StringVar(value=f"{custs[0][0]} - {custs[0][1]}")
        ctk.CTkOptionMenu(cart, variable=self.cust_var, values=[f"{c[0]} - {c[1]}" for c in custs]).pack(fill="x", padx=20)
        
        self.cart_frame = ctk.CTkScrollableFrame(cart, fg_color="transparent"); self.cart_frame.pack(fill="both", expand=True, padx=10, pady=10)
        foot = ctk.CTkFrame(cart, fg_color="transparent"); foot.pack(fill="x", padx=20, pady=20)
        self.total_lbl = ctk.CTkLabel(foot, text="Total: R 0.00", font=("Arial", 22, "bold")); self.total_lbl.pack(pady=10)
        ctk.CTkButton(foot, text="CONFIRM ORDER", height=50, fg_color="#2CC985", font=("Arial", 16, "bold"), command=self.checkout).pack(fill="x")
        self.update_cart()

    def load_grid(self, parent):
        for w in parent.winfo_children(): w.destroy()
        cat = self.cat_var.get()
        q = "SELECT * FROM items" + (f" WHERE category='{cat}'" if cat != "All" else "")
        items = db.fetch(q)
        r, c = 0, 0
        for i in items:
            card = ctk.CTkFrame(parent, border_width=1, border_color="gray40"); card.grid(row=r, column=c, padx=10, pady=10, sticky="ew")
            try: ctk.CTkLabel(card, text="", image=ctk.CTkImage(Image.open(i[5]), size=(60,60))).pack(side="left", padx=10, pady=10)
            except: pass
            inf = ctk.CTkFrame(card, fg_color="transparent"); inf.pack(side="left", padx=5)
            ctk.CTkLabel(inf, text=i[1], font=("Arial", 14, "bold"), wraplength=120).pack(anchor="w")
            ctk.CTkLabel(inf, text=f"R {i[3]:.2f}", font=("Arial", 12)).pack(anchor="w")
            ctk.CTkButton(card, text="+", width=40, command=lambda x=i: self.add_cart(x)).pack(side="right", padx=10)
            c += 1
            if c > 1: c=0; r+=1

    def add_cart(self, item):
        if item[0] in self.cart: self.cart[item[0]]['qty'] += 1
        else: self.cart[item[0]] = {'name': item[1], 'price': item[3], 'qty': 1}
        self.update_cart()

    def update_cart(self):
        for w in self.cart_frame.winfo_children(): w.destroy()
        tot = 0
        for iid, d in self.cart.items():
            tot += d['price']*d['qty']; row = ctk.CTkFrame(self.cart_frame, fg_color=("gray95", "#333")); row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{d['name']} (x{d['qty']})", anchor="w").pack(side="left", padx=5)
            ctk.CTkLabel(row, text=f"R{d['price']*d['qty']:.2f}", anchor="e").pack(side="right", padx=5)
            ctk.CTkButton(row, text="x", width=20, fg_color="red", command=lambda x=iid: self.rem_cart(x)).pack(side="right", padx=5)
        self.total_lbl.configure(text=f"Total: R {tot:.2f}")

    def rem_cart(self, iid): del self.cart[iid]; self.update_cart()
    def checkout(self):
        if not self.cart: return
        cid = int(self.cust_var.get().split(" - ")[0]); tot = sum(d['price']*d['qty'] for d in self.cart.values())
        oid = db.execute("INSERT INTO orders (customer_id, date, total, status) VALUES (?, ?, ?, 'Pending')", (cid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tot))
        for iid, d in self.cart.items(): db.execute("INSERT INTO order_items VALUES (?, ?, ?, ?)", (oid, iid, d['qty'], d['price']*d['qty']))
        messagebox.showinfo("Success", f"Order #{oid} Placed!"); self.cart={}; self.update_cart()

    # --- TAB 2: HISTORY (WITH EDITING) ---
    def show_history(self):
        for w in self.content.winfo_children(): w.destroy()
        self.add_header("Order Management")
        main = ctk.CTkFrame(self.content, fg_color="transparent"); main.pack(fill="both", expand=True, padx=20, pady=20)
        left = ctk.CTkScrollableFrame(main); left.pack(side="left", fill="both", expand=True, padx=(0, 20))
        
        # Headers
        h = ctk.CTkFrame(left, height=40, fg_color="transparent"); h.pack(fill="x", pady=5)
        for t, w in [("ID",50), ("Customer",150), ("Date",150), ("Status",100), ("Total",80)]:
            ctk.CTkLabel(h, text=t, width=w, anchor="w", font=("Arial", 12, "bold")).pack(side="left", padx=10)

        right = ctk.CTkFrame(main, width=350, fg_color=("white", "#2b2b2b")); right.pack(side="right", fill="y")
        ctk.CTkLabel(right, text="Order Details", font=("Arial", 18, "bold")).pack(pady=20)
        det_lbl = ctk.CTkLabel(right, text="Select an order...", text_color="gray"); det_lbl.pack(pady=10)
        det_frame = ctk.CTkScrollableFrame(right, fg_color="transparent"); det_frame.pack(fill="both", expand=True, padx=10)
        pdf_btn = ctk.CTkButton(right, text="Download PDF Invoice", state="disabled", fg_color="#2CC985", command=lambda: self.gen_pdf(self.sel_oid)); pdf_btn.pack(fill="x", padx=20, pady=20)

        def load_details(oid):
            self.sel_oid = oid; pdf_btn.configure(state="normal"); det_lbl.configure(text=f"Order #{oid}", text_color=("black", "white"))
            for w in det_frame.winfo_children(): w.destroy()
            for n, q, s in db.fetch("SELECT i.name, oi.quantity, oi.subtotal FROM order_items oi JOIN items i ON oi.item_id = i.id WHERE oi.order_id=?", (oid,)):
                r = ctk.CTkFrame(det_frame, fg_color=("gray95", "#333")); r.pack(fill="x", pady=2)
                ctk.CTkLabel(r, text=f"{n} x{q}").pack(side="left", padx=5); ctk.CTkLabel(r, text=f"R{s:.2f}").pack(side="right", padx=5)

        for r in db.fetch("SELECT o.id, c.name, o.date, o.status, o.total FROM orders o JOIN customers c ON o.customer_id = c.id ORDER BY o.id DESC"):
            rf = ctk.CTkFrame(left, fg_color=("gray90", "#333"), corner_radius=8); rf.pack(fill="x", pady=4, padx=5)
            ctk.CTkLabel(rf, text=str(r[0]), width=50, anchor="w").pack(side="left", padx=10, pady=10)
            ctk.CTkLabel(rf, text=r[1], width=150, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(rf, text=r[2][:10], width=150, anchor="w").pack(side="left", padx=10)
            
            # Status badge
            cols = {"Pending": "orange", "Delivered": "#2CC985", "Ready": "#3B8ED0"}
            ctk.CTkLabel(rf, text=r[3], text_color="white", fg_color=cols.get(r[3], "gray"), corner_radius=5, width=80).pack(side="left", padx=10)
            ctk.CTkLabel(rf, text=f"R{r[4]:.2f}", width=80, anchor="e", font=("Arial", 12, "bold")).pack(side="left", padx=10)
            
            # View & Edit
            ctk.CTkButton(rf, text="View", width=50, height=25, command=lambda oid=r[0]: load_details(oid)).pack(side="right", padx=5)
            
            # Edit Button (Disabled if Delivered)
            is_locked = r[3] == "Delivered"
            edit_col = "gray" if is_locked else "#FBC02D"
            edit_cmd = (lambda: messagebox.showerror("Locked", "Cannot edit completed orders.")) if is_locked else (lambda oid=r[0]: self.edit_order_popup(oid))
            ctk.CTkButton(rf, text="Edit", width=50, height=25, fg_color=edit_col, text_color="black" if not is_locked else "white", command=edit_cmd).pack(side="right", padx=5)

    def edit_order_popup(self, oid):
        t = ctk.CTkToplevel(self); t.geometry("600x600"); t.title(f"Edit Order #{oid}"); t.grab_set()
        
        # Helper to load existing items
        self.edit_cart = {} # {iid: {name, price, qty}}
        existing = db.fetch("SELECT oi.item_id, i.name, i.price, oi.quantity FROM order_items oi JOIN items i ON oi.item_id = i.id WHERE oi.order_id=?", (oid,))
        for iid, name, price, qty in existing: self.edit_cart[iid] = {'name': name, 'price': price, 'qty': qty}

        # UI
        ctk.CTkLabel(t, text=f"Editing Order #{oid}", font=("Arial", 20, "bold")).pack(pady=10)
        
        # Add New Item Section
        add_f = ctk.CTkFrame(t); add_f.pack(fill="x", padx=20, pady=10)
        all_items = db.fetch("SELECT id, name, price FROM items")
        item_map = {f"{i[1]} (R{i[2]})": i for i in all_items}
        sel_var = ctk.StringVar(value=list(item_map.keys())[0])
        ctk.CTkOptionMenu(add_f, variable=sel_var, values=list(item_map.keys())).pack(side="left", padx=10, expand=True, fill="x")
        
        def add_new():
            raw = item_map[sel_var.get()] # (id, name, price)
            if raw[0] in self.edit_cart: self.edit_cart[raw[0]]['qty'] += 1
            else: self.edit_cart[raw[0]] = {'name': raw[1], 'price': raw[2], 'qty': 1}
            refresh_list()
        ctk.CTkButton(add_f, text="Add Item", width=80, command=add_new).pack(side="right", padx=10)

        # List of items
        list_f = ctk.CTkScrollableFrame(t); list_f.pack(fill="both", expand=True, padx=20, pady=10)

        def change_qty(iid, delta):
            self.edit_cart[iid]['qty'] += delta
            if self.edit_cart[iid]['qty'] <= 0: del self.edit_cart[iid]
            refresh_list()

        def refresh_list():
            for w in list_f.winfo_children(): w.destroy()
            grand = 0
            for iid, d in self.edit_cart.items():
                sub = d['qty'] * d['price']; grand += sub
                r = ctk.CTkFrame(list_f, fg_color=("gray90", "#333")); r.pack(fill="x", pady=2)
                ctk.CTkLabel(r, text=d['name'], anchor="w", width=200).pack(side="left", padx=10)
                ctk.CTkLabel(r, text=f"R{d['price']}", width=60).pack(side="left")
                
                # Controls
                ctrl = ctk.CTkFrame(r, fg_color="transparent"); ctrl.pack(side="right", padx=10)
                ctk.CTkButton(ctrl, text="-", width=30, command=lambda x=iid: change_qty(x, -1)).pack(side="left")
                ctk.CTkLabel(ctrl, text=str(d['qty']), width=30).pack(side="left")
                ctk.CTkButton(ctrl, text="+", width=30, command=lambda x=iid: change_qty(x, 1)).pack(side="left")
            
            lbl_total.configure(text=f"New Total: R {grand:.2f}")

        lbl_total = ctk.CTkLabel(t, text="New Total: R 0.00", font=("Arial", 18, "bold")); lbl_total.pack(pady=10)

        def save_changes():
            tot = sum(d['qty']*d['price'] for d in self.edit_cart.values())
            db.execute("DELETE FROM order_items WHERE order_id=?", (oid,)) # Clear old
            for iid, d in self.edit_cart.items():
                db.execute("INSERT INTO order_items VALUES (?, ?, ?, ?)", (oid, iid, d['qty'], d['price']*d['qty']))
            db.execute("UPDATE orders SET total=? WHERE id=?", (tot, oid))
            messagebox.showinfo("Success", "Order Updated!"); t.destroy(); self.show_history()

        ctk.CTkButton(t, text="SAVE CHANGES", fg_color="green", height=40, command=save_changes).pack(fill="x", padx=20, pady=20)
        refresh_list()

    def gen_pdf(self, oid):
        file = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"Invoice_Order_{oid}.pdf")
        if not file: return
        data = db.fetch("SELECT o.id, c.name, o.date, o.total, c.address, c.city FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id=?", (oid,))[0]
        items = db.fetch("SELECT i.name, oi.quantity, i.price, oi.subtotal FROM order_items oi JOIN items i ON oi.item_id = i.id WHERE oi.order_id=?", (oid,))
        c = canvas.Canvas(file, pagesize=letter)
        c.setFont("Helvetica-Bold", 20); c.drawString(50, 750, "RENUS AUTHENTIC DELIGHTS")
        c.setFont("Helvetica", 12)
        c.drawString(50, 720, f"Invoice #{data[0]}"); c.drawString(50, 700, f"Customer: {data[1]}")
        c.drawString(50, 680, f"Address: {data[4]}, {data[5]}"); c.drawString(50, 660, f"Date: {data[2]}")
        y = 620; c.drawString(50, y, "Item"); c.drawString(300, y, "Qty"); c.drawString(380, y, "Price"); c.drawString(480, y, "Total")
        c.line(50, y-5, 550, y-5); y -= 25
        for n, q, p, s in items: c.drawString(50, y, n[:35]); c.drawString(300, y, str(q)); c.drawString(380, y, f"R{p:.2f}"); c.drawString(480, y, f"R{s:.2f}"); y -= 20
        c.line(50, y-5, 550, y-5); c.setFont("Helvetica-Bold", 14); c.drawString(380, y-30, "Grand Total:"); c.drawString(480, y-30, f"R{data[3]:.2f}")
        c.save(); messagebox.showinfo("Success", "PDF Saved!")

    # --- OTHER TABS (MENU & CUSTOMERS) ---
    def show_menu(self):
        for w in self.content.winfo_children(): w.destroy()
        self.add_header("Menu Database")
        main = ctk.CTkFrame(self.content, fg_color="transparent"); main.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkButton(main, text="+ Add New Item", width=200, height=40, font=("Arial", 14, "bold"), command=lambda: self.item_popup(None)).pack(anchor="e", pady=(0, 10))
        scroll = ctk.CTkScrollableFrame(main); scroll.pack(fill="both", expand=True)
        for r in db.fetch("SELECT id, name, category, price FROM items"):
            card = ctk.CTkFrame(scroll, fg_color=("gray90", "#333"), corner_radius=8); card.pack(fill="x", pady=5, padx=5)
            ctk.CTkLabel(card, text=r[1], font=("Arial", 14, "bold"), width=250, anchor="w").pack(side="left", padx=20, pady=15)
            ctk.CTkLabel(card, text=r[2], width=100, anchor="w").pack(side="left", padx=10)
            ctk.CTkLabel(card, text=f"R{r[3]:.2f}", font=("Arial", 14, "bold"), width=100, anchor="w").pack(side="left", padx=10)
            ctk.CTkButton(card, text="Delete", fg_color="#E53935", width=60, command=lambda i=r[0]: self.del_item(i)).pack(side="right", padx=10)
            ctk.CTkButton(card, text="Edit", fg_color="#FBC02D", text_color="black", width=60, command=lambda i=r[0]: self.item_popup(i)).pack(side="right", padx=5)
    
    def item_popup(self, iid):
        t = ctk.CTkToplevel(self); t.geometry("300x400"); t.title("Item Details"); t.grab_set()
        ctk.CTkLabel(t, text="Name").pack(pady=5); e1 = ctk.CTkEntry(t); e1.pack()
        ctk.CTkLabel(t, text="Category (Menu/Spice/Snack)").pack(pady=5); e2 = ctk.CTkEntry(t); e2.pack()
        ctk.CTkLabel(t, text="Price").pack(pady=5); e3 = ctk.CTkEntry(t); e3.pack()
        if iid: d = db.fetch("SELECT name, category, price FROM items WHERE id=?", (iid,))[0]; e1.insert(0, d[0]); e2.insert(0, d[1]); e3.insert(0, str(d[2]))
        def save():
            path = os.path.abspath("assets/placeholder.png")
            if iid: db.execute("UPDATE items SET name=?, category=?, price=? WHERE id=?", (e1.get(), e2.get(), float(e3.get()), iid))
            else: db.execute("INSERT INTO items (name, category, price, stock, image_path) VALUES (?, ?, ?, 50, ?)", (e1.get(), e2.get(), float(e3.get()), path))
            t.destroy(); self.show_menu()
        ctk.CTkButton(t, text="Save Item", command=save, fg_color="green").pack(pady=20)
    def del_item(self, iid):
        if messagebox.askyesno("Confirm", "Delete item?"): db.execute("DELETE FROM items WHERE id=?", (iid,)); self.show_menu()

    def show_customers(self):
        for w in self.content.winfo_children(): w.destroy()
        self.add_header("Customer Database")
        main = ctk.CTkFrame(self.content, fg_color="transparent"); main.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkButton(main, text="+ Add Customer", width=200, height=40, font=("Arial", 14, "bold"), command=lambda: self.cust_popup(None)).pack(anchor="e", pady=(0, 10))
        scroll = ctk.CTkScrollableFrame(main); scroll.pack(fill="both", expand=True)
        for r in db.fetch("SELECT id, name, email, address, city FROM customers"):
            card = ctk.CTkFrame(scroll, fg_color=("gray90", "#333"), corner_radius=8); card.pack(fill="x", pady=5, padx=5)
            info = ctk.CTkFrame(card, fg_color="transparent"); info.pack(side="left", padx=20, pady=10)
            ctk.CTkLabel(info, text=r[1], font=("Arial", 14, "bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=r[2], font=("Arial", 12), text_color="gray", anchor="w").pack(anchor="w")
            addr = ctk.CTkFrame(card, fg_color="transparent"); addr.pack(side="left", padx=20)
            ctk.CTkLabel(addr, text=r[4] or "No City", font=("Arial", 12, "bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(addr, text=r[3] or "No Address", font=("Arial", 11), text_color="gray", anchor="w").pack(anchor="w")
            ctk.CTkButton(card, text="Delete", fg_color="#E53935", width=60, command=lambda i=r[0]: self.del_cust(i)).pack(side="right", padx=10)
            ctk.CTkButton(card, text="Edit", fg_color="#FBC02D", text_color="black", width=60, command=lambda i=r[0]: self.cust_popup(i)).pack(side="right", padx=5)
    def cust_popup(self, cid):
        t = ctk.CTkToplevel(self); t.geometry("300x450"); t.title("Customer Details"); t.grab_set()
        ctk.CTkLabel(t, text="Name").pack(pady=2); e1 = ctk.CTkEntry(t); e1.pack()
        ctk.CTkLabel(t, text="Email").pack(pady=2); e2 = ctk.CTkEntry(t); e2.pack()
        ctk.CTkLabel(t, text="Address").pack(pady=2); e3 = ctk.CTkEntry(t); e3.pack()
        ctk.CTkLabel(t, text="City").pack(pady=2); e4 = ctk.CTkEntry(t); e4.pack()
        if cid: d = db.fetch("SELECT name, email, address, city FROM customers WHERE id=?", (cid,))[0]; e1.insert(0, d[0]); e2.insert(0, d[1]); e3.insert(0, d[2] or ""); e4.insert(0, d[3] or "")
        def save():
            if cid: db.execute("UPDATE customers SET name=?, email=?, address=?, city=? WHERE id=?", (e1.get(), e2.get(), e3.get(), e4.get(), cid))
            else: db.execute("INSERT INTO customers (name, email, address, city) VALUES (?, ?, ?, ?)", (e1.get(), e2.get(), e3.get(), e4.get()))
            t.destroy(); self.show_customers()
        ctk.CTkButton(t, text="Save", command=save, fg_color="green").pack(pady=20)
    def del_cust(self, cid):
        if messagebox.askyesno("Confirm", "Delete?"): db.execute("DELETE FROM customers WHERE id=?", (cid,)); self.show_customers()

if __name__ == "__main__":
    app = RenusApp()
    app.mainloop()