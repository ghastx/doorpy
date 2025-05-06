# doorpy/controller.py
import RPi.GPIO as GPIO
import logging
import time  # Necessario per time.sleep in unlock

def setup_gpio(cfg):
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(cfg['ring_pin'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(cfg['unlock_pin'], GPIO.OUT)
    GPIO.output(cfg['unlock_pin'], GPIO.LOW)
    logging.info("GPIO configurato")
    return cfg['ring_pin'], cfg['unlock_pin']

# Funzione per sblocco porta
def unlock(door_pin):
    logging.info("Sblocco porta")
    GPIO.output(door_pin, GPIO.HIGH)
    time.sleep(1)
    GPIO.output(door_pin, GPIO.LOW)

def start(self):
        try:
            # Inizializza libreria e trasporto
            self.lib.init(log_cfg=pj.LogConfig(level=3))
            self.lib.create_transport(pj.TransportType.UDP)
            # Rilevazione dispositivi audio se necessario
            snd_devs = self.lib.enum_snd_dev()
            if not snd_devs:
                raise RuntimeError('Nessun dispositivo audio disponibile')
            if self.audio_dev is None:
                # auto-select first available
                dev_index = snd_devs[0].driver
                cap_dev = dev_index
                play_dev = dev_index
                logging.info(f"Audio auto-detect: dev {dev_index}")
            else:
                cap_dev, play_dev = self.audio_dev
                max_index = max(d.driver for d in snd_devs)
                if cap_dev > max_index or play_dev > max_index:
                    raise RuntimeError(f"Indice audio non valido: {self.audio_dev}")
            # Imposta dispositivi audio (capture, playback)
            self.lib.set_snd_dev(cap_dev, play_dev)
            self.lib.start()

            # Configura account SIP
            acc_cfg = pj.AccountConfig(domain=self.sip_cfg['domain'],
                                       username=self.sip_cfg['username'],
                                       password=self.sip_cfg['password'],
                                       proxy=[self.sip_cfg['proxy']])
            self.account = self.lib.create_account(acc_cfg)
            self.account.set_callback(self)
            logging.info(f"SIP registrato su {self.sip_cfg['domain']}")
        except pj.Error as e:
            logging.error(f"Errore inizializzazione PJSIP: {e}")
            raise
        except Exception as e:
            logging.error(f"Errore audio setup: {e}")
            raise
            raise

    def call_extension(self):
        # Effettua chiamata verso l'interno configurato
        uri = f"sip:{self.sip_cfg['extension']}@{self.sip_cfg['domain']}"
        logging.info(f"Chiamata verso {uri}")
        self.current_call = self.account.make_call(uri)

    def on_incoming_call(self, call):
        # Gestione chiamata in ingresso dal citofono
        logging.info(f"Chiamata in ingresso: {call.info().remote_uri}")
        call_cb = CallCallback(call, self.on_dtmf)
        call.set_callback(call_cb)
        call.answer(200)
        self.on_ring()

class CallCallback(pj.CallCallback):
    def __init__(self, call, dtmf_handler):
        super().__init__(call)
        self.dtmf_handler = dtmf_handler

    def on_dtmf_digit(self, digits):
        # Gestione toni DTMF per sblocco
        logging.info(f"Ricevuto DTMF: {digits}")
        if digits == self.dtmf_handler['unlock_code']:
            self.dtmf_handler['callback']()
