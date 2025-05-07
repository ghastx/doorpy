# doorpy/display.py
import logging

try:
    from dot3k.lcd import LCD
    LCD_AVAILABLE = True
except (ImportError, RuntimeError) as e:
    logging.warning(f"LCD non disponibile: {e}")
    LCD_AVAILABLE = False

class DummyLCD:
    def clear(self):
        logging.info("[DummyLCD] clear() chiamato")

    def write(self, message):
        logging.info(f"[DummyLCD] write(): {message}")

class DoorBellDisplay:
    def __init__(self, config):
        """
        Gestisce il display LCD. Se è connesso imposta self.lcd con LCD reale, altrimenti usa dummyLCD e scrive sul log.
        """
        self.config = config
        if LCD_AVAILABLE:
            try:
                self.lcd = LCD()
            except Exception as e:
                logging.error(f"Errore inizializzazione LCD: {e}")
                self.lcd = DummyLCD()
        else:
            self.lcd = DummyLCD()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

    def show_message(self, message: str):
        """
        Pulisce il display se disponibile, altrimenti logga in debug.
        """
        self.logger.info("Clearing display")
        if self.lcd:
            self.lcd.clear()
        else:
            self.logger.debug("LCD sostituito con DummyLCD, clear() registrato.")