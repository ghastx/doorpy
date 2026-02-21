#!/usr/bin/env python3
"""
Sistema Citofono-VoIP per Terraneo con Baresip
Raspberry Pi 3B+ - Integrazione con centralino Grandstream

Copyright (C) 2025 Simone

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

Versione: 1.1
"""

import RPi.GPIO as GPIO
import time
import subprocess
import signal
import sys
import os
from threading import Thread, Event, Lock
import logging

# ============================================================
# CONFIGURAZIONE
# ============================================================

def _load_config():
    """Carica la configurazione da config.env se presente."""
    config_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.env'),
        '/etc/citofono-voip/config.env',
    ]
    for path in config_paths:
        if os.path.isfile(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, _, value = line.partition('=')
                        os.environ.setdefault(key.strip(), value.strip())
            break

_load_config()

def _env(key, default, cast=str):
    """Legge un valore dall'ambiente con fallback al default."""
    val = os.environ.get(key, default)
    return cast(val)

# GPIO Pins (BCM numbering)
PIN_SUONERIA = _env('PIN_SUONERIA', '17', int)
PIN_RELE_PORTONE = _env('PIN_RELE_PORTONE', '27', int)
PIN_LED_STATO = _env('PIN_LED_STATO', '22', int)

# Configurazione SIP
SIP_USERNAME = _env('SIP_USERNAME', '2000')
SIP_PASSWORD = _env('SIP_PASSWORD', '')
SIP_DOMAIN = _env('SIP_DOMAIN', 'centralino.ponsacco.local')
SIP_PORT = _env('SIP_PORT', '5060', int)

# Numero da chiamare quando suona il citofono
NUMERO_DA_CHIAMARE = _env('NUMERO_DA_CHIAMARE', '6400')

# Codice DTMF per aprire il portone
DTMF_APRI_PORTONE = _env('DTMF_APRI_PORTONE', '*9')

# Timing
DEBOUNCE_SUONERIA_MS = _env('DEBOUNCE_SUONERIA_MS', '300', int)
DURATA_APERTURA_SEC = _env('DURATA_APERTURA', '2', int)
TIMEOUT_CHIAMATA_SEC = _env('TIMEOUT_CHIAMATA', '60', int)
RITARDO_POST_SUONERIA_SEC = 0.5

# Audio - Verifica con 'aplay -l' e 'arecord -l'
AUDIO_PLAY_DEVICE = _env('AUDIO_PLAY_DEVICE', 'hw:1,0')
AUDIO_REC_DEVICE = _env('AUDIO_REC_DEVICE', 'hw:1,0')

# Logging
LOG_FILE = _env('LOG_FILE', '/var/log/citofono-voip.log')
LOG_LEVEL = logging.INFO

# ============================================================
# SETUP LOGGING
# ============================================================

def _setup_logging():
    """Configura il logging evitando handler duplicati."""
    handlers = [logging.StreamHandler()]
    log_dir = os.path.dirname(LOG_FILE) or '/var/log'
    if os.path.isdir(log_dir) and os.access(log_dir, os.W_OK):
        handlers.append(logging.FileHandler(LOG_FILE))
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=handlers,
    )

_setup_logging()
logger = logging.getLogger(__name__)


# ============================================================
# CLASSI
# ============================================================

class BaresipController:
    """Controlla Baresip via subprocess/stdio."""

    def __init__(self):
        self.processo = None
        self.lock = Lock()
        self.chiamata_attiva = Event()
        self.running = False
        self._drain_thread = None

    def avvia(self):
        """Avvia il processo Baresip."""
        logger.info("Avvio Baresip...")

        # Termina eventuali istanze precedenti
        subprocess.run(['pkill', '-9', 'baresip'], capture_output=True)
        time.sleep(1)

        # Avvia Baresip con stdin pipe; stdout viene drenato per evitare
        # che il buffer si riempia e blocchi il processo
        self.processo = subprocess.Popen(
            ['baresip'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # Avvia thread per drenare stdout
        self._drain_thread = Thread(target=self._drain_stdout, daemon=True)
        self._drain_thread.start()

        # Attendi registrazione SIP
        time.sleep(4)

        if self.processo.poll() is None:
            logger.info("Baresip avviato e connesso")
            self.running = True
            return True
        else:
            logger.error("Baresip non si è avviato")
            return False

    def _drain_stdout(self):
        """Legge e scarta l'output di baresip per evitare blocchi sulla pipe."""
        try:
            while True:
                line = self.processo.stdout.readline()
                if not line:
                    break
                # Log opzionale per debug (disabilitato per default)
                logger.debug("baresip: %s", line.decode(errors='replace').rstrip())
        except Exception:
            pass

    def chiama(self, numero):
        """Effettua una chiamata."""
        logger.info("Chiamata in uscita verso %s", numero)
        try:
            cmd = f"/dial {numero}\n"
            self.processo.stdin.write(cmd.encode())
            self.processo.stdin.flush()
            self.chiamata_attiva.set()
            return True
        except Exception as e:
            logger.error("Errore chiamata: %s", e)
            return False

    def riaggancia(self):
        """Termina la chiamata."""
        logger.info("Termine chiamata")
        try:
            self.processo.stdin.write(b"/hangup\n")
            self.processo.stdin.flush()
            self.chiamata_attiva.clear()
            return True
        except Exception as e:
            logger.error("Errore hangup: %s", e)
            return False

    def termina(self):
        """Termina Baresip."""
        self.running = False
        try:
            self.processo.stdin.write(b"/quit\n")
            self.processo.stdin.flush()
            self.processo.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            if self.processo:
                self.processo.terminate()
        logger.info("Baresip terminato")


class PortoneController:
    """Gestisce il relè del portone."""

    def __init__(self, pin):
        self.pin = pin
        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, GPIO.LOW)
        self.lock = Lock()

    def apri(self, durata=None):
        """Attiva il relè per aprire il portone."""
        if durata is None:
            durata = DURATA_APERTURA_SEC
        with self.lock:
            logger.info(">>> APERTURA PORTONE (durata: %ds) <<<", durata)
            GPIO.output(self.pin, GPIO.HIGH)
            time.sleep(durata)
            GPIO.output(self.pin, GPIO.LOW)
            logger.info(">>> PORTONE CHIUSO <<<")


class SuoneriaMonitor:
    """Monitora il segnale di suoneria del citofono."""

    def __init__(self, pin, callback):
        self.pin = pin
        self.callback = callback
        self.ultimo_trigger = 0

        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def avvia(self):
        """Avvia il monitoraggio con interrupt."""
        try:
            GPIO.add_event_detect(
                self.pin,
                GPIO.RISING,
                callback=self._on_trigger,
                bouncetime=DEBOUNCE_SUONERIA_MS,
            )
            logger.info("Monitoraggio suoneria attivo su GPIO%d (interrupt)", self.pin)
        except Exception as e:
            logger.warning("Edge detection fallito, uso polling: %s", e)
            Thread(target=self._polling_loop, daemon=True).start()

    def _polling_loop(self):
        """Fallback: controlla GPIO con polling rilevando il fronte di salita."""
        logger.info("Monitoraggio suoneria (polling) attivo su GPIO%d", self.pin)
        time.sleep(2)  # stabilizzazione iniziale

        ultimo_stato = GPIO.input(self.pin)
        debounce_sec = DEBOUNCE_SUONERIA_MS / 1000.0

        while True:
            stato = GPIO.input(self.pin)

            # Rileva fronte di salita (LOW -> HIGH) per coerenza con GPIO.RISING
            if stato == GPIO.HIGH and ultimo_stato == GPIO.LOW:
                self._on_trigger(self.pin)
                time.sleep(debounce_sec)

            ultimo_stato = stato
            time.sleep(0.02)

    def _on_trigger(self, channel):
        """Callback quando viene rilevata la suoneria."""
        now = time.time()
        if now - self.ultimo_trigger > (DEBOUNCE_SUONERIA_MS / 1000.0):
            self.ultimo_trigger = now
            logger.info("!!! SUONERIA CITOFONO RILEVATA !!!")
            self.callback()


class DTMFHandler:
    """Gestisce la ricezione dei toni DTMF."""

    def __init__(self, baresip, portone):
        self.baresip = baresip
        self.portone = portone
        self.buffer = ""
        self.ultimo_dtmf = 0
        self.running = False

    def avvia(self):
        """Segna l'handler come attivo."""
        self.running = True
        logger.info("Handler DTMF attivo")

    def processa_dtmf(self, tono):
        """Processa un tono DTMF ricevuto."""
        now = time.time()

        # Reset buffer se passato troppo tempo
        if now - self.ultimo_dtmf > 3:
            self.buffer = ""

        self.buffer += tono
        self.ultimo_dtmf = now

        logger.debug("DTMF buffer: %s", self.buffer)

        # Controlla se corrisponde al codice apertura
        if self.buffer.endswith(DTMF_APRI_PORTONE):
            logger.info("Codice apertura ricevuto: %s", DTMF_APRI_PORTONE)
            self.portone.apri()
            self.buffer = ""

    def termina(self):
        self.running = False


class LEDStatus:
    """Gestisce il LED di stato (opzionale)."""

    def __init__(self, pin):
        self.pin = pin
        if pin:
            GPIO.setup(self.pin, GPIO.OUT)
            GPIO.output(self.pin, GPIO.LOW)
        self.running = False

    def avvia(self):
        if self.pin:
            self.running = True
            Thread(target=self._blink_loop, daemon=True).start()

    def _blink_loop(self):
        """Lampeggio lento = tutto ok."""
        while self.running:
            if self.pin:
                GPIO.output(self.pin, GPIO.HIGH)
                time.sleep(0.1)
                GPIO.output(self.pin, GPIO.LOW)
                time.sleep(2)

    def errore(self):
        """Lampeggio veloce = errore."""
        if self.pin:
            for _ in range(10):
                GPIO.output(self.pin, GPIO.HIGH)
                time.sleep(0.1)
                GPIO.output(self.pin, GPIO.LOW)
                time.sleep(0.1)

    def termina(self):
        self.running = False
        if self.pin:
            GPIO.output(self.pin, GPIO.LOW)


# ============================================================
# SISTEMA PRINCIPALE
# ============================================================

class CitofonoVoIP:
    """Sistema principale Citofono-VoIP."""

    def __init__(self):
        self.running = False
        self.baresip = None
        self.portone = None
        self.suoneria = None
        self.dtmf_handler = None
        self.led = None
        self.chiamata_in_corso = Event()

    def _setup_gpio(self):
        """Inizializza GPIO."""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        logger.info("GPIO inizializzati")

    def _on_suoneria(self):
        """Callback quando suona il citofono."""
        if self.chiamata_in_corso.is_set():
            logger.warning("Chiamata già in corso, ignoro suoneria")
            return

        self.chiamata_in_corso.set()

        # Piccolo ritardo per stabilizzare
        time.sleep(RITARDO_POST_SUONERIA_SEC)

        # Effettua la chiamata
        self.baresip.chiama(NUMERO_DA_CHIAMARE)

        # Thread per gestire timeout
        Thread(target=self._timeout_chiamata, daemon=True).start()

    def _timeout_chiamata(self):
        """Gestisce il timeout della chiamata."""
        start = time.time()
        while time.time() - start < TIMEOUT_CHIAMATA_SEC:
            if not self.chiamata_in_corso.is_set():
                return
            if not self.baresip.chiamata_attiva.is_set():
                time.sleep(0.5)
            else:
                # Chiamata risposta, attendi che termini
                while self.baresip.chiamata_attiva.is_set():
                    time.sleep(0.5)
                break

        # Timeout o chiamata terminata
        if self.baresip.chiamata_attiva.is_set():
            logger.info("Timeout chiamata, riaggancio")
            self.baresip.riaggancia()

        self.chiamata_in_corso.clear()

    def avvia(self):
        """Avvia il sistema."""
        logger.info("=" * 60)
        logger.info("AVVIO SISTEMA CITOFONO-VOIP")
        logger.info("=" * 60)

        try:
            # Validazione configurazione
            if not SIP_PASSWORD:
                logger.error("SIP_PASSWORD non configurata! Impostala in config.env")
                return False

            # Setup GPIO
            self._setup_gpio()

            # Inizializza componenti
            self.portone = PortoneController(PIN_RELE_PORTONE)
            self.led = LEDStatus(PIN_LED_STATO)
            self.led.avvia()

            # Avvia Baresip
            self.baresip = BaresipController()
            if not self.baresip.avvia():
                logger.error("Impossibile avviare Baresip!")
                self.led.errore()
                return False

            # Avvia handler DTMF
            self.dtmf_handler = DTMFHandler(self.baresip, self.portone)
            self.dtmf_handler.avvia()

            # Avvia monitor suoneria
            self.suoneria = SuoneriaMonitor(PIN_SUONERIA, self._on_suoneria)
            self.suoneria.avvia()

            self.running = True

            logger.info("-" * 60)
            logger.info("SISTEMA PRONTO")
            logger.info("  Interno SIP: %s", SIP_USERNAME)
            logger.info("  Centralino: %s", SIP_DOMAIN)
            logger.info("  Chiama: %s", NUMERO_DA_CHIAMARE)
            logger.info("  Codice apertura: %s", DTMF_APRI_PORTONE)
            logger.info("-" * 60)

            return True

        except Exception as e:
            logger.error("Errore avvio sistema: %s", e)
            if self.led:
                self.led.errore()
            return False

    def loop(self):
        """Loop principale."""
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interruzione utente")
        finally:
            self.termina()

    def termina(self):
        """Termina il sistema."""
        logger.info("Arresto sistema...")
        self.running = False

        if self.dtmf_handler:
            self.dtmf_handler.termina()
        if self.baresip:
            self.baresip.termina()
        if self.led:
            self.led.termina()

        GPIO.cleanup()
        logger.info("Sistema terminato")


# ============================================================
# ENTRY POINT
# ============================================================

def signal_handler(sig, frame):
    """Gestisce segnali di terminazione."""
    logger.info("Ricevuto segnale %s", sig)
    sys.exit(0)


def main():
    # Registra handler per segnali
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Verifica permessi root (necessari per GPIO)
    if os.geteuid() != 0:
        print("ERRORE: Eseguire come root (sudo)")
        sys.exit(1)

    # Avvia sistema
    sistema = CitofonoVoIP()

    if sistema.avvia():
        sistema.loop()
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
