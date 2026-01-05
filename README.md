# BurnsPrunerTelementary

A Python-based automotive telemetry dashboard built with **Kivy** and **Python-OBD**. This application connects to an ELM327 Bluetooth/USB adapter to visualize real-time engine data, estimate performance metrics, and generate fuel maps.

## 🚀 Features

* **Real-Time Dashboard**: Monitors RPM, Speed, Coolant Temp, Engine Load, and Fuel Trims.
* **Performance Metrics**:
    * **Live Horsepower & Torque**: Estimated based on Mass Air Flow (MAF) readings.
    * **Volumetric Efficiency (VE)**: Calculates engine breathing efficiency in real-time.
    * **0-100 km/h Timer**: Automatic tracking of acceleration runs with a top-3 leaderboard.
* **Fuel Mapping**: Generates a dynamic heat map (Load vs. RPM) of fuel consumption as you drive.
* **Engine Stability**: Monitors Short Term Fuel Trim (STFT) standard deviation to detect engine smoothness.
* **Background Threading**: Ensures the UI stays smooth by running OBD queries in a separate worker thread.

## 🛠️ Installation & Requirements

### Desktop (Development)
To run locally on your laptop using a clean Virtual Environment:
1.  Clone the repository.
2.  **Create and Activate Virtual Environment**:
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # Mac/Linux:
    source .venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Run the application:
    ```bash
    python3 main.py
    ```

### Android (Buildozer)
The `buildozer` tool handles the entire packaging process. You do not need to manually move `main.py` to your phone.
1.  **Connect** your Android device via USB with "USB Debugging" enabled.
2.  **Run the command**:
    ```bash
    buildozer android debug deploy run
    ```
3.  **Result**: Buildozer compiles your code into an APK, installs it, and launches the app on your phone automatically.

## 🧪 Smart Connection Logic
The app is designed to be "plug and play":
* **Auto-Detection**: It scans for a real OBD-II adapter first.
* **Simulator Mode**: If no car is detected (e.g., you are testing on your couch), it automatically triggers a **Mock Connection** so you can see the telemetry logic in action without a vehicle.
    ```

## 🧪 Car-Free Testing (Mock Mode)
The app includes a built-in simulator. If no OBD adapter is found, the app automatically switches to **Mock Mode**. This allows you to test the dashboard on your laptop or phone without being connected to a car.

## ⚙️ Configuration

The application currently defaults to a **2.0L Engine displacement** for VE calculations.
* To adjust this, modify the `TelemetryBrain(displacement=2.0)` initialization in `main.py`.

## 📦 Dependencies

* [Kivy](https://kivy.org/) (v2.2.1) - UI Framework
* [python-obd](https://python-obd.readthedocs.io/) (v0.7.1) - OBD-II Communication
* [NumPy](https://numpy.org/) - Data processing and Fuel Map generation

## 📱 Permissions (Android)

The application requires Bluetooth permissions to communicate with the ELM327 adapter.
* `BLUETOOTH`
* `BLUETOOTH_ADMIN`
* `BLUETOOTH_SCAN` (Android 12+)
* `BLUETOOTH_CONNECT` (Android 12+)
* `ACCESS_FINE_LOCATION` (Required for Bluetooth scanning on Android)

## ⚠️ Hardware Note

You need an **ELM327 OBD-II Adapter** (Bluetooth or USB) connected to your vehicle to receive data. The application will attempt to auto-connect to the first available port.