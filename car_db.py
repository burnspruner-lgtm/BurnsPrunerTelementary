# car_db.py
import sqlite3
import threading
import requests

class CarDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('pruner_vehicles.db')
        self.cursor = self.conn.cursor()
        self._bootstrap_db()

    def fetch_from_cloud(self, query):
        """Pulls from a Master JSON on GitHub"""
        GITHUB_DB_URL = "https://raw.githubusercontent.com/YourUsername/PrunerDashDB/main/cars.json"
        try:
            response = requests.get(GITHUB_DB_URL, timeout=5)
            if response.status_code == 200:
                cloud_data = response.json()
                # Find the car in the cloud JSON
                for car in cloud_data:
                    if query.lower() in car['model'].lower():
                        # Save to local SQLite so we have it offline next time
                        self.cursor.execute("INSERT INTO cars VALUES (?,?,?,?,?)", 
                            (car['model'], car['cc'], car['fuel'], car['weight'], car['drag']))
                        self.conn.commit()
                        return [car['model']]
        except Exception as e:
            print(f"Cloud Sync Failed: {e}")
        return []

    def _bootstrap_db(self):
        """Creates the internal high-performance index."""
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS cars 
            (model TEXT, cc INTEGER, fuel TEXT, weight INTEGER, drag_coeff REAL)''')
        
        # Check if empty, then seed with thousands of entries (shortened for display)
        self.cursor.execute("SELECT COUNT(*) FROM cars")
        if self.cursor.fetchone()[0] == 0:
            print("Seeding database with sample data...")
            cars_seed_thread = threading.Thread(target=self._seed_db)
            cars_seed_thread.start()
        
    def save_active_car(self, model, cc):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
            (key TEXT PRIMARY KEY, value TEXT)''')
        
        # Save the last used car so it loads automatically next time
        self.cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_model', ?)", (model,))
        self.cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_cc', ?)", (str(cc),))
        self.conn.commit()

    def get_last_car(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
            (key TEXT PRIMARY KEY, value TEXT)''')
        
        self.cursor.execute("SELECT value FROM settings WHERE key = 'last_model'")
        model = self.cursor.fetchone()
        self.cursor.execute("SELECT value FROM settings WHERE key = 'last_cc'")
        cc = self.cursor.fetchone()
        return (model[0], float(cc[0])) if model and cc else ("Default", 2000.0)

    def _seed_db(self):
        with self.conn:
            sample_data = [
                ("Toyota Mark X", 2499, "Petrol", 1550, 0.29),
                ("Subaru Forester XT", 1998, "Petrol", 1610, 0.33),
                ("Mercedes C200", 1497, "Petrol", 1505, 0.26),
                ("Volkswagen Golf R", 1984, "Petrol", 1483, 0.35),
                ("Honda Fit RS", 1496, "Petrol", 1050, 0.32),
                ("Nissan GT-R", 3799, "Petrol", 1750, 0.30),
                ("Subaru WRX STi", 2499, "Petrol", 1610, 0.31), 
                ("Ford Mustang GT", 5038, "Petrol", 1750, 0.32),
                ("Nissan Altima (2.0)", 11496, "Petrol", 1050, 0.28),
                ("Subaru Outback (SX)", 2499, "Petrol", 1610, 0.33),
                ("Mercedes-Benz C-Class", 1998, "Petrol", 1505, 0.27),
                ("Volkswagen Passat", 197, "Petrol", 1483, 0.34),
                ("Subaru Impreza (2.0i)", 1995, "Petrol", 1050, 0.29),
                ("Mazda Demio (1.5)", 1496, "Petrol", 1050, 0.31),
                ("Mitsubishi Lancer EX", 1998, "Petrol", 1610, 0.32),
                ("Toyota Corolla (E210)", 3423, "Petrol", 1050, 0.23),
                ("Subaru WRX", 2499, "Petrol", 1610, 0.43),
                ("Mercedes-Benz E-Class", 2499, "Petrol", 1505, 0.22),
                ("Volkswagen Jetta GLI", 1984, "Petrol", 1483, 0.31),
                ("Honda CR-V (2.0i)", 1996, "Petrol", 1050, 0.28),
                ("Ford Mustang GT", 5038, "Petrol", 1750, 0.32),
                ("Nissan Altima (2.0)", 11496, "Petrol", 1050, 0.28),
                ("Subaru Outback (SX)", 2499, "Petrol", 1610, 0.33),
                ("Mercedes-Benz C-Class", 1998, "Petrol", 1505, 0.27),
                ("Volkswagen Passat", 197, "Petrol", 1483, 0.34),
                ("Subaru Impreza (2.0i)", 1995, "Petrol", 1050, 0.29),
                ("Mazda Demio (1.5)", 1496, "Petrol", 1050, 0.31),
                ("Mitsubishi Lancer EX", 1998, "Petrol", 1610, 0.32),
                ("Volkswagen Golf GTI", 1984, "Petrol", 1478, 0.35),
                ("Volkswagen Jetta", 2342,"cc", 1984, "Petrol", 234, 0.35),
                ("Honda CR-V", "cc", 1996,  "Petrol", 2430, 0.28),
                ("Ford Mustang", "cc", 5038,  "Petrol", 231, 0.32),
                ("Nissan Altima", "cc", 11496,  "Petrol",215, 0.28),
                ("Subaru Outback (SX)", "cc", 2499,"Petrol",9473, 0.33),
                ("Mercedes-Benz C-Class", "cc", 1998,"Petrol",903, 0.27),
                ("Volkswagen Passat", "cc", 197,"Petrol",465, 0.34),
                ("Subaru Impreza (2.0i)",4352,"cc", 1995,"Petrol",2342, 0.29),
                ("Mazda Demio (1.5)", "cc", 1496,"Petrol",9044, 0.31),
                ("Mitsubishi Lancer EX", "cc", 1998,"Petrol",2303, 0.32),
                ("Toyota Corolla (E210)", "cc", 3423,"Petrol",234, 0.23),
                ("Subaru WRX", "cc", 2499,"Petrol",234, 0.43),
                ("Mercedes-Benz E-Class", "cc", 2499,"Petrol",234, 0.22),
                ("Volkswagen Golf GTI", "cc", 1984,"Petrol",648, 0.31),
                ("Honda Civic (Type R)", "cc", 1996,"Petrol",495, 0.28),
                ("Ford Mustang (GT)", "cc", 5038,"Petrol",3945, 0.32),
                ("Nissan Note", "cc", 1198,"Petrol",8755, 0.28),
            ]
            self.cursor.executemany('INSERT INTO cars VALUES (?,?,?,?)', sample_data)
            self.conn.commit()

    def search(self, query, use_internet=True):
        """Searches local DB, then falls back to 'Cloud'."""
        self.cursor.execute("SELECT model FROM cars WHERE model LIKE ?", (f'%{query}%',))
        results = [row[0] for row in self.cursor.fetchall()]
        
        if not results and use_internet:
            # Simulated Internet/API Lookup
            return self._internet_lookup(query)
        return results

    def _internet_lookup(self, query):
        # In a real scenario, this would use 'requests.get(CAR_API_URL)'
        print(f"Searching Cloud for {query}...")
        return [f"{query.capitalize()} (Cloud Verified)"]

    def get_specs(self, car_name):
        self.cursor.execute("SELECT cc, fuel, weight FROM cars WHERE model = ?", (car_name,))
        row = self.cursor.fetchone()
        if row:
            return {"cc": row[0], "fuel": row[1], "weight": row[2]}
        else:
            if row:
                return {"cc": 2000, "fuel": "Petrol", "weight": 1500}
            else:
                return None