# 🛰️ RC Car — Mission Control

A real-time telemetry and remote-control system for an RC car, built with a **Raspberry Pi + Arduino + PC** architecture. The system provides live sensor monitoring, manual driving controls, telemetry recording, and post-session race analysis — all through polished dark-themed desktop interfaces.

## Architecture Overview

The project follows a three-tier hardware/software architecture:

```
┌─────────────┐   Serial (USB)    ┌──────────────┐   TCP/IP (WiFi)   ┌────────────────┐
│   Arduino   │ ◄──────────────►  │ Raspberry Pi │ ◄───────────────► │   PC (Client)  │
│ Motor Driver│                   │  Sensor Hub  │                   │ Mission Control│
└─────────────┘                   └──────────────┘                   └────────────────┘
```

| Layer | Hardware | Role |
|-------|----------|------|
| **Motor Control** | Arduino | Drives the H-Bridge motor driver (forward, backward, turn left/right, stop) via serial commands |
| **Sensor Hub** | Raspberry Pi | Reads 6× IR obstacle sensors + 4× wheel encoders via GPIO, calculates speed/RPM, runs the TCP socket server, and relays commands to Arduino |
| **Mission Control** | PC | Dark-themed GUI for live sensor visualization, manual WASD driving, telemetry recording to SQLite, and session timer |
| **Race Analysis** | PC | Post-session dashboard with speed charts, encoder RPM timelines, sensor event plots, KPI summaries, and raw data explorer |

## Features

- **Live Sensor Radar Matrix** — Real-time visual diagram of 6 obstacle sensors (front, front-left, front-right, side-left, side-right, rear) with color-coded status indicators
- **Manual Driving Mode** — WASD keyboard controls and on-screen D-pad with visual button feedback; supports diagonal movement and emergency stop (Space)
- **Telemetry Recording** — One-click session recording that logs all sensor states, speed, wheel RPMs, and navigation status to a local SQLite database
- **4× Wheel Encoder Monitoring** — Live RPM readouts with progress bars and km/h conversion for each wheel (FL, FR, RL, RR)
- **Race Analysis Dashboard** — Interactive session explorer with matplotlib charts:
  - Speed timeline with area fill
  - Per-wheel RPM overlay chart
  - Sensor trigger timeline (stacked by sensor)
  - KPI summary cards (top speed, avg speed, peak RPM, duration, etc.)
  - Navigation status distribution bars
  - Raw data table (last 500 records)
- **Sensor Debouncing** — Software debounce on the Raspberry Pi prevents false triggers from noisy IR sensors
- **Auto-Reconnection** — The PC client automatically reconnects if the Pi connection drops

## Hardware Requirements

| Component | Specification |
|-----------|---------------|
| Raspberry Pi | 3B+ / 4 / 5 (any model with GPIO) |
| Arduino | Uno / Nano / Mega |
| Motor Driver | L298N or compatible H-Bridge |
| DC Motors | 2× (differential drive) |
| IR Obstacle Sensors | 6× digital output |
| Wheel Encoders | 4× (optical slot type, 20 PPR) |
| Power Supply | Battery pack for motors + Pi power |

### GPIO Pin Mapping

**IR Sensors (Raspberry Pi):**

| Sensor | GPIO Pin |
|--------|----------|
| Front Center | GPIO 4 |
| Front Left | GPIO 27 |
| Front Right | GPIO 22 |
| Side Left | GPIO 5 |
| Side Right | GPIO 6 |
| Rear | GPIO 17 |

**Wheel Encoders (Raspberry Pi):**

| Encoder | GPIO Pin |
|---------|----------|
| Front Left (FL) | GPIO 20 |
| Front Right (FR) | GPIO 21 |
| Rear Left (RL) | GPIO 23 |
| Rear Right (RR) | GPIO 24 |

**Motor Driver (Arduino):**

| Signal | Arduino Pin |
|--------|-------------|
| IN1 | D5 |
| IN2 | D6 |
| IN3 | D7 |
| IN4 | D8 |

## Software Requirements

**PC (Windows/macOS/Linux):**
- Python 3.9+
- customtkinter ≥ 5.2.0
- matplotlib ≥ 3.7.0

**Raspberry Pi:**
- Python 3.9+
- RPi.GPIO
- pyserial
- smbus2

**Arduino:**
- Arduino IDE (for uploading `motor_control.ino`)

## Installation

### 1. Arduino Setup

Open `motor_control/motor_control.ino` in the Arduino IDE, select the correct board and port, then upload.

### 2. Raspberry Pi Setup

```bash
git clone <repository-url>
cd <project-directory>
pip install -r requirements_pi.txt
```

### 3. PC Setup

```bash
git clone <repository-url>
cd <project-directory>
pip install -r requirements_pc.txt
```

## Usage

### Step 1 — Start the Raspberry Pi

Connect the Arduino to the Pi via USB, then run:

```bash
python sensor_test.py
```

This starts the TCP socket server on port `5005`, begins reading sensors and encoders, and waits for the PC to connect.

### Step 2 — Launch Mission Control (PC)

Make sure the Pi and PC are on the same network. Update the `pi_ip` variable in `car_ui.py` if your Pi's IP differs from `192.168.1.3`, then run:

```bash
python car_ui.py
```

The UI will automatically attempt to connect to the Pi. Once connected, you can:

- **Toggle Manual Mode** — Click the "Manual" button in the header (or use the toggle)
- **Drive** — Use `W` `A` `S` `D` keys or click the on-screen D-pad
- **Emergency Stop** — Press `Space`
- **Record a Session** — Click `⏺ Start Recording` to begin logging telemetry to `race_logs.db`

### Step 3 — Analyze Recorded Sessions

After recording one or more sessions, launch the analysis dashboard:

```bash
python dashboard.py
```

Select any session from the sidebar to view detailed charts and statistics.

## Project Structure

```
.
├── car_ui.py                 # Mission Control GUI (runs on PC)
├── dashboard.py              # Race Analysis Dashboard (runs on PC)
├── sensor_test.py            # Sensor hub + socket server (runs on Raspberry Pi)
├── motor_control/
│   └── motor_control.ino     # Motor driver firmware (runs on Arduino)
├── race_logs.db              # SQLite database for recorded telemetry
├── requirements_pc.txt       # Python dependencies for PC
└── requirements_pi.txt       # Python dependencies for Raspberry Pi
```

## Communication Protocol

The system uses a simple, newline-delimited text protocol over TCP:

**PC → Pi (Commands):**

| Command | Description |
|---------|-------------|
| `1` / `2` / `3` | Set driving mode (Slow / Balanced / Aggressive) |
| `M` | Enter manual mode |
| `M_W` | Manual forward |
| `M_S` | Manual backward |
| `M_A` | Manual turn left |
| `M_D` | Manual turn right |
| `M_X` | Manual stop |

**Pi → PC (Telemetry Packets):**

```
FRONT,FRONT_LEFT,FRONT_RIGHT,SIDE_LEFT,SIDE_RIGHT,REAR,STATUS,MODE,SPEED,BATTERY,FL_RPM,FR_RPM,RL_RPM,RR_RPM
```

Each field is comma-separated and sent at ~12.5 Hz (every 80ms).

## Authors

- **Okan Umut Özen**
- **Toprak Türe**

## License

This project is provided as-is for educational and personal use.