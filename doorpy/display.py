# doorpy/display.py
import logging
from dot3k.lcd import LCD

class DoorBellDisplay:
    def __init__(self, config):
        self.lcd = LCD()
        self.config = config
        logging.basicConfig(level=logging.INFO)

    def show_message(self, message: str):
        logging.info(f"Displaying message: {message}")
        self.lcd.clear()
        # Split message if longer than display width
        self.lcd.write(message)

    def clear(self):
        logging.info("Clearing display")
        self.lcd.clear()
