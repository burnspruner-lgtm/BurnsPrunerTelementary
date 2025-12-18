import obd
import time
import numpy as np
from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.utils import platform

class TelemetryBrain:
    def __init__(self, displacement=2.0):
        self.displacement = displacement
        self.cum_fuel = 0
        self.perf_running = False
        self.perf_start_time = None
        self.leaderboard = []
        self.rpm_bins = np.arange(0, 7501, 250)
        self.load_bins = np.arange(0, 101, 5)
        self.fuel_map = np.zeros((len(self.load_bins), len(self.rpm_bins)))
        self.trim_window = []

    def get_metrics(self, connection):
        if not connection or not connection.is_connected():
            return [0]*10
        r, s = connection.query(obd.commands.RPM), connection.query(obd.commands.SPEED)
        m, c = connection.query(obd.commands.MAF), connection.query(obd.commands.COOLANT_TEMP)
        l, t = connection.query(obd.commands.ENGINE_LOAD), connection.query(obd.commands.SHORT_FUEL_TRIM_1)
        i = connection.query(obd.commands.INTAKE_TEMP)

        rpm = r.value.magnitude if not r.is_null() else 0
        speed = s.value.magnitude if not s.is_null() else 0
        maf = m.value.magnitude if not m.is_null() else 0
        coolant = c.value.magnitude if not c.is_null() else 0
        load = l.value.magnitude if not l.is_null() else 0
        trim = t.value.magnitude if not t.is_null() else 0
        intake = i.value.magnitude if not i.is_null() else 25

        hp = maf * 1.32
        torque = (hp * 7127) / rpm if rpm > 500 else 0
        density = 1.225 * 288.15 / (273.15 + intake)
        ve = (maf / ((rpm * (self.displacement/1000) * density) / 120 * 1000)) * 100 if rpm > 400 else 0
        fuel_rate = (maf * 3600) / (14.7 * 740)
        self.cum_fuel += fuel_rate * 0.1 / 3600

        self.trim_window.append(trim)
        if len(self.trim_window) > 40: self.trim_window.pop(0)
        stability = np.std(self.trim_window) if len(self.trim_window) > 5 else 0

        if not self.perf_running and 2 < speed < 8:
            self.perf_running, self.perf_start_time = True, time.time()
        elif self.perf_running and speed >= 100:
            self.leaderboard.append(time.time() - self.perf_start_time)
            self.leaderboard = sorted(self.leaderboard)[:3]
            self.perf_running = False

        r_idx, l_idx = np.digitize(rpm, self.rpm_bins)-1, np.digitize(load, self.load_bins)-1
        if 0 <= r_idx < len(self.rpm_bins) and 0 <= l_idx < len(self.load_bins):
            self.fuel_map[l_idx, r_idx] = fuel_rate

        return [rpm, speed, hp, torque, ve, fuel_rate, coolant, load, self.cum_fuel, stability]

class FuelMapWidget(Widget):
    def __init__(self, brain, **kwargs):
        super().__init__(**kwargs)
        self.brain = brain
        self.img = Image(size_hint=(1, 1))
        self.add_widget(self.img)
        Clock.schedule_interval(self.update_texture, 0.5)

    def update_texture(self, dt):
        data = self.brain.fuel_map
        norm = (data - np.min(data)) / (np.ptp(data) + 1e-6)
        norm = (norm * 255).astype(np.uint8)
        texture = Texture.create(size=(norm.shape[1], norm.shape[0]), colorfmt='luminance')
        texture.blit_buffer(norm.tobytes(), colorfmt='luminance', bufferfmt='ubyte')
        texture.flip_vertical()
        self.img.texture = texture

class DashboardApp(App):
    def build(self):
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.BLUETOOTH, Permission.BLUETOOTH_ADMIN, Permission.ACCESS_FINE_LOCATION])

        self.brain = TelemetryBrain()
        self.connection = obd.OBD()
        self.layout = GridLayout(cols=2, padding=10, spacing=10)
        self.widgets = {}

        labels = ["RPM", "Speed", "HP", "Torque Nm", "VE %", "Fuel L/h", "Coolant C", "Load %", "Total Fuel", "Stability"]
        for label in labels:
            box = GridLayout(rows=2, size_hint_y=None, height=120)
            lbl = Label(text=label, font_size='14sp', color=(.5,.5,.5,1))
            val = Label(text="0.0", font_size='32sp', bold=True)
            box.add_widget(lbl); box.add_widget(val)
            self.layout.add_widget(box); self.widgets[label] = val

        self.leader_lbl = Label(text="0-100: N/A", font_size='16sp', color=(0,1,1,1), size_hint_y=None, height=50)
        self.layout.add_widget(self.leader_lbl)
        self.layout.add_widget(FuelMapWidget(self.brain))

        Clock.schedule_interval(self.update, 0.1)
        return self.layout

    def update(self, dt):
        m = self.brain.get_metrics(self.connection)
        keys = ["RPM", "Speed", "HP", "Torque Nm", "VE %", "Fuel L/h", "Coolant C", "Load %", "Total Fuel", "Stability"]
        for i, key in enumerate(keys):
            self.widgets[key].text = f"{m[i]:.1f}"
            limit = 6000 if m[6] > 75 else 3500
            if key == "RPM": self.widgets[key].color = (1,0,0,1) if m[i] > limit else (0,1,0,1)
            if key == "Stability": self.widgets[key].color = (0,1,0,1) if m[i] < 2.5 else (1,0,0,1)
        self.leader_lbl.text = f"0-100: {', '.join([f'{t:.2f}s' for t in self.brain.leaderboard])}"

if __name__ == "__main__":
    DashboardApp().run()
