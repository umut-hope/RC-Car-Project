import RPi.GPIO as GPIO
import time
import socket
import threading
import sqlite3
import datetime
import os

try:
    import serial
    try:
        arduino = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    except Exception:
        arduino = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
    time.sleep(2)
    print("[OK] Arduino connected.")
except Exception:
    arduino = None
    print("[WARNING] Arduino not found.")

GPIO.setmode(GPIO.BCM)

PINS = {
    "FRONT":       4,
    "FRONT_LEFT":  27,
    "FRONT_RIGHT": 22,
    "SIDE_LEFT":   5,
    "SIDE_RIGHT":  6,
    "REAR":        17,
}
for pin in PINS.values():
    GPIO.setup(pin, GPIO.IN)
print(f"[OK] GPIO sensors: {list(PINS.keys())} ready.")

ENCODER_PINS = {"FL": 20, "FR": 21, "RL": 23, "RR": 24}
PPR         = 20
WHEEL_CIRC  = 0.22

encoder_counts = {"FL": 0, "FR": 0, "RL": 0, "RR": 0}
enc_lock       = threading.Lock()

for key, pin in ENCODER_PINS.items():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def _poll_encoders():
    prev = {key: GPIO.input(pin) for key, pin in ENCODER_PINS.items()}
    while True:
        for key, pin in ENCODER_PINS.items():
            curr = GPIO.input(pin)
            if curr == 1 and prev[key] == 0:
                with enc_lock:
                    encoder_counts[key] += 1
            prev[key] = curr
        time.sleep(0.005)

threading.Thread(target=_poll_encoders, daemon=True).start()
print(f"[OK] GPIO encoders: {list(ENCODER_PINS.keys())} ready (PPR={PPR}, polling@200Hz)")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pi_log.db")

def init_db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS telemetry(
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        ts       TEXT,
        s_front  INTEGER, s_front_l INTEGER, s_front_r INTEGER,
        s_side_l INTEGER, s_side_r  INTEGER, s_rear    INTEGER,
        speed    REAL,    battery_v REAL,
        enc_fl   REAL,    enc_fr    REAL,    enc_rl REAL, enc_rr REAL,
        status   TEXT,    throttle  INTEGER
    )""")
    con.commit()
    return con

pi_db = init_db()
print(f"[OK] SQLite: {DB_PATH}")

active_mode  = 2
throttle_pct = 0
pc_client    = None

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
except AttributeError:
    pass

for attempt in range(10):
    try:
        server.bind(("0.0.0.0", 5005))
        break
    except OSError:
        if attempt < 9:
            print(f"[WARNING] Port 5005 busy, waiting...")
            time.sleep(2 * (attempt + 1))
        else:
            raise

server.listen(1)
print("[OK] Socket server listening on port 5005...")


def send_to_arduino(command):
    if arduino:
        try:
            arduino.write((command + '\n').encode())
        except Exception:
            pass


def listen_for_pc():
    global active_mode, pc_client, throttle_pct
    while True:
        try:
            print("[INFO] Waiting for PC...")
            client, addr = server.accept()
            pc_client = client
            print(f"[OK] PC connected: {addr}")
            buffer = ""
            while True:
                data = client.recv(1024).decode("utf-8", errors="replace")
                if not data:
                    break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    if line in ["1", "2", "3"]:
                        active_mode = int(line)
                        print(f"[MODE] Mode {active_mode}")
                    elif line.startswith("M_"):
                        cmd = line[2:]
                        # Doğru yön — swap kaldırıldı
                        cmd_map = {
                            "W":  "F",       # W → ileri
                            "S":  "B",       # S → geri
                            "A":  "L_TURN",  # kendi ekseninde sol
                            "D":  "R_TURN",  # kendi ekseninde sağ
                            "WA": "L_TURN",
                            "WD": "R_TURN",
                            "SA": "L_TURN",
                            "SD": "R_TURN",
                            "X":  "H",       # dur
                        }
                        if cmd in cmd_map:
                            send_to_arduino(cmd_map[cmd])
                            print(f"[CMD] {cmd} -> {cmd_map[cmd]}")
        except Exception as e:
            print(f"[ERROR] PC disconnected: {e}")
            pc_client = None


threading.Thread(target=listen_for_pc, daemon=True).start()

_log_counter = 0

def log_to_db(s, speed, enc_rpm):
    global _log_counter
    _log_counter += 1
    if _log_counter % 5 != 0:
        return
    try:
        pi_db.execute("""INSERT INTO telemetry(
            ts, s_front, s_front_l, s_front_r, s_side_l, s_side_r, s_rear,
            speed, battery_v, enc_fl, enc_fr, enc_rl, enc_rr, status, throttle
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.datetime.now().isoformat(),
         s["FRONT"], s["FRONT_LEFT"], s["FRONT_RIGHT"],
         s["SIDE_LEFT"], s["SIDE_RIGHT"], s["REAR"],
         speed, 0.0,
         enc_rpm["FL"], enc_rpm["FR"], enc_rpm["RL"], enc_rpm["RR"],
         "MANUAL", throttle_pct))
        pi_db.commit()
    except Exception:
        pass


print("[OK] Main loop started. Exit: Ctrl+C\n")

prev_enc      = {k: 0 for k in ["FL", "FR", "RL", "RR"]}
prev_enc_time = time.time()

DEBOUNCE_THRESH = 3
debounce_count  = {key: 0 for key in PINS}
stable_state    = {key: 0 for key in PINS}

try:
    while True:
        raw = {key: GPIO.input(PINS[key]) for key in PINS}
        s   = {}
        for key in PINS:
            if raw[key] == stable_state[key]:
                debounce_count[key] = 0
            else:
                debounce_count[key] += 1
                if debounce_count[key] >= DEBOUNCE_THRESH:
                    stable_state[key]   = raw[key]
                    debounce_count[key] = 0
            s[key] = stable_state[key]

        now_t = time.time()
        dt    = now_t - prev_enc_time
        with enc_lock:
            cur_counts = dict(encoder_counts)
        enc_rpm = {}
        if dt > 0:
            for k in ["FL", "FR", "RL", "RR"]:
                delta      = cur_counts[k] - prev_enc[k]
                enc_rpm[k] = round((delta / PPR * 60) / dt, 1)
        else:
            enc_rpm = {k: 0.0 for k in ["FL", "FR", "RL", "RR"]}
        prev_enc      = cur_counts
        prev_enc_time = now_t

        avg_speed_ms = sum(enc_rpm[k] * WHEEL_CIRC / 60 for k in enc_rpm) / 4
        speed        = round(avg_speed_ms * 3.6, 2)

        if pc_client:
            try:
                packet = (
                    f"{s['FRONT']},{s['FRONT_LEFT']},{s['FRONT_RIGHT']},"
                    f"{s['SIDE_LEFT']},{s['SIDE_RIGHT']},{s['REAR']},"
                    f"MANUAL,{active_mode},"
                    f"{speed:.2f},0.00,"
                    f"{enc_rpm['FL']:.1f},{enc_rpm['FR']:.1f},"
                    f"{enc_rpm['RL']:.1f},{enc_rpm['RR']:.1f}\n"
                )
                pc_client.send(packet.encode("utf-8"))
            except Exception:
                pc_client = None

        log_to_db(s, speed, enc_rpm)

        print(
            f"F:{s['FRONT']} FL:{s['FRONT_LEFT']} FR:{s['FRONT_RIGHT']} "
            f"SL:{s['SIDE_LEFT']} SR:{s['SIDE_RIGHT']} R:{s['REAR']} | "
            f"Speed:{speed:.1f}km/h | "
            f"RPM FL:{enc_rpm.get('FL',0):.0f} FR:{enc_rpm.get('FR',0):.0f} "
            f"RL:{enc_rpm.get('RL',0):.0f} RR:{enc_rpm.get('RR',0):.0f}",
            end="\r"
        )

        time.sleep(0.08)

except KeyboardInterrupt:
    print("\n\n[INFO] Shutting down...")
finally:
    GPIO.cleanup()
    if arduino:
        arduino.close()
    server.close()
    pi_db.close()
    print("[OK] Resources released.")
