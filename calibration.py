from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.storage.jsonstore import JsonStore
from kivy.app import App


class CalibrationPopup(Popup):
    def __init__(self, brain, db_instance, **kwargs):
        super().__init__(**kwargs)
        self.brain = brain
        self.db = db_instance
        self.store = JsonStore('car_settings.json')
        
        self.title = "VEHICLE CONFIGURATOR"
        self.size_hint = (0.9, 0.7)
        self.auto_dismiss = False

        # --- LAYOUTS ---
        main_layout = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        # 1. SEARCH SECTION
        search_box = BoxLayout(size_hint_y=None, height=50, spacing=10)
        self.search_input = TextInput(hint_text="Search Car (e.g., Subaru)", multiline=False, size_hint_x=0.7)
        search_btn = Button(text="🔍", size_hint_x=0.3, background_color=(0, 1, 1, 1))
        search_btn.bind(on_press=self.do_search)
        search_box.add_widget(self.search_input)
        search_box.add_widget(search_btn)
        
        # 2. RESULTS SPINNER (Dropdown)
        self.car_selector = Spinner(
            text='Select a Car',
            values=list(self.db.db.keys()),
            size_hint_y=None,
            height=50
        )
        self.car_selector.bind(text=self.on_car_select)

        # 3. SPECS DISPLAY (The "Credential" Area)
        specs_grid = GridLayout(cols=2, spacing=10, size_hint_y=None, height=100)
        
        specs_grid.add_widget(Label(text="Engine (cc):", halign="right"))
        # Load saved or default
        saved_cc = self.store.get('engine')['cc'] if self.store.exists('engine') else 2000
        self.cc_input = TextInput(text=str(saved_cc), multiline=False, input_filter='int', readonly=True)
        specs_grid.add_widget(self.cc_input)

        # 4. EDIT / OK CONTROLS
        ctrl_box = BoxLayout(size_hint_y=None, height=50, spacing=20)
        
        self.edit_btn = Button(text="EDIT ✏️", background_color=(1, 0.5, 0, 1))
        self.edit_btn.bind(on_press=self.enable_edit)
        
        self.ok_btn = Button(text="OK ✅", background_color=(0, 1, 0, 1))
        self.ok_btn.bind(on_press=self.save_and_close)
        
        ctrl_box.add_widget(self.edit_btn)
        ctrl_box.add_widget(self.ok_btn)

        # Add all to Main
        main_layout.add_widget(Label(text="Select or Enter Vehicle Details", size_hint_y=None, height=30))
        main_layout.add_widget(search_box)
        main_layout.add_widget(self.car_selector)
        main_layout.add_widget(specs_grid)
        main_layout.add_widget(Label(text="")) # Spacer
        main_layout.add_widget(ctrl_box)

        self.content = main_layout

    def do_search(self, instance):
        query = self.search_input.text
        results = self.db.search(query)
        if results:
            self.car_selector.values = results
            self.car_selector.text = results[0] # Auto-select first result
        else:
            self.car_selector.values = []
            self.car_selector.text = "No Car Found"

    def on_car_select(self, spinner, text):
        specs = self.db.get_specs(text)
        if specs:
            self.cc_input.text = str(specs['cc'])
            self.fuel_type = specs.get('fuel', 'Petrol')
            
        self.cc_input.readonly = True 

    def enable_edit(self, instance):
        self.cc_input.readonly = False
        self.cc_input.background_color = (1, 1, 0.8, 1) # Light yellow to show active

    def save_and_close(self, instance):
        try:
            cc = int(self.cc_input.text)
            # Update Brain
            self.brain.displacement = cc / 1000.0
            # Save to Store
            self.store.put('engine', cc=cc) 
            self.dismiss()
        except ValueError:
            self.cc_input.text = "Error"

    def save_and_apply(self, instance):      
        # 1. Get the data from the UI
        selected_car = self.car_selector.text
        try:
            new_cc = float(self.cc_input.text)
        except ValueError:
            new_cc = 2000 # Fallback default
        
        # 2. Save to JsonStore (Persistence)
        self.db.save_active_car(selected_car, new_cc) # self.store.put('active_car', model=selected_car, cc=new_cc)
        
        # 3. DIRECT UPDATE TO BRAIN MATH
        try:
            if self.brain:
                self.brain.displacement = new_cc / 1000.0
                print(f"✅ Brain Reconfigured: Now calculating for {self.brain.displacement}L")
        except:
            print("⚠️ Brain not initialized. Cannot update displacement.")
            pass
        
        # 4. Update the App's global state (from our previous fix)
        app = App.get_running_app()
        app.system_state["active_cc"] = new_cc / 1000.0
        
        # The Guard Clause
        if not app.system_state["has_adapter"]:
            print("Warning: No real adapter. VE calculations will stay in Mock Mode.")
            # Proceed with updating the CC in the DB, but skip OBD commands
        else:
            # Proceed with real calibration commands to the ECU
            self.brain.update_ve_table()
            
        # CLOSE THE POPUP
        self.dismiss()