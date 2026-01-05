import obd
import time
import threading
import random
import numpy as np
from unittest.mock import MagicMock
from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform

# --- TOGGLE SWITCH ---
# --- Logic to Auto-Switch between Real Car and Mock ---
def get_connection():
    # Attempt 1: Real Car
    ports = obd.scan_serial() # Look for Bluetooth/USB ports
    if ports:
        for port in ports:
            try:
                conn = obd.OBD(port)
                if conn.is_connected():
                    print(f"✅ REAL CAR DETECTED ANDCONNECTED ON {port}")
                    return conn
            except:
                continue
    
    # Attempt 2: If no ports or connection fails, go Mock
    print("⚠️ NO OBD ADAPTER FOUND - ENGAGING SIMULATOR")
    print("⚠️ --- STARTING MOCK MODE")
    mock_conn = MagicMock()
    mock_conn.is_connected.return_value = True

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

    mock_conn.query.side_effect = fake_query
    obd.OBD = MagicMock(return_value=mock_conn)

# -------------------------------------------------------------------------
# LOGIC CORE: Calculates physics and stores history
# -------------------------------------------------------------------------
class TelemetryBrain:
    def __init__(self, displacement=2.0):
        self.displacement = displacement
        self.cum_fuel = 0
        self.perf_running = False
        self.perf_start_time = None
        self.leaderboard = []
        
        # Bins for the Fuel Map
        self.rpm_bins = np.arange(0, 7501, 250)
        self.load_bins = np.arange(0, 101, 5)
        self.fuel_map = np.zeros((len(self.load_bins), len(self.rpm_bins)))
        self.trim_window = []

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
        intake = i.value.magnitude if not i.is_null() else 25

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

        return [rpm, speed, hp, torque, ve, fuel_rate, coolant, load, self.cum_fuel, stability]

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
class PrunerDashApp(App):
    def build(self):
        # 1. Handle Android Permissions (Updated for Android 12+)
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            from android.os import Build
            
            perms = [Permission.ACCESS_FINE_LOCATION]
            
            # SDK 31 is Android 12
            if Build.VERSION.SDK_INT >= 31:
                perms.extend([Permission.BLUETOOTH_SCAN, Permission.BLUETOOTH_CONNECT])
            else:
                perms.extend([Permission.BLUETOOTH, Permission.BLUETOOTH_ADMIN])
                
            request_permissions(perms)

        # 2. Init Logic
        self.brain = TelemetryBrain(displacement=2.0) # Set engine size here
        self.latest_metrics = [0]*10
        self.stop_thread = False
        self.connection = None
        
        # 3. Start Background Thread
        self.worker_thread = threading.Thread(target=self.background_worker)
        self.worker_thread.daemon = True # Kills thread if app crashes hard
        self.worker_thread.start()

        # 4. Build Layout
        self.layout = GridLayout(cols=2, padding=10, spacing=10)
        self.widgets = {}

        # --- HEADER SECTION ---
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=100, spacing=20)
        
        # Connection Status "Light"
        self.status_light = Label(text="●", font_size='40sp', color=(1, 0, 0, 1), size_hint_x=0.2)
        self.status_label = Label(text="DISCONNECTED", font_size='18sp', size_hint_x=0.4)
        
        # Manual Reconnect Button
        reconnect_btn = Button(text="RECONNECT", size_hint_x=0.4, background_color=(0, 0.5, 1, 1))
        reconnect_btn.bind(on_press=self.start_connection_thread)
        
        header.add_widget(self.status_light)
        header.add_widget(self.status_label)
        header.add_widget(reconnect_btn)

        # Main Data Grid
        self.main_container = BoxLayout(orientation='vertical')
        self.main_container.add_widget(header)
        self.main_container.add_widget(self.layout)

        labels = ["RPM", "Speed", "HP", "Torque Nm", "VE %", "Fuel L/h", "Coolant C", "Load %", "Total Fuel", "Stability"]
        for label in labels:
            box = GridLayout(rows=2, size_hint_y=None, height=120)
            lbl = Label(text=label, font_size='14sp', color=(.5,.5,.5,1))
            val = Label(text="0.0", font_size='32sp', bold=True)
            box.add_widget(lbl)
            box.add_widget(val)
            self.layout.add_widget(box)
            self.widgets[label] = val

        self.leader_lbl = Label(text="0-100: N/A", font_size='16sp', color=(0,1,1,1), size_hint_y=None, height=50)
        self.layout.add_widget(self.leader_lbl)
        self.layout.add_widget(FuelMapWidget(self.brain))

        # 5. UI Update Loop (Fast, non-blocking)
        self.start_connection_thread()
        Clock.schedule_interval(self.update_ui, 0.1)
        def get_layout(self):
            return self.layout
        return self.main_container
    
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
        # Connect to OBD
        connection = get_connection() # Auto-connects
        
        while not self.stop_thread:
            if connection.is_connected():
                # This performs the slow queries and math
                self.latest_metrics = self.brain.process_data(connection)
            else:
                # Try to reconnect or wait if connection lost
                pass 
            
            time.sleep(1) # Prevent CPU hogging
            
        connection.close()

    def update_ui(self, dt):
        """ Reads the latest data from the thread and updates screen """
        m = self.latest_metrics
        keys = ["RPM", "Speed", "HP", "Torque Nm", "VE %", "Fuel L/h", "Coolant C", "Load %", "Total Fuel", "Stability"]
        
        # Update the Status Light
        if hasattr(self, 'is_mock') and self.is_mock:
            self.status_light.color = (1, 0.5, 0, 1) # Orange = Mock
            self.status_label.text = "MOCK MODE"
        elif m[0] > 0 or (self.connection and self.connection.is_connected()):
            self.status_light.color = (0, 1, 0, 1) # Green = Car
            self.status_label.text = "CAR CONNECTED"
        
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

    def on_stop(self):
        """ Clean up thread when app closes """
        self.stop_thread = True
        self.worker_thread.join()

if __name__ == "__main__":
    PrunerDashApp().run()