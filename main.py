import time
import threading
import random
import obd
import numpy as np
from unittest.mock import MagicMock

from visuals import RealTimeGraph, ShiftBar, StressMeter
from logger import DataLogger
from engine_data import calculate_extra_metrics
from calibration import CalibrationPopup
from car_db import CarDatabase
from replay import TelemetryReplayer

from kivy.storage.jsonstore import JsonStore
from kivy.uix.listview import ListView # Or a RecycleView for modern Kivy
from kivy.uix.selectableview import SelectableView
from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Line, Gradient
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics.texture import Texture
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform

# --- TOGGLE SWITCH ---
# --- Logic to Auto-Switch between Real Car and Mock ---
def get_connection():
    # Look for Bluetooth/USB ports
    try:
        ports = BTDeviceWindow
    except Exception as e:
        print(f"Error getting ports: {e}")
        print("Failed to load BT/WiFi/MockMode connection")              

# -------------------------------------------------------------------------
# LOGIC CORE: Calculates physics and stores history
# -------------------------------------------------------------------------
class CarDoctor:
    @staticmethod
    def diagnose(metrics):
        """
        Analyzes metrics and returns a 'Prescription' (Recommendation string)
        metrics: [rpm, speed, hp, torque, ve, fuel_rate, coolant, load, cum_fuel, stability. temp_in]
        """
        rpm, speed, hp, torque, ve, fuel, coolant, load, total_fuel, stability, temp_in = metrics
        
        advice = "System Normal"
        severity = 0 # 0=Green, 1=Yellow, 2=Red

        # 1. Warmup Protection
        if coolant < 70:
            advice = "⚠️ Engine Cold: Limit RPM < 3000"
            severity = 1
            if rpm > 3500:
                advice = "⛔ CRITICAL: HIGH RPM ON COLD ENGINE!"
                severity = 2

        # 2. Overheat Warning
        elif coolant > 105:
            advice = "⛔ OVERHEATING: Check Airflow / Coolant"
            severity = 2
        
        # 3. Efficiency Trainer (Highway Cruising)
        elif speed > 80 and load < 30 and rpm > 3000:
            advice = "💡 Shift Up to Save Fuel"
            severity = 0
            
        # 4. Stability Check (Rough Idle or Misfire)
        elif speed < 5 and stability > 3.0:
            advice = "⚠️ Rough Idle Detected: Check Spark/Fuel"
            severity = 1

        return advice, severity

class TelemetryBrain:
    def __init__(self, displacement=2.0):
        self.displacement = displacement
        self.cum_fuel = 0
        self.perf_running = False
        self.perf_start_time = None
        self.leaderboard = []
        
        # Logger
        self.logger = DataLogger() 
        self.logging_active = True

        # Buffers for smoothing
        self.connection = None
        self.trim_window = []
        
        # Bins for the Fuel Map
        self.rpm_bins = np.arange(0, 7501, 250)
        self.load_bins = np.arange(0, 101, 5)
        self.fuel_map = np.zeros((len(self.load_bins), len(self.rpm_bins)))

    def process_data(self, connection):
        """
        This method is designed to be run in a BACKGROUND THREAD.
        It queries the OBD port (blocking operation) and returns calculated metrics.
        """
        if not connection or not connection.is_connected():
            return [0]*10

        # Query OBD (These take time!)
        r = connection.query(obd.commands.RPM)
        s = connection.query(obd.commands.SPEED)
        m = connection.query(obd.commands.MAF)
        c = connection.query(obd.commands.COOLANT_TEMP)
        l = connection.query(obd.commands.ENGINE_LOAD)
        t = connection.query(obd.commands.SHORT_FUEL_TRIM_1)
        i = connection.query(obd.commands.INTAKE_TEMP)

        # Extract values safely
        rpm = r.value.magnitude if not r.is_null() else 0
        speed = s.value.magnitude if not s.is_null() else 0
        maf = m.value.magnitude if not m.is_null() else 0
        coolant = c.value.magnitude if not c.is_null() else 0
        load = l.value.magnitude if not l.is_null() else 0
        trim = t.value.magnitude if not t.is_null() else 0
        intake = i.value.magnitude if not i.is_null() else 0
        temp_in = self.connection.query(obd.commands.INTAKE_TEMP).value.magnitude if not i.is_null() else 25

        # --- Calculations ---
        hp = maf * 1.32
        # Torque (Nm) = (HP * 5252 / RPM) * 1.3558 (conversion to Nm)
        # Simplified: (HP * 7120) / RPM
        torque = (hp * 7127) / rpm if rpm > 500 else 0
        
        # Air Density for VE calc
        density = 1.225 * 288.15 / (273.15 + intake)
        
        # Volumetric Efficiency
        ve = 0
        if rpm > 400:
            theoretical_flow = (rpm * (self.displacement/1000) * density) / 120 * 1000
            ve = (maf / theoretical_flow) * 100

        # Fuel Rate (Liters per hour)
        fuel_rate = (maf * 3600) / (14.7 * 740)
        self.cum_fuel += fuel_rate * 0.1 / 3600  # Integrate over 0.1s (approx)

        # Stability (Fuel Trim Standard Deviation)
        self.trim_window.append(trim)
        if len(self.trim_window) > 40: 
            self.trim_window.pop(0)
        stability = np.std(self.trim_window) if len(self.trim_window) > 5 else 0

        # 0-100 Performance Timer
        if not self.perf_running and 2 < speed < 8:
            self.perf_running = True
            self.perf_start_time = time.time()
        elif self.perf_running and speed >= 100:
            elapsed = time.time() - self.perf_start_time
            self.leaderboard.append(elapsed)
            self.leaderboard = sorted(self.leaderboard)[:3] # Keep top 3
            self.perf_running = False

        # Update Fuel Map Learning
        r_idx = np.digitize(rpm, self.rpm_bins) - 1
        l_idx = np.digitize(load, self.load_bins) - 1
        
        if 0 <= r_idx < len(self.rpm_bins) and 0 <= l_idx < len(self.load_bins):
            # Simple averaging or overwrite? Let's use overwrite for now
            self.fuel_map[l_idx, r_idx] = fuel_rate

        current_metrics = [rpm, speed, hp, torque, ve, fuel_rate, coolant, load, self.cum_fuel, stability, temp_in]

        # --- LOGGING INTEGRATION ---
        if self.logging_active and rpm > 0: # Only log if engine is running
            self.logger.log_sample(current_metrics)

        return current_metrics

# -------------------------------------------------------------------------
# UI WIDGET: Draws the Fuel Map
# -------------------------------------------------------------------------
class FuelMapWidget(Widget):
    def __init__(self, brain, **kwargs):
        super().__init__(**kwargs)
        self.brain = brain
        self.img = Image(size_hint=(1, 1))
        self.add_widget(self.img)
        Clock.schedule_interval(self.update_texture, 0.5)

    def update_texture(self, dt):
        data = self.brain.fuel_map
        # Normalize data 0-255 for visualization
        if np.max(data) > 0:
            norm = (data - np.min(data)) / (np.ptp(data) + 1e-6)
            norm = (norm * 255).astype(np.uint8)
        else:
            norm = np.zeros_like(data, dtype=np.uint8)
            
        # Create texture (Grayscale for now)
        texture = Texture.create(size=(norm.shape[1], norm.shape[0]), colorfmt='luminance')
        texture.blit_buffer(norm.tobytes(), colorfmt='luminance', bufferfmt='ubyte')
        texture.flip_vertical()
        
        # Use Nearest interpolation to keep the "grid" look
        texture.mag_filter = 'nearest'
        self.img.texture = texture

# -------------------------------------------------------------------------
# MAIN APP: Handles Threads and Display
# -------------------------------------------------------------------------
class ModernMetricCard(ButtonBehavior, BoxLayout):
    def __init__(self, title, icon, unit='', **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.title = title
        self.icon = icon
        self.value_label = Label(text="__", font_size='36sp', bold=True, color=(1, 1, 1, 1))
        self.ghost_metrics = TelemetryReplayer(start_ghost_mode)
        self.ghost_val = Label(
            text="", 
            font_size='18sp', 
            color=(1, 1, 1, 0.3), # Semi-transparent
            size_hint_y=None, 
            height=30
        )
        
        self.add_widget(self.ghost_val)
        self.add_widget(Label(text=f"{icon} {title}", font_size='14sp', color=(0.5, 0.5, 0.5, 1)))
        self.add_widget(self.value_label)
        self.add_widget(Label(text=unit, font_size='12sp', color=(0, 1, 1, 1)))
        
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def handle_ghost_data(self, ghost_m):
        # This stores the ghost data so the main update_ui can see it
        self.ghost_metrics = ghost_m

    def start_ghost_race(self, log_file_path):
        # This is how you actually 'use' start_ghost_mode
        self.replayer.start_ghost_mode(log_file_path, self.handle_ghost_data)

    def update_ghost(self, value):
        self.ghost_val.text = f"GHOST: {value}"

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            # Subtle border and background
            Color(0.1, 0.1, 0.1, 0.8) # Dark, semi-transparent
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[20,])
            Color(0, 1, 1, 0.3) # Cyan Glow
            self.border = Line(rounded_rectangle=[self.x, self.y, self.width, self.height, 20], width=1.5)
        
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.border.rounded_rectangle = (self.x, self.y, self.width, self.height, 20)

class BTDeviceWindow(Popup):
    def __init__(self, reconnect_callback, **kwargs):
        super().__init__(**kwargs)
        self.title = "SELECT OBD-II DEVICE"
        self.size_hint = (0.8, 0.8)
        self.callback = reconnect_callback
        app = App.get_running_app()
        
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Scan for ports (ELM327 adapters)
        ports = obd.scan_serial()
        
        if not ports:
            layout.add_widget(Label(text="No Bluetooth Devices Found"))
            # Attempt 3: If no ports or connection fails, go Mock
            print("⚠️ NO OBD ADAPTER FOUND - ENGAGING SIMULATOR")
            print("⚠️ --- STARTING MOCK MODE")
            print("⚠️ SIMULATOR MODE ACTIVE")
            app.system_state["has_adapter"] = False
            app.system_state["mode"] = "MOCK"
            app.is_mock = True
            def fake_query(command):
                res = MagicMock()
                if command.name == "RPM": val = random.randint(800, 6500)
                elif command.name == "SPEED": val = random.randint(0, 140)
                elif command.name == "MAF": val = random.uniform(5.0, 150.0)
                elif command.name == "COOLANT_TEMP": val = random.randint(80, 105)
                elif command.name == "ENGINE_LOAD": val = random.uniform(10, 95)
                elif command.name == "SHORT_FUEL_TRIM_1": val = random.uniform(-5, 5)
                else: val = 25
                res.value.magnitude = val
                res.is_null.return_value = False
                return res
            MagicMock.is_connected.return_value = True
            MagicMock.query.side_effect = fake_query
            return MagicMock()
        else:
            for port in ports:
                btn = Button(on_press=self.bt_connect, text=f"Device: {port}", size_hint_y=None, height=50)
                # When pressed, it tells the app to reconnect to THIS port
                btn.bind(on_release=lambda x, p=port: self.select_and_close(p))
                layout.add_widget(btn)
        
        close_btn = Button(text="CANCEL", size_hint_y=None, height=50)
        close_btn.bind(on_release=self.dismiss)
        layout.add_widget(close_btn)
        self.content = layout

    def select_and_close(self, port):
        self.callback(port) # Triggers manual_reconnect(port)
        self.dismiss()

    def bt_connect(self, port, **kwargs):
        app = App.get_running_app()
        try:
            # Attempt 1: Real Car
            conn = obd.OBD(port[0])
            if conn.is_connected():
                app.system_state["has_adapter"] = True
                app.system_state["mode"] = "LIVE"
                app.is_mock = False
                print(f"Connecting to Serial: {port[0]}")
                print(f"✅ REAL CAR DETECTED ANDCONNECTED ON {port[0]}")
                return conn
        except:
            # Attempt 2. Try WiFi (Common Address)
            # connection_string="192.168.0.10:35000" is standard for many WiFi dongles
            wifi_conn = obd.OBD(connection_string="192.168.0.10:35000")
            if wifi_conn.is_connected():
                app.system_state["has_adapter"] = True
                app.system_state["mode"] = "LIVE"
                print("Connected via WiFi")
                return wifi_conn

class PrunerDashApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.system_state = {
            "mode": "IDLE",       # IDLE, LIVE, MOCK, or REPLAY
            "has_adapter": False, # Physical connection status
            "active_cc": 2.0      # Current engine displacement
        }

    def start_telemetry(self):
        # 1. Check what car the user selected last
        active_car_name = self.store.get('active_car')['model'] if self.store.exists('active_car') else "Default"
        # 2. Get specs from your SQLite database
        specs = self.db.get_specs(active_car_name) 
        # 3. Pass the REAL displacement to the brain (convert cc to Liters)
        real_displacement = specs['cc'] / 1000.0 if specs else 2.0
        
        self.brain = TelemetryBrain(displacement=real_displacement)

    def build(self):
        # 1. Handle Android Permissions (Updated for Android 12+)
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            from jnius import autoclass

            # Define both classes separately
            Build = autoclass('android.os.Build')
            VERSION_CLASS = autoclass('android.os.Build$VERSION')
            sdk_version = VERSION_CLASS.SDK_INT
            
            print(f"Device: {Build.MODEL}, SDK: {sdk_version}")
            
            # Start with Location (Required for all Bluetooth)
            perms = [Permission.ACCESS_FINE_LOCATION]
            
            # Android 12 (SDK 31) and above requires specific BT permissions
            if sdk_version >= 31:
                perms.extend([Permission.BLUETOOTH_SCAN, Permission.BLUETOOTH_CONNECT])
            else:
                # Older Android versions just need the general ones
                perms.extend([Permission.BLUETOOTH, Permission.BLUETOOTH_ADMIN])
                
            try:
                request_permissions(perms)
            except Exception as e:
                print(f"Permission Request Failed: {e}")

        store = JsonStore('car_settings.json')
        if store.exists('engine'):
            saved_cc = store.get('engine')
            specs = saved_cc['cc'] / 1000.0
            self.brain = TelemetryBrain(displacement=specs)
            print(f"Loaded Saved Config: {saved_cc}cc")
        else:
            try:
                self.start_telemetry()
                return
            except:
                # Get the displacement from the DB
                car_model = store.get('active_car')['model'] # From JsonStore
                specs_v = self.db.get_specs(car_model)
                specs = specs_v['cc'] / 1000.0
                print(f"Loaded Saved Config: {specs_v}cc")

        # 2. Init Logic
        self.doctor = CarDoctor()
        self.latest_metrics = [0]*11
        self.stop_thread = False
        self.connection = get_connection()
        self.refresh_connection_status()
        self.store = JsonStore('car_settings.json')
        self.replayer = TelemetryReplayer(ui_update_callback=self.update_ui_from_metrics)
        self.db = CarDatabase()
        
        # 3. Start Background Thread
        self.worker_thread = threading.Thread(target=self.background_worker)
        self.worker_thread.daemon = True # Kills thread if app crashes hard
        self.worker_thread.start()

        # 4. Build Layout
        self.layout = GridLayout(cols=2, padding=11, spacing=11)
        self.widgets = {}
        self.doctor_label = Label(
            text="Initializing Diagnostics...", 
            font_size='20sp', 
            color=(0, 1, 0, 1),
            size_hint_y=None, 
            height=60,
            bold=True
        )
        self.status_badge = Label(
            text="LIVE OBD", 
            size_hint=(None, None), 
            size=(100, 30),
            color=(0, 1, 0, 1) # Green for live
        )
        
        # 5. THEME COLORS
        self.neon_cyan = (0, 1, 1, 1)
        self.neon_green = (0, 1, 0, 1)
        self.alert_red = (1, 0, 0, 1)
        self.bg_dark = (0.1, 0.1, 0.1, 1)
        
        # Connection Status "Light"
        self.status_light = Label(text="●", font_size='40sp', color=(1, 0, 0, 1), size_hint_x=0.15)
        self.status_label = Label(text="DISCONNECTED", font_size='16sp', size_hint_x=0.35, bold=True)
        
        # Manual Reconnect Button
        reconnect_btn = Button(
            text="🔄 RECONNECT ⚡",
            size_hint=(None, None),
            size_hint_x=0.3,
            size=(120, 40),
            background_color=(self.neon_cyan)
        )
        reconnect_btn.bind(on_press=self.start_connection_thread, on_release=lambda x: BTDeviceWindow(self.manual_reconnect).open())
       
        # SETTINGS BUTTON
        settings_btn = Button(text="⚙", font_size='30sp', size_hint_x=0.2, background_color=(0.2, 0.2, 0.2, 1))
        settings_btn.bind(on_press=self.open_settings)
        
        # HEADER SECTION
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=80, spacing=10)       
        self.status_lbl = Label(text="DISCONNECTED", color=self.alert_red, bold=True)
        
        btn_settings = Button(text="⚙ CALIBRATE", background_color=(0.5, 0.5, 0.5, 1), size_hint_x=0.3)
        btn_settings.bind(on_press=self.open_settings)

        header.add_widget(self.status_lbl)
        header.add_widget(reconnect_btn)
        header.add_widget(btn_settings)
        header.add_widget(self.status_light)
        header.add_widget(self.status_label)
        header.add_widget(reconnect_btn)
        header.add_widget(settings_btn)
        self.main_container.add_widget(header)
        
        # DIAGNOSTIC BANNER ("The Doctor")
        self.doctor_panel = Button(
            text="🛂 Diagnosis", 
            font_size='18sp', 
            background_normal='',
            background_color=(0.2, 0.2, 0.2, 1),
            size_hint_y=None, 
            height=60
        )
        self.main_container.add_widget(self.doctor_label, index=len(self.main_container.children))

        # 3. INTERACTIVE DASHBOARD (Grid)
        self.dashboard_grid = GridLayout(cols=2, spacing=20, padding=10)
        self.widgets = {
            "RPM": ModernMetricCard("ENGINE", icon="🚀", unit="RPM"),
            "Speed": ModernMetricCard("SPEED", icon="💨", unit="KPH"),
            "HP": ModernMetricCard("HP", icon="🐎", unit=""),
            "Torque Nm": ModernMetricCard("TORQUE", icon="⚙️", unit="NM"),
            "VE %": ModernMetricCard("VE", icon="📈", unit=""),
            "Fuel L/h": ModernMetricCard("FUEL", icon="⛽", unit="L/h"),
            "Coolant C": ModernMetricCard("TEMP", icon="🌡️", unit="°C"),
            "Load %": ModernMetricCard("LOAD", icon="🏋️", unit="kg"),
            "Total Fuel": ModernMetricCard("TOTAL FUEL", icon="⛽️", unit="L"),
            "Stability": ModernMetricCard("STABILITY", icon="⚖️", unit=""),
            "Temp_In": ModernMetricCard("TEMP_IN", icon="📈", unit=""),
        }
        for w in self.widgets.values(): self.dashboard_grid.add_widget(w)
        
        # Add a "REPLAY LAST RUN" Button
        replay_btn = Button(text="📹 REPLAY LAST RUN", size_hint_y=None, height=60, background_color=(0, 0.5, 1, 1))
        replay_btn.bind(on_press=self.trigger_replay)
        self.main_container.add_widget(replay_btn)
        
        # -- Define Metrics with Icons --
        # Main Data Grid
        self.shift_bar = ShiftBar(size_hint=(None, 1), width=40)
        self.stress_meter = StressMeter(size_hint=(0.4, 1)) # Takes 40% width
        self.data_grid = GridLayout(cols=2)
        self.main_container = BoxLayout(orientation='vertical', padding=5, spacing=5)
        self.main_container.add_widget(header)
                
        # Format: Label, Icon, Key
        layout_map = [
            ("ENGINE", "🚀", "RPM"), ("SPEED", "💨", "KPH"),
            ("HORSEPOWER", "🐎", ""), ("TORQUE", "⚙️", "Nm"),
            ("VE", "📈", ""), ("AFR / FUEL", "⛽", "Fuel L/h"),
            ("TEMP", "🌡️", "°C"), ("LOAD", "🏋️", "kg"),
            ("TOTAL FUEL", "⛽️", "L"), ("STABILITY", "⚖️", "Stability"),
            ("TEMP_IN", "📈", "")
        ]
        
        lbl = Label(text="DATA", font_size='20sp', color=(0, 1, 1, 1))
        val = Label(text="__", font_size='24sp', bold=True, color=(1, 1, 1, 1))
        self.main_container.add_widget(self.layout)
        
        for label_text, icon, key in layout_map:
            box = GridLayout(rows=2, size_hint_y=None, height=120)
            box.add_widget(lbl)
            box.add_widget(val)
            
            # Each metric is a Card
            card = BoxLayout(orientation='vertical', padding=11)
            
            # Canvas instruction for background color (Dark Grey Card)            
            # Title
            lbl = Label(text=f"{icon} {label_text}", font_size='12sp', color=(0.7, 0.7, 0.7, 1))
            # Value
            val = Label(text="--", font_size='24sp', bold=True, color=self.neon_cyan)
            
            card.add_widget(lbl)
            card.add_widget(val)
            
            self.dashboard_grid.add_widget(card)
            self.layout.add_widget(box)
            self.widgets[key] = val
            
            return layout_map

        # 4. VISUALS (Graphs)
        self.rpm_graph = RealTimeGraph(label="Live RPM", color=self.neon_green, size_hint_y=0.25)
        
        self.leader_lbl = Label(text="0-100: N/A", font_size='16sp', color=(0,1,1,1), size_hint_y=None, height=50)
        self.layout.add_widget(self.leader_lbl)
        self.layout.add_widget(FuelMapWidget(self.brain))
        self.main_container.add_widget(self.rpm_graph)
        self.main_container.add_widget(self.dashboard_grid)

        # 5. UI Update Loop (Fast, non-blocking)
        self.start_connection_thread()
        
        from kivy.core.window import Window
        # This handles the "Back" button on Android so it calls on_stop properly
        Window.bind(on_request_close=self.on_stop)
        
        return self.main_container
    
    def refresh_connection_status(self):
        try:
            is_mock_active = getattr(self, 'is_mock', False)
            print(f"is_mock_active: {is_mock_active}")
        except:
            try:
                is_mock_active = hasattr(self, 'is_mock') and self.is_mock
                print(f"is_mock_active: {is_mock_active}")
            except Exception as e:
                print(f"Error refreshing connection status: {e}")
                is_mock_active = False
        
        if is_mock_active:
            self.status_badge.text = "SIMULATOR MODE"
            self.status_badge.color = (1, 0.5, 0, 1) # Orange
        else:
            self.status_badge.text = "LIVE OBD"
            self.status_badge.color = (0, 1, 0, 1) # Green
    
    def trigger_replay(self):
        # Point to the last log created by your CSV logger
        try:
            log_path = self.brain.logger.filepath
            self.replayer = TelemetryReplayer(log_path, self.update_ui_from_data)
            self.replayer.start_replay(speed=2.0) # Play back at 2x speed!
        except:
            import os
            log_dir = "TelemetryLogs"
            files = [os.path.join(log_dir, f) for f in os.listdir(log_dir)]
            if files:
                latest_file = max(files, key=os.path.getctime)
                self.replayer.start_replay(latest_file)

    def update_ui_from_metrics(self, m):
        # [rpm, speed, hp, torque, ve, fuel_rate, coolant, load, fuel_total, stability]
        self.widgets["RPM"].value_label.text = f"{int(m[0])}"
        self.widgets["Speed"].value_label.text = f"{m[1]:.1f}"
        self.widgets["HP"].value_label.text = f"{m[2]:.1f}"
        self.widgets["Torque Nm"].value_label.text = f"{m[3]:.1f}"
        self.widgets["VE %"].value_label.text = f"{m[4]:.1f}"
        self.widgets["Fuel L/h"].value_label.text = f"{m[5]:.1f}"
        self.widgets["Coolant C"].value_label.text = f"{m[6]:.1f}"
        self.widgets["Load %"].value_label.text = f"{m[7]:.1f}"
        self.widgets["Total Fuel"].value_label.text = f"{m[8]:.1f}"
        self.widgets["Stability"].value_label.text = f"{m[9]:.1f}"
        self.widgets["temp_in"].value_label.text = f"{m[10]:.1f}"
        
        #  Updates the widgets
        print(f"Updating: {m[0]}, {m[7]}, {m[3]}")
        self.shift_bar.update(m[0])            # Pass RPM to Shift Bar
        self.stress_meter.update(m[7], m[3])   # Pass Load and Torque to Stress Meter
        self.rpm_graph.update_value(m[0])      # Pass RPM to the Graph
        
        # Calculate and update derived data
        extra = calculate_extra_metrics(m)
        self.widgets["L/100km"].value_label.text = f"{extra['l_100km']:.1f}"
        self.widgets["hp_per_tonne"].value_label.text = f"{extra['hp_per_tonne']:.1f}"
        
        # Add them to your layout (e.g., adding to a horizontal box)
        layout = BoxLayout(orientation='horizontal')
        layout.add_widget(self.shift_bar)
        layout.add_widget(self.stress_meter)
        
        return layout
    
    def manual_reconnect(self):
        # 1. Kill the old connection if it exists
        if self.connection:
            try:
                self.connection.close()
            except:
                pass

        # 2. Attempt new connection
        # If a port is selected from the BT window, we target it specifically
        self.connection = get_connection()
        
        # 3. Update the Global State & Badge
        self.refresh_connection_status()
    
    def open_settings(self, instance):
        popup = CalibrationPopup(self.brain, self.db)
        popup.open()
    
    def start_connection_thread(self, *args):
        """ Starts a thread to (re)connect to OBD """
        def connect():
            self.connection = get_connection()
            if self.connection.is_connected():
                self.status_light.color = (0, 1, 0, 1)
                self.status_label.text = "CONNECTED"
            else:
                self.status_light.color = (1, 0, 0, 1)
                self.status_label.text = "DISCONNECTED"
        
        threading.Thread(target=connect).start()

    def background_worker(self):
        """ Runs in a separate thread to handle slow OBD communication """
        while not self.stop_thread:
            try:
                # Always check if we have a valid, active connection
                if self.connection and self.connection.is_connected():
                    # Perform the OBD queries and math
                    self.latest_metrics = self.brain.process_data(self.connection)
                    metrics = [rpm, speed, hp, torque, ve, fuel_rate, coolant, load, fuel_total, stability, temp_in] = self.latest_metrics
                    extra = calculate_extra_metrics(metrics)
                    # Send both to the UI
                    Clock.schedule_once(lambda dt: self.update_ui(metrics, extra))
                    # Dashboard speed: 10 times per second
                    time.sleep(0.1) 
                else:
                    # No connection? Wait longer before checking again to save battery
                    time.sleep(2.0)
            except Exception as e:
                print(f"OBD Thread Error: {e}")
                # If a query fails hard (e.g. adapter lost power), reset connection
                self.connection = None
                time.sleep(2.0)
            
        # Final cleanup when the app is actually closing
        if self.connection:
            try:
                self.connection.close()
            except:
                pass

    def update_ui(self, m, live_m, extra):
        """ Reads the latest data from the thread and updates screen """
        try:
            if self.replayer:
                # If replaying, metrics come directly from the replayer
                m = m # m is already passed from replayer
                extra = calculate_extra_metrics(m)
                self.status_light.color = (0, 0.5, 1, 1) # Blue for Replay
                self.status_label.text = "REPLAYING..."
            else:
                # Otherwise, get from the live background worker
                m = self.latest_metrics
        except:
            self.update_ui_from_metrics(m) # Update the UI from the replayer's data

        keys = ["RPM", "Speed", "HP", "Torque Nm", "VE %", "Fuel L/h", "Coolant C", "Load %", "Total Fuel", "Stability", "Tepm_in"]
        # 1. Update primary gauges with live data
        self.update_ui_from_metrics(live_m)
        
        # 2. IF Ghost Mode is active, update the Ghost UI elements
        if self.ghost_metrics:
            # We use 'ghost_m' to update a 'shadow' needle or a small label
            # Example: Showing Ghost RPM next to Live RPM
            self.widgets["Ghost_RPM_Label"].text = f"Ghost: {int(self.ghost_metrics[0])}"
            
            # One Orange (Live), One White (Ghost)
            self.stress_meter.update_with_ghost(
                live_load=live_m[7], 
                live_torque=live_m[3],
                ghost_load=self.ghost_metrics[7],
                ghost_torque=self.ghost_metrics[3]
            )
                
        # Update the Status Light
        if hasattr(self, 'is_mock') and self.is_mock:
            self.status_light.color = (1, 0.5, 0, 1) # Orange = Mock
            self.status_label.text = "MOCK MODE"
        elif m[0] > 0 or (self.connection and self.connection.is_connected()):
            self.status_light.color = (0, 1, 0, 1) # Green = Car
            self.status_label.text = "CAR CONNECTED"
        
        # Update Connection Status
        if self.connection and self.connection.is_connected():
            self.status_lbl.text = "ONLINE"
            self.status_lbl.color = self.neon_green
        else:
            self.status_lbl.text = "OFFLINE"
            self.status_lbl.color = self.alert_red
        
        # Update Widgets
        # Map indices to keys (Must match layout_map order in build)
        data_map = {
            "RPM": m[0], "Speed": m[1], "HP": m[2], "Torque Nm": m[3], "VE %": m[4],
            "Coolant C": m[6], "Load %": m[7], "Total Fuel": m[8], "Stability": m[9], "Temp_In": m[10]
        }
        
        for key, value in data_map.items():
            if key in self.widgets:
                self.widgets[key].text = f"{value:.1f}"
                
                # Special Color for High Load/RPM
                if key == "RPM" and value > 6000: self.widgets[key].color = self.alert_red
                elif key == "RPM": self.widgets[key].color = self.neon_cyan
        
        for i, key in enumerate(keys):
            self.widgets[key].text = f"{m[i]:.1f}"
            
            # Dynamic Colors
            if key == "RPM":
                limit = 6000 if m[6] > 75 else 3500 # Warmup rev limit
                self.widgets[key].color = (1,0,0,1) if m[i] > limit else (0,1,0,1)
            
            if key == "Stability":
                self.widgets[key].color = (0,1,0,1) if m[i] < 2.5 else (1,0,0,1)
        
        # Update Leaderboard text
        if self.brain.leaderboard:
            times = ", ".join([f"{t:.2f}s" for t in self.brain.leaderboard])
            self.leader_lbl.text = f"0-100: {times}"

        # Run The Doctor
        advice, severity = self.doctor.diagnose(m)
        self.doctor_panel.text = f"{advice}"
        
        # Doctor Color Logic
        if severity == 0: 
            self.doctor_panel.background_color = (0, 0.5, 0, 1) # Dark Green
        elif severity == 1: 
            self.doctor_panel.background_color = (0.8, 0.6, 0, 1) # Orange
        else: 
            self.doctor_panel.background_color = (0.8, 0, 0, 1) # Red

    def on_stop(self):
        """ Called when the user closes the app """
        print("Stopping App... Cleaning up threads and connection.")
        
        # 1. Tell the background loop to finish its current cycle
        self.stop_thread = True 
        
        # 2. Close the OBD connection safely
        if self.connection:
            try:
                self.connection.close()
                print("OBD Connection closed.")
            except Exception as e:
                print(f"Error closing connection: {e}")

        # 3. Wait for the thread to actually die (timeout after 1 second)
        if hasattr(self, 'worker_thread'):
            self.worker_thread.join(timeout=1.0)
            print("Background thread stopped.")

if __name__ == "__main__":
    PrunerDashApp().run()