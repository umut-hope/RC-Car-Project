import socket, threading, time, datetime, sqlite3, os
import customtkinter as ctk
import tkinter as tk

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BG       = "#111113"
BG_HDR   = "#0c0c0e"
CARD     = "#1c1c1f"
CARD2    = "#171719"
CARD3    = "#141416"
BORDER   = "#2c2c30"
DIM      = "#3d3d42"
RED      = "#e63946"
RED_D    = "#c1121f"
RED_DIM  = "#3a080a"
AMBER    = "#f5a623"
AMBER_D  = "#b87a0f"
AMBER_DIM= "#2a1e06"
GREEN    = "#22c55e"
GREEN_D  = "#052e16"
DANGER   = "#e63946"
TXT_W    = "#f0f0f0"
TXT_G    = "#a0a0a8"
TXT_DIM  = "#5c5c63"
BTN_BG   = "#1a1a1e"
BTN_HOV  = "#222226"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "race_logs.db")


def init_db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT,
            started_at    TEXT,
            ended_at      TEXT,
            total_records INTEGER DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS telemetry(
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            ts_ms      INTEGER,
            ts         TEXT,
            s_front    INTEGER, s_front_l INTEGER, s_front_r INTEGER,
            s_side_l   INTEGER, s_side_r  INTEGER, s_rear    INTEGER,
            speed      REAL,    battery_v REAL,
            imu_ax     REAL,    imu_ay    REAL,    imu_az    REAL,
            enc_fl     REAL,    enc_fr    REAL,
            enc_rl     REAL,    enc_rr    REAL,
            status     TEXT,    mode      INTEGER,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    """)
    con.commit()
    return con


class CarUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("RC CAR — Mission Control v5.0")
        self.geometry("1350x800")
        self.minsize(1100, 680)
        self.configure(fg_color=BG)

        self.pi_ip   = "192.168.1.3"
        self.pi_port = 5005
        self.sock      = None
        self.connected = False

        self.manual_mode  = False
        self.active_mode  = 2
        self.keys_pressed = set()
        self.last_cmd     = None
        self.throttle_val = 0

        self.dropdown_open = False
        self.dropdown_win  = None

        self.mode_data = {
            "1": ("🐢  Slow & Safe",       GREEN),
            "2": ("⚖️  Balanced",          AMBER),
            "3": ("🔥  Fast & Aggressive",  RED),
        }

        self.db            = init_db()
        self.session_id    = None
        self.session_start = None
        self.record_count  = 0
        self.recording     = False

        self.active_sensors = {"FRONT", "FRONT_LEFT", "FRONT_RIGHT",
                               "SIDE_LEFT", "SIDE_RIGHT", "REAR"}

        self._latest_raw       = None
        self._ui_update_pending = False

        self._build_ui()
        self._bind_keys()
        self._update_clock()

        threading.Thread(target=self._connect_to_pi, daemon=True).start()
        threading.Thread(target=self._manual_loop,   daemon=True).start()

    def _build_ui(self):
        self._build_header()
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(8, 5))
        body.columnconfigure(0, weight=32)
        body.columnconfigure(1, weight=30)
        body.columnconfigure(2, weight=38)
        body.rowconfigure(0, weight=1)
        self._build_left_col(body)
        self._build_middle_col(body)
        self._build_right_col(body)
        self._build_footer()

    def _build_header(self):
        h = ctk.CTkFrame(self, height=52, fg_color=BG_HDR, corner_radius=0)
        h.pack(fill="x")
        h.pack_propagate(False)

        brand = ctk.CTkFrame(h, fg_color="transparent")
        brand.pack(side="left", padx=16)
        ctk.CTkLabel(brand, text="🛰️ RC",
                     font=ctk.CTkFont(size=20, weight="bold"), text_color=RED).pack(side="left")
        ctk.CTkLabel(brand, text=" MISSION CONTROL",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=TXT_W).pack(side="left")
        ctk.CTkLabel(brand, text="  v5.0",
                     font=ctk.CTkFont(size=10), text_color=DIM).pack(side="left")

        rh = ctk.CTkFrame(h, fg_color="transparent")
        rh.pack(side="right", padx=12, pady=7)

        self.conn_dot = ctk.CTkLabel(rh, text="⬤", text_color=DANGER,
                                     font=ctk.CTkFont(size=12))
        self.conn_dot.pack(side="left", padx=(0, 4))
        self.conn_label = ctk.CTkLabel(rh, text="No Connection",
                                       font=ctk.CTkFont(size=10), text_color=TXT_DIM)
        self.conn_label.pack(side="left", padx=(0, 16))

        self.session_btn = ctk.CTkButton(
            rh, text="⏺  Start Recording", width=155, height=32,
            fg_color=RED_DIM, hover_color="#4a0a0d",
            border_width=1, border_color="#7f1d1d",
            font=ctk.CTkFont(size=11), text_color=TXT_G,
            command=self._toggle_session,
        )
        self.session_btn.pack(side="left", padx=(0, 6))

        self.session_timer_lbl = ctk.CTkLabel(rh, text="00:00:00",
                                               font=ctk.CTkFont(size=11, weight="bold"),
                                               text_color=DIM)
        self.session_timer_lbl.pack(side="left", padx=(0, 16))

        self.manual_btn = ctk.CTkButton(
            rh, text="🕹️  Manual: OFF", width=160, height=32,
            fg_color=BTN_BG, hover_color=BTN_HOV,
            border_width=1, border_color=BORDER,
            font=ctk.CTkFont(size=11), text_color=TXT_G,
            command=self._toggle_manual,
        )
        self.manual_btn.pack(side="left", padx=(0, 8))



    def _build_left_col(self, parent):
        col = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12,
                           border_width=1, border_color=BORDER)
        col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(col, text="SENSOR RADAR MATRIX",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=RED).pack(pady=(12, 4))

        self._divider(col)

        self.canvas = tk.Canvas(col, width=270, height=295, bg=CARD, highlightthickness=0)
        self.canvas.pack(pady=4)
        self._draw_vehicle_diagram()

        self._divider(col)

        sf = ctk.CTkFrame(col, fg_color="transparent")
        sf.pack(fill="x", padx=12, pady=(2, 12))

        sensor_defs = [
            ("FRONT",       "FRONT CENTER"),
            ("FRONT_LEFT",  "FRONT LEFT DIAGONAL"),
            ("FRONT_RIGHT", "FRONT RIGHT DIAGONAL"),
            ("SIDE_LEFT",   "LEFT SIDE WALL"),
            ("SIDE_RIGHT",  "RIGHT SIDE WALL"),
            ("REAR",        "REAR SAFETY"),
        ]
        self.sensor_labels = {}
        for key, name in sensor_defs:
            active = key in self.active_sensors
            row = ctk.CTkFrame(sf, fg_color=CARD2 if active else CARD3,
                               corner_radius=5, height=27)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text="" if active else "🔌",
                         font=ctk.CTkFont(size=9), text_color=DIM, width=16).pack(side="left", padx=2)
            ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=10),
                         text_color=TXT_G if active else DIM, anchor="w").pack(side="left", fill="x", expand=True)
            val = ctk.CTkLabel(row, text="—" if active else "NOT CONNECTED",
                               font=ctk.CTkFont(size=9, weight="bold"),
                               text_color=DIM if active else "#2a2a2e", width=92)
            val.pack(side="right", padx=5)
            self.sensor_labels[key] = val

    def _build_middle_col(self, parent):
        col = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12,
                           border_width=1, border_color=BORDER)
        col.grid(row=0, column=1, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(col, text="VEHICLE CONTROL PANEL",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=RED).pack(pady=(12, 1))
        ctk.CTkLabel(col, text="WASD = ileri/geri/dönüş  ·  Space = dur",
                     font=ctk.CTkFont(size=8), text_color=TXT_DIM).pack()

        self._divider(col)

        ctk.CTkLabel(col, text="📍 DIRECTION  ·  WASD / Space = Stop",
                     font=ctk.CTkFont(size=9, weight="bold"), text_color=TXT_DIM).pack()

        dpad_area = ctk.CTkFrame(col, fg_color="transparent")
        dpad_area.pack(fill="both", expand=True)

        dpad = ctk.CTkFrame(dpad_area, fg_color="transparent")
        dpad.place(relx=0.5, rely=0.5, anchor="center")

        BS = dict(width=68, height=68, corner_radius=10,
                  font=ctk.CTkFont(size=17), fg_color=BTN_BG,
                  hover_color="#2a2a2e", border_width=2,
                  border_color=BORDER, text_color=TXT_G)

        r0 = ctk.CTkFrame(dpad, fg_color="transparent")
        r0.pack()
        self.btn_fwd = ctk.CTkButton(r0, text="▲\nW", **BS,
                                     command=lambda: self._btn_manual("W"))
        self.btn_fwd.pack(padx=4, pady=3)

        r1 = ctk.CTkFrame(dpad, fg_color="transparent")
        r1.pack()
        self.btn_left = ctk.CTkButton(r1, text="◀\nA", **BS,
                                      command=lambda: self._btn_manual("A"))
        self.btn_left.pack(side="left", padx=4, pady=3)
        self.btn_stop = ctk.CTkButton(r1, text="⏹\nX", width=68, height=68,
                                      corner_radius=10, font=ctk.CTkFont(size=14),
                                      text_color=TXT_G, fg_color=RED_DIM,
                                      hover_color="#4a0a0d", border_width=2,
                                      border_color="#7f1d1d",
                                      command=lambda: self._btn_manual("X"))
        self.btn_stop.pack(side="left", padx=4, pady=3)
        self.btn_right = ctk.CTkButton(r1, text="▶\nD", **BS,
                                       command=lambda: self._btn_manual("D"))
        self.btn_right.pack(side="left", padx=4, pady=3)

        r2 = ctk.CTkFrame(dpad, fg_color="transparent")
        r2.pack()
        self.btn_bwd = ctk.CTkButton(r2, text="▼\nS", **BS,
                                     command=lambda: self._btn_manual("S"))
        self.btn_bwd.pack(padx=4, pady=3)

        self.manual_hint = ctk.CTkLabel(col,
                                        text="⚠️  Manual mode OFF — activate from top right",
                                        font=ctk.CTkFont(size=9), text_color=DIM)
        self.manual_hint.pack(pady=(0, 10))

    def _build_right_col(self, parent):
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.grid(row=0, column=2, sticky="nsew")


        nav = ctk.CTkFrame(col, fg_color=CARD, corner_radius=12,
                           border_width=1, border_color=BORDER, height=55)
        nav.pack(fill="x", pady=(0, 6))
        nav.pack_propagate(False)
        ctk.CTkLabel(nav, text="NAVIGATION STATUS",
                     font=ctk.CTkFont(size=9), text_color=TXT_DIM).pack(pady=(10, 2))
        self.mode_label = ctk.CTkLabel(nav, text="MODE: —",
                                        font=ctk.CTkFont(size=9), text_color=DIM)
        self.mode_label.pack(pady=(0, 8))




        enc = ctk.CTkFrame(col, fg_color=CARD, corner_radius=12,
                            border_width=1, border_color=BORDER)
        enc.pack(fill="x", pady=(0, 6))
        enc_inner = ctk.CTkFrame(enc, fg_color="transparent")
        enc_inner.pack(fill="x", padx=14, pady=10)
        enc_hdr = ctk.CTkFrame(enc_inner, fg_color="transparent")
        enc_hdr.pack(fill="x")
        ctk.CTkLabel(enc_hdr, text="⚙️ WHEEL ENCODERS",
                     font=ctk.CTkFont(size=10, weight="bold"), text_color=TXT_G).pack(side="left")
        ctk.CTkLabel(enc_hdr, text="4× RPM",
                     font=ctk.CTkFont(size=8), text_color=DIM).pack(side="right")
        enc_row = ctk.CTkFrame(enc_inner, fg_color="transparent")
        enc_row.pack(fill="x", pady=(8, 0))
        self.enc_labels = {}
        for pos in ["FL", "FR", "RL", "RR"]:
            cell = ctk.CTkFrame(enc_row, fg_color=CARD2, corner_radius=8,
                                border_width=1, border_color=BORDER)
            cell.pack(side="left", fill="x", expand=True, padx=2)
            ctk.CTkLabel(cell, text=pos, font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=RED).pack(pady=(6, 0))
            rpm_l = ctk.CTkLabel(cell, text="0",
                                 font=ctk.CTkFont(size=18, weight="bold"), text_color=DIM)
            rpm_l.pack()
            ctk.CTkLabel(cell, text="RPM", font=ctk.CTkFont(size=6),
                         text_color=TXT_DIM).pack()
            bar = ctk.CTkProgressBar(cell, height=4, corner_radius=2,
                                      progress_color=GREEN, fg_color=CARD3)
            bar.set(0)
            bar.pack(fill="x", padx=6, pady=(3, 1))
            spd_l = ctk.CTkLabel(cell, text="0.0 km/h",
                                 font=ctk.CTkFont(size=7), text_color=TXT_DIM)
            spd_l.pack(pady=(0, 5))
            self.enc_labels[pos] = (rpm_l, bar, spd_l)

        log_card = ctk.CTkFrame(col, fg_color=CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER)
        log_card.pack(fill="both", expand=True)
        log_inner = ctk.CTkFrame(log_card, fg_color="transparent")
        log_inner.pack(fill="both", expand=True, padx=14, pady=10)

        log_hdr = ctk.CTkFrame(log_inner, fg_color="transparent")
        log_hdr.pack(fill="x")
        ctk.CTkLabel(log_hdr, text="💾 DATA RECORDING STATUS",
                     font=ctk.CTkFont(size=10, weight="bold"), text_color=TXT_G).pack(side="left")
        ctk.CTkLabel(log_hdr, text="race_logs.db",
                     font=ctk.CTkFont(size=8), text_color=DIM).pack(side="right")

        stat_row = ctk.CTkFrame(log_inner, fg_color="transparent")
        stat_row.pack(fill="x", pady=6)
        self.record_lbl = ctk.CTkLabel(stat_row, text="0",
                                        font=ctk.CTkFont(size=30, weight="bold"), text_color=DIM)
        self.record_lbl.pack(side="left")
        ctk.CTkLabel(stat_row, text="  records — this session",
                     font=ctk.CTkFont(size=10), text_color=TXT_DIM).pack(side="left", pady=10)

        self.db_status_lbl = ctk.CTkLabel(log_inner, text="💡 Press ⏺ to start recording",
                                           font=ctk.CTkFont(size=9), text_color=TXT_DIM, wraplength=380)
        self.db_status_lbl.pack(anchor="w")
        ctk.CTkLabel(log_inner, text="📊 Race analysis → python dashboard.py",
                     font=ctk.CTkFont(size=8), text_color=DIM).pack(anchor="w", pady=(4, 0))

    def _build_footer(self):
        f = ctk.CTkFrame(self, height=24, fg_color=BG_HDR, corner_radius=0)
        f.pack(fill="x")
        f.pack_propagate(False)
        ctk.CTkLabel(f, text=f"📡  Pi: {self.pi_ip}:{self.pi_port}  |  💾  {DB_PATH}",
                     font=ctk.CTkFont(size=8), text_color=DIM).pack(side="left", padx=12)
        self.clock_lbl = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=8), text_color=DIM)
        self.clock_lbl.pack(side="right", padx=12)

    def _divider(self, p):
        ctk.CTkFrame(p, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=5)

    def _update_clock(self):
        now = datetime.datetime.now()
        self.clock_lbl.configure(text=f"🕐  {now:%H:%M:%S}")
        if self.recording and self.session_start:
            elapsed = now - self.session_start
            total_s = int(elapsed.total_seconds())
            h, r = divmod(total_s, 3600)
            m, s = divmod(r, 60)
            self.session_timer_lbl.configure(text=f"{h:02d}:{m:02d}:{s:02d}", text_color=GREEN)
        self.after(1000, self._update_clock)

    def _draw_vehicle_diagram(self):
        c  = self.canvas
        c.delete("all")
        cx, cy = 135, 148

        for x in range(0, 271, 22):
            c.create_line(x, 0, x, 295, fill="#181818", width=1)
        for y in range(0, 296, 22):
            c.create_line(0, y, 270, y, fill="#181818", width=1)

        c.create_rectangle(cx-34, cy-68, cx+34, cy+68, fill="#1c1c20", outline=RED, width=2)
        c.create_rectangle(cx-24, cy-50, cx+24, cy+50, fill="#161618", outline=RED_D, width=1)
        c.create_line(cx-18, cy-45, cx+18, cy-45, fill=RED_D, width=1)

        for wx, wy, wh in [(cx-47, cy-52, 26), (cx+37, cy-52, 26),
                            (cx-47, cy+26, 26), (cx+37, cy+26, 26)]:
            c.create_rectangle(wx, wy, wx+10, wy+wh, fill="#1e1818", outline="#3a2a2a", width=1)

        c.create_polygon(cx, cy-76, cx-8, cy-62, cx+8, cy-62, fill=RED, outline=RED)

        r = 8
        self.sv_front       = c.create_oval(cx-r,  cy-92,     cx+r,      cy-92+r*2,  fill=BORDER, outline=DIM,     width=2)
        self.sv_front_left  = c.create_oval(cx-70, cy-88,     cx-70+r*2, cy-88+r*2,  fill=BORDER, outline=DIM,     width=2)
        self.sv_front_right = c.create_oval(cx+54, cy-88,     cx+54+r*2, cy-88+r*2,  fill=BORDER, outline=DIM,     width=2)
        self.sv_side_left   = c.create_oval(cx-94, cy-r,      cx-94+r*2, cy+r,        fill=BORDER, outline=DIM,     width=2)
        self.sv_side_right  = c.create_oval(cx+78, cy-r,      cx+78+r*2, cy+r,        fill=BORDER, outline=DIM,     width=2)
        self.sv_back        = c.create_oval(cx-r,  cy+76,     cx+r,      cy+76+r*2,  fill=DANGER, outline="#ff6b6b",width=2)

        lbl = dict(fill=TXT_DIM, font=("Courier", 6, "bold"))
        c.create_text(cx,     cy-105, text="FWD",    **lbl)
        c.create_text(cx-72,  cy-100, text="FWD-L",  **lbl)
        c.create_text(cx+70,  cy-100, text="FWD-R",  **lbl)
        c.create_text(cx-103, cy,     text="SIDE\nL", **lbl)
        c.create_text(cx+103, cy,     text="SIDE\nR", **lbl)
        c.create_text(cx,     cy+100, text="REAR",    **{**lbl, "fill": TXT_G})

        wc = "#1a1a1e"
        c.create_line(cx, cy-68,    cx, cy-92,       fill=wc, dash=(3, 3))
        c.create_line(cx-34, cy-60, cx-62, cy-82,    fill=wc, dash=(3, 3))
        c.create_line(cx+34, cy-60, cx+56, cy-82,    fill=wc, dash=(3, 3))
        c.create_line(cx-34, cy,    cx-92, cy,        fill=wc, dash=(3, 3))
        c.create_line(cx+34, cy,    cx+80, cy,        fill=wc, dash=(3, 3))
        c.create_line(cx, cy+68,    cx, cy+78,        fill=wc, dash=(3, 3))

        c.create_text(cx, 12, text="[ TEST MODE ]", fill=AMBER_D, font=("Courier", 7, "bold"))

    def _update_sensor_diagram(self, vals):
        mapping = {
            "FRONT":       self.sv_front,
            "FRONT_LEFT":  self.sv_front_left,
            "FRONT_RIGHT": self.sv_front_right,
            "SIDE_LEFT":   self.sv_side_left,
            "SIDE_RIGHT":  self.sv_side_right,
            "REAR":        self.sv_back,
        }
        for key, oval in mapping.items():
            if key not in self.active_sensors:
                self.canvas.itemconfig(oval, fill=BORDER, outline=DIM)
            elif vals.get(key, "0") == "1":
                self.canvas.itemconfig(oval, fill=DANGER, outline="#ff6b6b")
            else:
                self.canvas.itemconfig(oval, fill=GREEN, outline="#86efac")

    def _toggle_session(self):
        if not self.recording:
            now  = datetime.datetime.now()
            name = f"Session {now:%Y-%m-%d %H:%M:%S}"
            cur  = self.db.execute("INSERT INTO sessions(name, started_at) VALUES(?,?)",
                                   (name, now.isoformat()))
            self.db.commit()
            self.session_id    = cur.lastrowid
            self.session_start = now
            self.record_count  = 0
            self.recording     = True
            self.session_btn.configure(text="⏹  Stop Recording",
                                       fg_color=GREEN_D, border_color=GREEN, text_color=GREEN)
            self.record_lbl.configure(text_color=GREEN)
            self.db_status_lbl.configure(
                text=f"✅  Recording active — Session #{self.session_id}: {name}",
                text_color=GREEN)
        else:
            now = datetime.datetime.now()
            self.db.execute("UPDATE sessions SET ended_at=?, total_records=? WHERE id=?",
                            (now.isoformat(), self.record_count, self.session_id))
            self.db.commit()
            self.recording  = False
            self.session_btn.configure(text="⏺  Start Recording",
                                       fg_color=RED_DIM, border_color="#7f1d1d", text_color=TXT_G)
            self.session_timer_lbl.configure(text_color=DIM)
            self.db_status_lbl.configure(
                text=f"💾  {self.record_count:,} records saved — analysis: python dashboard.py",
                text_color=AMBER)
            self.session_id   = None
            self.record_count = 0
            self.record_lbl.configure(text="0", text_color=DIM)

    def _log_telemetry(self, front, fl, fr, sl, sr, rear,
                       speed, bat, ax, ay, az, enc_fl, enc_fr, enc_rl, enc_rr, status, mode):
        if not self.recording or not self.session_id:
            return
        try:
            ts_ms = int(time.time() * 1000)
            ts    = datetime.datetime.now().isoformat()
            self.db.execute(
                """INSERT INTO telemetry(
                    session_id, ts_ms, ts,
                    s_front, s_front_l, s_front_r, s_side_l, s_side_r, s_rear,
                    speed, battery_v, imu_ax, imu_ay, imu_az,
                    enc_fl, enc_fr, enc_rl, enc_rr, status, mode
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.session_id, ts_ms, ts,
                 int(front), int(fl), int(fr), int(sl), int(sr), int(rear),
                 speed, bat, ax, ay, az, enc_fl, enc_fr, enc_rl, enc_rr, status, mode),
            )
            self.db.commit()
            self.record_count += 1
            self.record_lbl.configure(text=f"{self.record_count:,}")
        except Exception as e:
            print(f"[DB ERROR] {e}")

    def _throttle_change(self, val):
        self.throttle_val = int(val)
        self.thr_val_lbl.configure(text=f"{self.throttle_val} %")
        if self.manual_mode:
            self._send(f"THROTTLE:{self.throttle_val}")


    def _toggle_dropdown(self):
        if self.dropdown_open:
            self._close_dropdown()
            return
        self.dropdown_win = ctk.CTkToplevel(self)
        self.dropdown_win.overrideredirect(True)
        self.dropdown_win.attributes("-topmost", True)
        self.dropdown_win.configure(fg_color=CARD3)
        x = self.mode_btn.winfo_rootx()
        y = self.mode_btn.winfo_rooty() + self.mode_btn.winfo_height() + 4
        self.dropdown_win.geometry(f"215x168+{x}+{y}")
        border = ctk.CTkFrame(self.dropdown_win, fg_color=CARD3,
                               border_width=1, border_color=RED, corner_radius=10)
        border.pack(fill="both", expand=True, padx=1, pady=1)
        for mid, (lbl, col) in self.mode_data.items():
            ctk.CTkButton(border, text=lbl, height=50, anchor="w",
                          fg_color="transparent", hover_color=BTN_BG,
                          border_width=0, font=ctk.CTkFont(size=12), text_color=TXT_G,
                          command=lambda m=mid, l=lbl: self._set_mode(m, l)).pack(fill="x", padx=6, pady=2)
        self.dropdown_open = True
        self.dropdown_win.bind("<FocusOut>", lambda e: self._close_dropdown())
        self.dropdown_win.focus_set()

    def _close_dropdown(self):
        if self.dropdown_win:
            try: self.dropdown_win.destroy()
            except: pass
        self.dropdown_open = False
        self.dropdown_win  = None

    def _set_mode(self, mid, lbl):
        self._close_dropdown()
        self.active_mode = int(mid)
        self.mode_btn.configure(text=f"{lbl}  ▾")
        self.mode_label.configure(text=f"MODE: {lbl}")
        self._send(f"{mid}")

    def _toggle_manual(self):
        self.manual_mode = not self.manual_mode
        if self.manual_mode:
            self.manual_btn.configure(text="🕹️  Manual: ON",
                                      fg_color=GREEN_D, border_color=GREEN, text_color=GREEN)
            self.manual_hint.configure(text="✅  Manual mode ACTIVE", text_color=GREEN)
            self._send("M")
        else:
            self.manual_btn.configure(text="🕹️  Manual: OFF",
                                      fg_color=BTN_BG, border_color=BORDER, text_color=TXT_G)
            self.manual_hint.configure(text="⚠️  Manual mode OFF — activate from top right",
                                       text_color=DIM)
            self._send(f"{self.active_mode}")

    def _bind_keys(self):
        for ch in ["w", "a", "s", "d", "W", "A", "S", "D"]:
            self.bind(f"<KeyPress-{ch}>",   lambda e, k=ch.upper(): self._kp(k))
            self.bind(f"<KeyRelease-{ch}>", lambda e, k=ch.upper(): self._kr(k))
        self.bind("<KeyPress-space>",   lambda e: self._kp("X"))
        self.bind("<KeyRelease-space>", lambda e: self._kr("X"))

    def _kp(self, k):
        if not self.manual_mode: return
        self.keys_pressed.add(k)
        self._btn_hl(k, True)

    def _kr(self, k):
        self.keys_pressed.discard(k)
        self._btn_hl(k, False)
        if self.manual_mode and not self.keys_pressed:
            self._send("M_X")
            self.last_cmd = None

    def _btn_hl(self, k, on):
        m = {"W": self.btn_fwd, "A": self.btn_left, "S": self.btn_bwd,
             "D": self.btn_right, "X": self.btn_stop}
        b = m.get(k)
        if not b: return
        if on:
            if k == "X": b.configure(fg_color="#7a0d10", border_color=RED)
            else:         b.configure(fg_color="#3a2020", border_color=AMBER)
        else:
            if k == "X": b.configure(fg_color=RED_DIM,  border_color="#7f1d1d")
            else:         b.configure(fg_color=BTN_BG,   border_color=BORDER)

    def _btn_manual(self, cmd):
        if not self.manual_mode: return
        self._send(f"M_{cmd}")

    def _manual_loop(self):
        while True:
            if self.manual_mode and self.keys_pressed:
                if "X" in self.keys_pressed:
                    self._send("M_X")
                    self.last_cmd = "X"
                else:
                    w = "W" in self.keys_pressed
                    s = "S" in self.keys_pressed
                    a = "A" in self.keys_pressed
                    d = "D" in self.keys_pressed
                    if   w and a: cmd = "WA"
                    elif w and d: cmd = "WD"
                    elif s and a: cmd = "SA"
                    elif s and d: cmd = "SD"
                    elif w:       cmd = "W"
                    elif s:       cmd = "S"
                    elif a:       cmd = "A"
                    elif d:       cmd = "D"
                    else:         cmd = None
                    if cmd and cmd != self.last_cmd:
                        self._send(f"M_{cmd}")
                        self.last_cmd = cmd
            time.sleep(0.06)

    def _send(self, msg):
        if self.connected and self.sock:
            try: self.sock.send(f"{msg}\n".encode())
            except: pass

    def _connect_to_pi(self):
        while not self.connected:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect((self.pi_ip, self.pi_port))
                s.settimeout(None)
                self.sock = s
                self.connected = True
                self.conn_dot.configure(text_color=GREEN)
                self.conn_label.configure(text="Connected ✔", text_color=GREEN)
                threading.Thread(target=self._read_loop, daemon=True).start()
            except:
                self.conn_dot.configure(text_color=DANGER)
                self.conn_label.configure(text="Searching...", text_color=TXT_DIM)
                time.sleep(2)

    def _read_loop(self):
        buf = ""
        while self.connected:
            try:
                chunk = self.sock.recv(4096).decode("utf-8", errors="replace")
                if not chunk: break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._latest_raw = line
                        if not self._ui_update_pending:
                            self._ui_update_pending = True
                            self.after(50, self._schedule_ui_update)
            except: break
        self.connected = False
        try:
            self.conn_dot.configure(text_color=DANGER)
            self.conn_label.configure(text="Disconnected ❌", text_color=DANGER)
        except: pass
        self._connect_to_pi()

    def _schedule_ui_update(self):
        self._ui_update_pending = False
        if self._latest_raw:
            self._process(self._latest_raw)
            self._latest_raw = None

    def _process(self, raw):
        try:
            p = [x.strip() for x in raw.split(",")]
            if len(p) < 7: return

            front, fl, fr, sl, sr, rear = p[0], p[1], p[2], p[3], p[4], p[5]
            status = p[6]
            mode   = int(p[7])    if len(p) > 7  else self.active_mode
            speed  = float(p[8])  if len(p) > 8  else 0.0
            bat    = float(p[9])  if len(p) > 9  else 0.0

            vals = {"FRONT": front, "FRONT_LEFT": fl, "FRONT_RIGHT": fr,
                    "SIDE_LEFT": sl, "SIDE_RIGHT": sr, "REAR": rear}

            for key, v in vals.items():
                if key not in self.active_sensors: continue
                self.sensor_labels[key].configure(
                    text="🟥 OBSTACLE" if v == "1" else "🟩 CLEAR",
                    text_color=DANGER if v == "1" else GREEN,
                )
            self._update_sensor_diagram(vals)

            enc_fl = float(p[10]) if len(p) > 10 else 0.0
            enc_fr = float(p[11]) if len(p) > 11 else 0.0
            enc_rl = float(p[12]) if len(p) > 12 else 0.0
            enc_rr = float(p[13]) if len(p) > 13 else 0.0

            ax = ay = az = 0.0
            self._log_telemetry(front, fl, fr, sl, sr, rear,
                                speed, 0.0, ax, ay, az,
                                enc_fl, enc_fr, enc_rl, enc_rr, status, mode)

            MAX_RPM  = 3000.0
            WHL_CIRC = 0.22
            for key, rpm_v in [("FL", enc_fl), ("FR", enc_fr), ("RL", enc_rl), ("RR", enc_rr)]:
                try:
                    rpm_lbl, bar, spd_lbl = self.enc_labels[key]
                    bar_col = (DANGER if rpm_v > MAX_RPM * 0.8
                               else AMBER if rpm_v > MAX_RPM * 0.5
                               else GREEN if rpm_v > 10 else DIM)
                    rpm_lbl.configure(text=f"{rpm_v:.0f}", text_color=bar_col)
                    bar.set(min(1.0, rpm_v / MAX_RPM))
                    bar.configure(progress_color=bar_col)
                    spd_lbl.configure(text=f"{rpm_v * WHL_CIRC / 60 * 3.6:.1f} km/h")
                except Exception:
                    pass


        except Exception as e:
            print(f"[PROCESS ERROR] {e}")


if __name__ == "__main__":
    app = CarUI()
    app.mainloop()