import csv
from kivy.clock import Clock

class TelemetryReplayer:
    def __init__(self, ui_update_callback):
        self.ui_update = ui_update_callback
        self.is_playing = False
        self._event = None
        self.data = []

    def start_ghost_mode(self, file_path, ghost_ui_callback):
        """Plays log data to a secondary UI callback without stopping live data"""
        self.ghost_callback = ghost_ui_callback
        self._load_file(file_path[0])
        self.current_index = 0
        Clock.schedule_interval(self.ghost_step, 0.1)

    def ghost_step(self, dt):
        if self.current_index < len(self.data):
            row = self.data[self.current_index]
            # Send only key metrics for comparison
            ghost_metrics = {
                "rpm": float(row.get('rpm', 0)),
                "speed": float(row.get('speed', 0)),
                "hp": float(row.get('hp', 0)),
                "torque": float(row.get('torque', 0)),
                "ve": float(row.get('ve', 0)),
                "fuel_rate": float(row.get('fuel_rate', 0)),
                "coolant": float(row.get('coolant', 0)),
                "load": float(row.get('load', 0)),
                "fuel_total": float(row.get('fuel_total', 0)),
                "stability": float(row.get('stability', 0))
            }
            self.ghost_callback(ghost_metrics)
            self.current_index += 1
            return True
        return False

    def _load_file(self):
        try:
            with open(self.filepath, 'r') as f:
                reader = csv.DictReader(f)
                self.data = [row for row in reader]
        except Exception as e:
            print(f"Replay Error: {e}")

    def start_replay(self, file_path, speed=1.0):
        # We schedule the update based on the original log frequency
        # Clock.schedule_interval(self.step, 0.1 / speed)
        self.data = []
        try:
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                self.data = list(reader)
            
            self.current_frame = 0
            self.is_playing = True
            # Playback at 10Hz (0.1s) to match original recording
            self._event = Clock.schedule_interval(self._tick, 0.1)
        except Exception as e:
            print(f"Replay Error: {e}")

    def _tick(self, dt):
        if self.current_frame < len(self.data):
            row = self.data[self.current_frame]
            # [rpm, speed, hp, torque, ve, fuel, coolant, load, fuel_total, stability]
            metrics_list = [
                float(row.get('rpm', 0)),
                float(row.get('speed', 0)),
                float(row.get('hp', 0)),
                float(row.get('torque', 0)),
                float(row.get('ve', 0)),
                float(row.get('fuel_rate', 0)),
                float(row.get('coolant', 0)),
                float(row.get('load', 0)),
                float(row.get('fuel_total', 0)),
                float(row.get('stability', 0)),
                float(row.get('temp_in', 25))
            ]
            self.ui_update(metrics_list)
            self.current_frame += 1
        else:
            self.stop_replay()
            
    def stop_replay(self):
        self.is_playing = False
        if self._event:
            Clock.unschedule(self._event)
            