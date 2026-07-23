import os, sqlite3, datetime
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

DB_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "race_logs.db")

BG     = "#111113"
CARD   = "#1c1c1f"
CARD2  = "#171719"
BORD   = "#2c2c30"
RED    = "#e63946"
GREEN  = "#22c55e"
AMBER  = "#f5a623"
GRAY   = "#a0a0a8"
DIM    = "#5c5c63"
BTN_BG = "#1a1a1e"
BTN_HV = "#222226"


def get_db():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def fetch_sessions(con):
    return con.execute(
        "SELECT id, name, started_at, ended_at, total_records FROM sessions ORDER BY id DESC"
    ).fetchall()


def fetch_telemetry(con, session_id):
    try:
        return con.execute("""
            SELECT ts_ms, ts, s_front, s_front_l, s_front_r, s_side_l, s_side_r, s_rear,
                   speed, battery_v,
                   COALESCE(enc_fl, 0), COALESCE(enc_fr, 0),
                   COALESCE(enc_rl, 0), COALESCE(enc_rr, 0),
                   status, mode
            FROM telemetry WHERE session_id = ? ORDER BY ts_ms ASC
        """, (session_id,)).fetchall()
    except Exception:
        return []


def session_kpms(rows):
    if not rows:
        return {}
    speeds   = [r[8]  for r in rows if r[8]  is not None]
    bats     = [r[9]  for r in rows if r[9]  is not None and r[9] > 0]
    statuses = [r[14] for r in rows]
    all_rpm  = [r[10] for r in rows] + [r[11] for r in rows] + \
               [r[12] for r in rows] + [r[13] for r in rows]
    all_rpm  = [v for v in all_rpm if v]
    total_s  = (rows[-1][0] - rows[0][0]) / 1000 if rows else 0
    total_trig = sum(1 for r in rows if any([r[2], r[3], r[4], r[5], r[6], r[7]]))
    return {
        "total_records":   len(rows),
        "duration_s":      total_s,
        "max_speed":       max(speeds)              if speeds  else 0,
        "avg_speed":       sum(speeds)/len(speeds)  if speeds  else 0,
        "max_rpm":         max(all_rpm)             if all_rpm else 0,
        "avg_rpm":         sum(all_rpm)/len(all_rpm)if all_rpm else 0,
        "min_battery":     min(bats)                if bats    else None,
        "sensor_triggers": total_trig,
        "error_rate":      total_trig / len(rows) * 100 if rows else 0,
        "status_counts":   {k: statuses.count(k) for k in set(statuses)},
    }


class Dashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("RC CAR — Race Analysis Dashboard")
        self.geometry("1280x780")
        self.minsize(1000, 640)
        self.configure(fg_color=BG)

        self.db          = get_db()
        self.sel_session = None
        self.tele_rows   = []

        self._build_ui()
        self._load_sessions()

    def _build_ui(self):
        h = ctk.CTkFrame(self, height=50, fg_color="#0c0c0e", corner_radius=0)
        h.pack(fill="x")
        h.pack_propagate(False)
        ctk.CTkLabel(h, text="📊  RC CAR — RACE ANALYSIS DASHBOARD",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=RED).pack(side="left", padx=18, pady=10)
        ctk.CTkLabel(h, text=f"DB: {DB_PATH}",
                     font=ctk.CTkFont(size=9), text_color=DIM).pack(side="right", padx=14)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=8)

        left = ctk.CTkFrame(body, fg_color=CARD, corner_radius=12,
                            border_width=1, border_color=BORD, width=260)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="SESSIONS",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=RED).pack(pady=(12, 4), padx=12, anchor="w")
        ctk.CTkButton(left, text="🔄 Refresh", height=28, width=110,
                      fg_color=BTN_BG, hover_color=BTN_HV,
                      border_width=1, border_color=BORD,
                      font=ctk.CTkFont(size=10),
                      command=self._load_sessions).pack(padx=12, pady=(0, 6), anchor="w")

        self._divider(left)

        self.sess_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.sess_frame.pack(fill="both", expand=True, padx=4, pady=4)

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True)

        self.tabs = ctk.CTkTabview(right, fg_color=CARD,
                                    segmented_button_fg_color=BTN_BG,
                                    segmented_button_selected_color="#2e2e33",
                                    segmented_button_unselected_color=BTN_BG,
                                    text_color=GRAY,
                                    border_width=1, border_color=BORD)
        self.tabs.pack(fill="both", expand=True)

        self.tabs.add("📈 KPM Summary")
        self.tabs.add("⚡ Speed")
        self.tabs.add("🔄 Encoder RPM")
        self.tabs.add("🔴 Sensor Events")
        self.tabs.add("📋 Raw Data")

        self._build_kpm_tab()
        self._build_speed_tab()
        self._build_encoder_tab()
        self._build_sensor_tab()
        self._build_raw_tab()

        f = ctk.CTkFrame(self, height=24, fg_color="#0c0c0e", corner_radius=0)
        f.pack(fill="x")
        f.pack_propagate(False)
        self.footer_lbl = ctk.CTkLabel(f, text="Select a session →",
                                        font=ctk.CTkFont(size=8), text_color=DIM)
        self.footer_lbl.pack(side="left", padx=12)

    def _build_kpm_tab(self):
        tab = self.tabs.tab("📈 KPM Summary")
        self.kpm_cards = {}

        kpm_defs = [
            ("max_speed",       "TOP SPEED",       "0.0", "km/h",  GREEN),
            ("avg_speed",       "AVG SPEED",        "0.0", "km/h",  RED),
            ("duration",        "TOTAL TIME",       "—",   "",      AMBER),
            ("total_records",   "TOTAL RECORDS",    "0",   "rows",  RED),
            ("max_rpm",         "PEAK RPM",         "0",   "RPM",   GREEN),
            ("avg_rpm",         "AVG RPM",          "0",   "RPM",   AMBER),
            ("sensor_triggers", "SENSOR TRIGGERS",  "0",   "times", RED),
        ]

        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(padx=20, pady=20, fill="both", expand=True)

        cols = 4
        for i, (key, title, init_val, unit, col) in enumerate(kpm_defs):
            card = ctk.CTkFrame(grid, fg_color=CARD2, corner_radius=10,
                                border_width=1, border_color=BORD)
            card.grid(row=i//cols, column=i%cols, padx=6, pady=6, sticky="nsew")
            grid.columnconfigure(i%cols, weight=1)
            grid.rowconfigure(i//cols, weight=1)
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=9), text_color=DIM).pack(pady=(12, 2))
            val_lbl = ctk.CTkLabel(card, text=init_val,
                                   font=ctk.CTkFont(size=26, weight="bold"), text_color=DIM)
            val_lbl.pack()
            ctk.CTkLabel(card, text=unit, font=ctk.CTkFont(size=9), text_color=DIM).pack(pady=(0, 12))
            self.kpm_cards[key] = (val_lbl, col)

        status_frame = ctk.CTkFrame(tab, fg_color=CARD2, corner_radius=10,
                                     border_width=1, border_color=BORD)
        status_frame.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkLabel(status_frame, text="NAVIGATION STATUS DISTRIBUTION",
                     font=ctk.CTkFont(size=10, weight="bold"), text_color=RED).pack(pady=(10, 4), anchor="w", padx=14)
        self.status_bar_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        self.status_bar_frame.pack(fill="x", padx=14, pady=(0, 10))

    def _build_speed_tab(self):
        tab = self.tabs.tab("⚡ Speed")
        if HAS_MPL:
            self.fig_speed = Figure(figsize=(8, 4.5), facecolor=CARD)
            self.fig_speed.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.12)
            self.ax_speed  = self.fig_speed.add_subplot(111)
            self._style_ax(self.ax_speed, "Time (s)", "Speed (km/h)")
            self.canvas_speed = FigureCanvasTkAgg(self.fig_speed, master=tab)
            self.canvas_speed.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        else:
            ctk.CTkLabel(tab, text="📦 matplotlib required:\n\npip install matplotlib",
                         font=ctk.CTkFont(size=13), text_color=AMBER).pack(expand=True)

    def _build_encoder_tab(self):
        tab = self.tabs.tab("🔄 Encoder RPM")
        if HAS_MPL:
            self.fig_enc = Figure(figsize=(8, 4.5), facecolor=CARD)
            self.fig_enc.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.12)
            self.ax_enc  = self.fig_enc.add_subplot(111)
            self._style_ax(self.ax_enc, "Time (s)", "RPM")
            self.canvas_enc = FigureCanvasTkAgg(self.fig_enc, master=tab)
            self.canvas_enc.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        else:
            ctk.CTkLabel(tab, text="📦 matplotlib required:\n\npip install matplotlib",
                         font=ctk.CTkFont(size=13), text_color=AMBER).pack(expand=True)

    def _build_sensor_tab(self):
        tab = self.tabs.tab("🔴 Sensor Events")
        if HAS_MPL:
            self.fig_sens = Figure(figsize=(8, 4.5), facecolor=CARD)
            self.fig_sens.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.18)
            self.ax_sens  = self.fig_sens.add_subplot(111)
            self._style_ax(self.ax_sens, "Time (s)", "Sensor (0=CLEAR, 1=OBSTACLE)")
            self.canvas_sens = FigureCanvasTkAgg(self.fig_sens, master=tab)
            self.canvas_sens.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        else:
            ctk.CTkLabel(tab, text="📦 matplotlib required:\n\npip install matplotlib",
                         font=ctk.CTkFont(size=13), text_color=AMBER).pack(expand=True)

    def _build_raw_tab(self):
        tab = self.tabs.tab("📋 Raw Data")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Treeview",
                        background=CARD, foreground=GRAY,
                        fieldbackground=CARD, rowheight=22,
                        font=("Courier", 9))
        style.configure("Dark.Treeview.Heading",
                        background=BTN_BG, foreground=RED,
                        font=("Courier", 9, "bold"))
        style.map("Dark.Treeview", background=[("selected", "#2e2e33")])

        cols = ("timestamp", "REAR", "SPEED", "FL RPM", "FR RPM", "RL RPM", "RR RPM", "STATUS", "MODE")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings",
                                  style="Dark.Treeview", height=28)
        widths = {"timestamp": 140, "REAR": 60, "SPEED": 70,
                  "FL RPM": 65, "FR RPM": 65, "RL RPM": 65, "RR RPM": 65,
                  "STATUS": 130, "MODE": 40}
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths.get(col, 80), anchor="center")

        scroll_y = ttk.Scrollbar(tab, orient="vertical",   command=self.tree.yview)
        scroll_x = ttk.Scrollbar(tab, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll_y.pack(side="right", fill="y",   pady=8)
        scroll_x.pack(side="bottom", fill="x")

    def _load_sessions(self):
        for w in self.sess_frame.winfo_children():
            w.destroy()

        if not self.db:
            ctk.CTkLabel(self.sess_frame,
                         text="race_logs.db not found.\nStart recording in car_ui.py",
                         font=ctk.CTkFont(size=10), text_color=DIM, wraplength=200).pack(pady=20)
            return

        sessions = fetch_sessions(self.db)

        if not sessions:
            ctk.CTkLabel(self.sess_frame,
                         text="No sessions yet.\ncar_ui.py → ⏺ Start Recording",
                         font=ctk.CTkFont(size=10), text_color=DIM, wraplength=200).pack(pady=20)
            return

        for sid, name, started_at, ended_at, total_records in sessions:
            try:
                t0      = datetime.datetime.fromisoformat(started_at)
                t1      = datetime.datetime.fromisoformat(ended_at) if ended_at else datetime.datetime.now()
                dur     = int((t1 - t0).total_seconds())
                dur_str = f"{dur//60:02d}:{dur%60:02d}"
            except Exception:
                dur_str = "—"

            card = ctk.CTkFrame(self.sess_frame, fg_color=CARD2, corner_radius=8,
                                border_width=1, border_color=BORD, cursor="hand2")
            card.pack(fill="x", pady=3, padx=2)
            ctk.CTkLabel(card, text=f"#{sid}",
                         font=ctk.CTkFont(size=9, weight="bold"), text_color=RED).pack(anchor="w", padx=8, pady=(6, 0))
            ctk.CTkLabel(card, text=name,
                         font=ctk.CTkFont(size=9), text_color=GRAY, wraplength=220, anchor="w").pack(anchor="w", padx=8)
            ctk.CTkLabel(card, text=f"⏱ {dur_str}  ·  📊 {total_records or 0} records",
                         font=ctk.CTkFont(size=8), text_color=DIM).pack(anchor="w", padx=8, pady=(0, 6))
            card.bind("<Button-1>", lambda e, s=sid: self._select_session(s))
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda e, s=sid: self._select_session(s))

    def _select_session(self, session_id):
        self.sel_session = session_id
        self.tele_rows   = fetch_telemetry(self.db, session_id)
        self.footer_lbl.configure(
            text=f"Session #{session_id} loaded — {len(self.tele_rows)} rows",
            text_color=GREEN)
        self._update_kpms()
        self._update_speed_chart()
        self._update_encoder_chart()
        self._update_sensor_chart()
        self._update_raw_table()

    def _update_kpms(self):
        kpm = session_kpms(self.tele_rows)
        if not kpm:
            return

        def set_card(key, val_str):
            if key in self.kpm_cards:
                lbl, col = self.kpm_cards[key]
                lbl.configure(text=val_str, text_color=col)

        dur  = kpm["duration_s"]
        m, s = divmod(int(dur), 60)
        h, m = divmod(m, 60)

        set_card("max_speed",       f"{kpm['max_speed']:.1f}")
        set_card("avg_speed",       f"{kpm['avg_speed']:.1f}")
        set_card("duration",        f"{h:02d}:{m:02d}:{s:02d}")
        set_card("total_records",   f"{kpm['total_records']:,}")
        set_card("max_rpm",         f"{kpm['max_rpm']:.0f}")
        set_card("avg_rpm",         f"{kpm['avg_rpm']:.0f}")
        set_card("sensor_triggers", f"{kpm['sensor_triggers']}")

        for w in self.status_bar_frame.winfo_children():
            w.destroy()

        status_colors = {
            "CLEAR":          (GREEN,     "Clear"),
            "CRITICAL_FRONT": (RED,       "Critical Front"),
            "TURN_LEFT":      (AMBER,     "Turn Left"),
            "TURN_RIGHT":     (AMBER,     "Turn Right"),
            "REAR_HAZARD":    ("#f97316", "Rear Hazard"),
            "MANUAL":         (RED,       "Manual"),
        }
        total = kpm["total_records"] or 1
        for status, count in kpm["status_counts"].items():
            col, label = status_colors.get(status, (GRAY, status))
            pct = count / total
            row = ctk.CTkFrame(self.status_bar_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=9),
                         text_color=GRAY, width=110, anchor="w").pack(side="left")
            bar = ctk.CTkProgressBar(row, height=10, corner_radius=3,
                                      progress_color=col, fg_color=BTN_BG)
            bar.set(pct)
            bar.pack(side="left", fill="x", expand=True, padx=(6, 6))
            ctk.CTkLabel(row, text=f"{count} ({pct*100:.0f}%)",
                         font=ctk.CTkFont(size=8), text_color=DIM, width=80).pack(side="left")

    def _update_speed_chart(self):
        if not HAS_MPL or not self.tele_rows:
            return
        ax = self.ax_speed
        ax.clear()
        self._style_ax(ax, "Time (s)", "Speed (km/h)")
        t0     = self.tele_rows[0][0]
        times  = [(r[0] - t0) / 1000 for r in self.tele_rows]
        speeds = [r[8] or 0 for r in self.tele_rows]
        ax.plot(times, speeds, color=RED, linewidth=1.5, label="Speed (km/h)", alpha=0.9)
        ax.fill_between(times, speeds, alpha=0.15, color=RED)
        ax.legend(fontsize=8, facecolor=CARD, edgecolor=BORD, labelcolor=GRAY, loc="upper left")
        ax.set_title(f"Session #{self.sel_session} — Speed Timeline", color=GRAY, fontsize=10)
        self.canvas_speed.draw()

    def _update_encoder_chart(self):
        if not HAS_MPL or not self.tele_rows:
            return
        ax = self.ax_enc
        ax.clear()
        self._style_ax(ax, "Time (s)", "RPM")
        t0    = self.tele_rows[0][0]
        times = [(r[0] - t0) / 1000 for r in self.tele_rows]
        wheel_data = [
            ("FL — Front Left",  [r[10] or 0 for r in self.tele_rows], RED),
            ("FR — Front Right", [r[11] or 0 for r in self.tele_rows], "#f97316"),
            ("RL — Rear Left",   [r[12] or 0 for r in self.tele_rows], GREEN),
            ("RR — Rear Right",  [r[13] or 0 for r in self.tele_rows], AMBER),
        ]
        for label, vals, col in wheel_data:
            ax.plot(times, vals, color=col, linewidth=1.4, label=label, alpha=0.85)
        ax.fill_between(times,
                        [min(r[10] or 0, r[11] or 0, r[12] or 0, r[13] or 0) for r in self.tele_rows],
                        [max(r[10] or 0, r[11] or 0, r[12] or 0, r[13] or 0) for r in self.tele_rows],
                        alpha=0.06, color=GRAY)
        ax.legend(fontsize=8, facecolor=CARD, edgecolor=BORD, labelcolor=GRAY,
                  loc="upper left", ncol=2)
        ax.set_title(f"Session #{self.sel_session} — Wheel RPM Timeline",
                     color=GRAY, fontsize=10)
        self.canvas_enc.draw()

    def _update_sensor_chart(self):
        if not HAS_MPL or not self.tele_rows:
            return
        ax = self.ax_sens
        ax.clear()
        self._style_ax(ax, "Time (s)", "Sensor Value")
        t0    = self.tele_rows[0][0]
        times = [(r[0] - t0) / 1000 for r in self.tele_rows]
        sensor_data = [
            ("Front",       [r[2] or 0 for r in self.tele_rows], RED),
            ("Front Left",  [r[3] or 0 for r in self.tele_rows], AMBER),
            ("Front Right", [r[4] or 0 for r in self.tele_rows], GREEN),
            ("Side Left",   [r[5] or 0 for r in self.tele_rows], "#60a5fa"),
            ("Side Right",  [r[6] or 0 for r in self.tele_rows], "#c084fc"),
            ("Rear",        [r[7] or 0 for r in self.tele_rows], "#f97316"),
        ]
        for i, (name, vals, col) in enumerate(sensor_data):
            offset  = i * 1.2
            shifted = [v + offset for v in vals]
            ax.plot(times, shifted, color=col, linewidth=1.2, label=name, alpha=0.9)
            ax.fill_between(times, offset, shifted, alpha=0.2, color=col)
        ax.legend(fontsize=7, facecolor=CARD, edgecolor=BORD,
                  labelcolor=GRAY, loc="upper right", ncol=2)
        ax.set_title(f"Session #{self.sel_session} — Sensor Trigger Timeline",
                      color=GRAY, fontsize=10)
        ax.set_yticks([])
        self.canvas_sens.draw()

    def _update_raw_table(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.tele_rows[-500:]:
            ts_str = r[1][:19] if r[1] else "—"
            values = (
                ts_str,
                "🔴" if r[7] == 1 else "🟢",
                f"{r[8]:.1f}"  if r[8]  else "0.0",
                f"{r[10]:.0f}" if r[10] else "0",
                f"{r[11]:.0f}" if r[11] else "0",
                f"{r[12]:.0f}" if r[12] else "0",
                f"{r[13]:.0f}" if r[13] else "0",
                r[14],
                r[15],
            )
            tag = "red" if r[7] == 1 else "normal"
            self.tree.insert("", "end", values=values, tags=(tag,))
        self.tree.tag_configure("red",    background="#1a0000", foreground="#fca5a5")
        self.tree.tag_configure("normal", background=CARD,      foreground=GRAY)

    def _divider(self, p):
        ctk.CTkFrame(p, height=1, fg_color=BORD).pack(fill="x", padx=10, pady=4)

    def _style_ax(self, ax, xlabel, ylabel):
        ax.set_facecolor(BG)
        ax.tick_params(colors=DIM, labelsize=7)
        ax.set_xlabel(xlabel, color=GRAY, fontsize=8)
        ax.set_ylabel(ylabel, color=GRAY, fontsize=8)
        ax.spines["bottom"].set_color(BORD)
        ax.spines["left"].set_color(BORD)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(True, color=BTN_BG, linewidth=0.5, linestyle="--")


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"[WARNING] Database not found: {DB_PATH}")
        print("Start recording in car_ui.py → ⏺ Start Recording")
    app = Dashboard()
    app.mainloop()
