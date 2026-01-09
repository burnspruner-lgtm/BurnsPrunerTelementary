from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, InstructionGroup
from kivy.properties import ListProperty
from kivy.graphics import Color, Line, InstructionGroup, Ellipse, Rectangle

class StressMeter(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dot_pos = (0.5, 0.5)

    def update(self, load, torque_percent):
        # Maps engine load and torque to a 2D grid
        self.dot_pos = (load / 100, torque_percent / 100)
        self.draw()

    def draw(self):
        self.canvas.clear()
        with self.canvas:
            Color(0.3, 0.3, 0.3, 1)
            # Draw Crosshair
            Line(points=[self.center_x, self.y, self.center_x, self.top], width=1)
            Line(points=[self.x, self.center_y, self.right, self.center_y], width=1)
            
            # The "Stress" Dot
            Color(1, 0.5, 0, 1)
            curr_x = self.x + (self.width * self.dot_pos[0])
            curr_y = self.y + (self.height * self.dot_pos[1])
            Ellipse(pos=(curr_x-5, curr_y-5), size=(10, 10))

class ShiftBar(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.level = 0  # 0 to 1
        with self.canvas.before:
            Color(1, 1, 1, 1) # White
            Line(rectangle=(self.x, self.y, self.width, self.height), width=2)

    def update(self, current_rpm, max_rpm=7000):
        self.level = min(current_rpm / max_rpm, 1.0)
        self.canvas.clear()
        with self.canvas:
            # Background
            Color(0.1, 0.1, 0.1, 1)
            Rectangle(pos=self.pos, size=self.size)
            
            # Dynamic Color logic
            if self.level < 0.7: Color(0, 1, 0, 1)      # Green
            elif self.level < 0.9: Color(1, 1, 0, 1)    # Yellow
            else: Color(1, 0, 0, 1)                    # Red
            
            Rectangle(pos=self.pos, size=(self.width, self.height * self.level))

class RealTimeGraph(Widget):
    points = ListProperty([])

    def __init__(self, label="Data", color=(0, 1, 0, 1), **kwargs):
        super().__init__(**kwargs)
        self.label_name = label
        self.line_color = color
        self.buffer = []

    def update_value(self, value, max_val=7000):
        # Scale value to widget height
        normalized = (value / max_val) * self.height
        self.buffer.append(normalized)
        
        if len(self.buffer) > 50: # Show last 50 data points
            self.buffer.pop(0)
            
        self.draw_graph()

    def draw_graph(self):
        self.canvas.after.clear()
        with self.canvas.after:
            Color(*self.line_color)
            points = []
            x_step = self.width / 50
            for i, val in enumerate(self.buffer):
                points.extend([self.x + (i * x_step), self.y + val])
            
            if len(points) >= 4:
                Line(points=points, width=1.5)