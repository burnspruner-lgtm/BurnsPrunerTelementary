import csv
import time
import os
from kivy.utils import platform

class DataLogger:
    def __init__(self):
        # Determine path based on device
        if platform == 'android':
            from android.storage import primary_external_storage_path
            base_dir = os.path.join(primary_external_storage_path(), 'TelemetryLogs')
        else:
            # On PC, save in the current folder
            base_dir = os.path.join(os.getcwd(), 'TelemetryLogs')

        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        self.filepath = os.path.join(base_dir, f"run_log_{int(time.time())}.csv")
        self.headers = ["timestamp", "rpm", "speed", "hp", "torque", "ve", "fuel_rate", "coolant", "load", "fuel_total", "stability", "temp_in"]
        
        # Create file and write headers immediately
        with open(self.filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.headers)

    def log_sample(self, metrics):
        # metrics list order must match headers logic in main.py 11-item list
        # [rpm, speed, hp, torque, ve, fuel_rate, coolant, load, fuel_total, stability, temp_in]
        timestamp = time.time()
        
        # row will now be 1(timestamp) + 11(metrics)
        # Let's map explicitly to be safe:
        if len(metrics) >= 11:
            row = [timestamp] + metrics
        else:
            # Fallback if temp_in is missing
            try:
                row = [timestamp] + metrics + [25.0] 
            except:
                row = [timestamp] + metrics
                while len(row) < len(self.headers):
                    row.append(25.0)
                
        
        try:
            with open(self.filepath, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(row)
        except Exception as e:
            print(f"Logging Error: {e}")