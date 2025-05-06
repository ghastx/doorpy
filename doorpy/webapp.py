# doorpy/webapp.py
from flask import Flask, jsonify, request
from doorpy.display import DoorBellDisplay
from doorpy.controller import setup_gpio, unlock
from doorpy.telephony import Telephony
from doorpy.config import load_config
import threading

# Carica configurazione
def main():
    cfg = load_config()
    ring_pin, unlock_pin = setup_gpio(cfg)

    def on_ring():
        display.show_message("Chiamata")
        t.call_extension()

    def on_unlock():
        unlock(unlock_pin)

    display = DoorBellDisplay(cfg)
    t = Telephony(cfg, on_ring, {'unlock_code': cfg['dtmf']['unlock_code'], 'callback': on_unlock})

    # Avvia thread telephony
    threading.Thread(target=t.start, daemon=True).start()

    app = Flask(__name__)
    @app.route('/unlock', methods=['POST'])
    def manual_unlock():
        unlock(unlock_pin)
        return jsonify({'status': 'unlocked'})

    app.run(host='0.0.0.0', port=cfg['general']['web_port'])

if __name__ == '__main__':
    main()
