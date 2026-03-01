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
import re
from threading import Thread, Event, Lock
import logging

# ============================================================
# CONFIGURAZIONE
# ============================================================

def _load_config():
    """Carica la configurazione da /etc/citofono-voip/config.env se presente."""
    path = '/etc/citofono-voip/config.env'
    if os.path.isfile(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, _, value = line.partition('=')
                    os.environ[key.strip()] = value.strip()

_load_config()

def _env(key, default, cast=str):
    """Legge un valore dall'ambiente con fallback al default."""
    val = os.environ.get(key, default)
    return cast(val)

# GPIO Pins (BCM numbering)
PIN_SUONERIA = _env('PIN_SUONERIA', '17', int)
PIN_RELE_PORTONE = _env('PIN_RELE_PORTONE', '27', int)
PIN_LED_STATO = _env('PIN_LED_STATO', '22', int)

def _validate_gpio_pins():
    """Valida i PIN GPIO configurati."""
    pins = {
        'PIN_SUONERIA': PIN_SUONERIA,
        'PIN_RELE_PORTONE': PIN_RELE_PORTONE,
        'PIN_LED_STATO': PIN_LED_STATO,
    }
    for name, pin in pins.items():
        if not (2 <= pin <= 27):
            raise ValueError(f"{name}={pin} non valido. Usa GPIO 2-27")
    values = list(pins.values())
    if len(values) != len(set(values)):
        raise ValueError(f"Pin GPIO duplicati: {pins}")

_validate_gpio_pins()

# Configurazione SIP
SIP_USERNAME = _env('SIP_USERNAME', '2000')
SIP_PASSWORD = _env('SIP_PASSWORD', '')
SIP_DOMAIN = _env('SIP_DOMAIN', 'centralino.ponsacco.local')
SIP_PORT = _env('SIP_PORT', '5060', int)

# Numero da chiamare quando suona il citofono
NUMERO_DA_CHIAMARE = _env('NUMERO_DA_CHIAMARE', '6400')

# Codice DTMF per aprire il portone
DTMF_APRI_PORTONE = _env('DTMF_APRI_PORTONE', '91')

# Timing
DEBOUNCE_SUONERIA_MS = _env('DEBOUNCE_SUONERIA_MS', '300', int)
DURATA_APERTURA_SEC = _env('DURATA_APERTURA', '2', int)
TIMEOUT_CHIAMATA_SEC = _env('TIMEOUT_CHIAMATA', '60', int)
RITARDO_POST_SUONERIA_SEC = 0.5

# Audio - Verifica con 'aplay -l' e 'arecord -l'
AUDIO_PLAY_DEVICE = _env('AUDIO_PLAY_DEVICE', 'plughw:1,0')
AUDIO_REC_DEVICE = _env('AUDIO_REC_DEVICE', 'plughw:1,0')

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

    # Pattern per riconoscere DTMF nell'output di baresip (src/call.c):
    #   RFC 4733: "received in-band DTMF event: '5' (end=0)"
    #   SIP INFO: "call: received SIP INFO DTMF: '*' (duration=100)"
    _RE_DTMF = re.compile(r"received (?:in-band DTMF event|SIP INFO DTMF): '([0-9A-D*#])'")
    _RE_ANSI = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    _RE_CALL_END = re.compile(
        r'(?:call.*(?:closed|terminated|rejected|busy)|'
        r'BYE|'
        r'487 Request Terminated|'
        r'486 Busy)',
        re.IGNORECASE
    )
    _RE_IMPORTANT = re.compile(
        r'(?:error|warning|incoming call|outgoing|registered|DTMF|BYE|'
        r'busy|rejected|closed|terminated|failed)',
        re.IGNORECASE
    )
    _RE_REG_OK = re.compile(r'(?:registered successfully|200 OK.*register)', re.IGNORECASE)
    _RE_REG_FAIL = re.compile(r'(?:register.*failed|register.*timeout|403|401 Unauthorized)', re.IGNORECASE)

    def __init__(self):
        self.processo = None
        self.lock = Lock()
        self.chiamata_attiva = Event()
        self.running = False
        self._drain_thread = None
        self.on_dtmf = None  # callback(tono: str)
        self.on_incoming_call = None  # callback(numero: str)
        self.on_call_end = None  # callback()
        self._reg_fail_count = 0

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
            logger.info("Baresip avviato e connesso (PID: %d)", self.processo.pid)
            self.running = True
            return True
        else:
            logger.error("Baresip non si è avviato")
            return False

    def _drain_stdout(self):
        """Legge l'output di baresip, rileva eventi DTMF e previene blocchi sulla pipe."""
        try:
            while True:
                line = self.processo.stdout.readline()
                if not line:
                    break
                # Decodifica e rimuovi codici ANSI che baresip può inserire
                text = line.decode(errors='replace').rstrip()
                clean = self._RE_ANSI.sub('', text)
                if clean != text:
                    logger.debug("baresip (raw): %r", text)
                    text = clean
                if self._RE_IMPORTANT.search(text):
                    logger.info("baresip: %s", text)
                else:
                    logger.debug("baresip: %s", text)

                # Cerca toni DTMF ricevuti
                m = self._RE_DTMF.search(text)
                if m and self.on_dtmf:
                    tono = m.group(1)
                    logger.info("DTMF ricevuto da baresip: %s", tono)
                    self.on_dtmf(tono)
                    
                # Intercetta chiamate in ingresso
                if self.on_incoming_call and re.search(r'(?:Incoming call from|call: incoming call from)[:\s]+', text, re.IGNORECASE):
                    # Estrae il numero dal formato SIP URI
                    m_inc = re.search(r"sip:([^@>]+)", text)
                    numero = m_inc.group(1) if m_inc else "Sconosciuto"
                    Thread(target=self.on_incoming_call, args=(numero,), daemon=True).start()
                    
                # Rilevamento fine/rifiuto chiamata per riagganciare lo stato
                if self._RE_CALL_END.search(text):
                    self.chiamata_attiva.clear()
                    if self.on_call_end:
                        self.on_call_end()
                    logger.info("Chiamata terminata o rifiutata (rilevato da output baresip)")

                # Monitoraggio registrazione SIP
                if self._RE_REG_OK.search(text):
                    self._reg_fail_count = 0
                    logger.info("Registrazione SIP OK")
                elif self._RE_REG_FAIL.search(text):
                    self._reg_fail_count += 1
                    logger.warning("Registrazione SIP fallita (%d consecutive)", self._reg_fail_count)
                    if self._reg_fail_count >= 3:
                        logger.error("Registrazione SIP fallita 3 volte, riavvio baresip")
                        Thread(target=self._restart_baresip, daemon=True).start()

        except Exception:
            logger.debug("Errore drain stdout", exc_info=True)

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

    def rispondi(self):
        """Risponde alla chiamata."""
        logger.info("Risposta chiamata")
        try:
            self.processo.stdin.write(b"/accept\n")
            self.processo.stdin.flush()
            self.chiamata_attiva.set()
            return True
        except Exception as e:
            logger.error("Errore risposta: %s", e)
            return False

    def riaggancia(self):
        """Termina la chiamata."""
        logger.info("Termine chiamata")
        try:
            self.processo.stdin.write(b"/hangup\n")
            self.processo.stdin.flush()
            self.chiamata_attiva.clear()
            if self.on_call_end:
                self.on_call_end()
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

    def _restart_baresip(self):
        """Riavvia baresip dopo fallimenti di registrazione."""
        self._reg_fail_count = 0
        try:
            self.processo.stdin.write(b"/quit\n")
            self.processo.stdin.flush()
            self.processo.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            if self.processo:
                self.processo.terminate()
        time.sleep(2)
        self.avvia()

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
        logger.debug("GPIO%d trigger: stato=%s, timestamp=%.3f", self.pin, GPIO.input(self.pin), now)
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
            self.buffer = ""
            Thread(target=self._apri_e_riaggancia, daemon=True).start()

    def _apri_e_riaggancia(self):
        """Apre il portone e riaggancia la chiamata (eseguito in thread separato)."""
        self.portone.apri()
        time.sleep(2)
        logger.info("Portone aperto, riaggancio chiamata")
        self.baresip.riaggancia()

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
        self._call_lock = Lock()
        self._call_active = False
        self._chiamata_terminata = Event()

    def _on_call_end(self):
        """Callback thread-safe per fine chiamata."""
        with self._call_lock:
            self._call_active = False
        self._chiamata_terminata.set()

    def _setup_gpio(self):
        """Inizializza GPIO."""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        logger.info("GPIO inizializzati")

    def _on_suoneria(self):
        """Callback quando suona il citofono — dispatch su thread separato."""
        Thread(target=self._gestisci_suoneria, daemon=True).start()

    def _gestisci_suoneria(self):
        """Gestisce la suoneria fuori dal thread di interrupt GPIO."""
        with self._call_lock:
            if self._call_active:
                logger.warning("Chiamata già in corso, ignoro suoneria")
                return
            self._call_active = True
            self._chiamata_terminata.clear()

        # Piccolo ritardo per stabilizzare
        time.sleep(RITARDO_POST_SUONERIA_SEC)

        # Effettua la chiamata
        self.baresip.chiama(NUMERO_DA_CHIAMARE)

        # Thread per gestire timeout
        Thread(target=self._timeout_chiamata, daemon=True).start()

    def _on_chiamata_in_ingresso(self, numero):
        """Callback quando arriva una chiamata in ingresso."""
        logger.info("Chiamata in ingresso da %s", numero)

        with self._call_lock:
            if self._call_active:
                logger.warning("Chiamata già in corso, rifiuto")
                self.baresip.riaggancia()
                return
            self._call_active = True
            self._chiamata_terminata.clear()
        self.baresip.chiamata_attiva.set()   # evita race con _timeout_chiamata

        # Rispondi automaticamente dopo un breve ritardo
        time.sleep(0.5)
        self.baresip.rispondi()

        # Thread per gestire timeout
        Thread(target=self._timeout_chiamata, daemon=True).start()

    def _timeout_chiamata(self):
        """Attende la fine della chiamata o scade il timeout."""
        terminata = self._chiamata_terminata.wait(timeout=TIMEOUT_CHIAMATA_SEC)
        if not terminata:
            logger.info("Timeout chiamata, riaggancio")
            self.baresip.riaggancia()
        self._chiamata_terminata.clear()

    def _genera_config_baresip(self):
        """Genera i file di configurazione per Baresip."""
        baresip_dir = '/root/.baresip'
        accounts_path = os.path.join(baresip_dir, 'accounts')
        config_path = os.path.join(baresip_dir, 'config')

        # Crea la directory se non esiste
        if not os.path.isdir(baresip_dir):
            os.makedirs(baresip_dir)
            logger.info("Creata directory %s", baresip_dir)

        # Backup dei file esistenti
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        for path in (accounts_path, config_path):
            if os.path.isfile(path):
                backup = f"{path}.bak.{timestamp}"
                os.rename(path, backup)
                logger.info("Backup %s -> %s", path, backup)

        # Scrivi accounts
        accounts_line = (
            f"<sip:{SIP_USERNAME}@{SIP_DOMAIN}>"
            f";auth_pass={SIP_PASSWORD}"
            f";regint=300"
            f";answermode=manual\n"
        )
        with open(accounts_path, 'w') as f:
            f.write(accounts_line)
        logger.info("Scritto %s", accounts_path)

        # Scrivi config
        config_content = (
            f"module_path /usr/lib/baresip/modules\n"
            f"audio_player alsa,{AUDIO_PLAY_DEVICE}\n"
            f"audio_source alsa,{AUDIO_REC_DEVICE}\n"
            f"module alsa.so\n"
            f"module account.so\n"
            f"module menu.so\n"
            f"module contact.so\n"
            f"module stdio.so\n"
            f"module g711.so\n"
            f"module ctrl_tcp.so\n"
            f"ctrl_tcp_listen 0.0.0.0:4444\n"
        )
        with open(config_path, 'w') as f:
            f.write(config_content)
        logger.info("Scritto %s", config_path)

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

            # Genera configurazione Baresip
            self._genera_config_baresip()

            # Avvia Baresip
            self.baresip = BaresipController()
            if not self.baresip.avvia():
                logger.error("Impossibile avviare Baresip!")
                self.led.errore()
                return False

            # Avvia handler DTMF e collegalo all'output di baresip
            self.dtmf_handler = DTMFHandler(self.baresip, self.portone)
            self.dtmf_handler.avvia()
            self.baresip.on_dtmf = self.dtmf_handler.processa_dtmf
            
            # Collega l'evento di chiamata in ingresso
            self.baresip.on_incoming_call = self._on_chiamata_in_ingresso
            self.baresip.on_call_end = self._on_call_end

            # Avvia monitor suoneria
            self.suoneria = SuoneriaMonitor(PIN_SUONERIA, self._on_suoneria)
            self.suoneria.avvia()

            self.running = True
            self._start_time = time.time()

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

    def get_status(self):
        """Ritorna lo stato del sistema per debugging."""
        return {
            'running': self.running,
            'uptime_sec': int(time.time() - self._start_time) if hasattr(self, '_start_time') else 0,
            'call_active': self._call_active,
            'baresip_running': self.baresip.running if self.baresip else False,
            'baresip_pid': self.baresip.processo.pid if self.baresip and self.baresip.processo else None,
        }


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    # Verifica permessi root (necessari per GPIO)
    if os.geteuid() != 0:
        print("ERRORE: Eseguire come root (sudo)")
        sys.exit(1)

    sistema = CitofonoVoIP()

    def signal_handler(sig, frame):
        logger.info("Ricevuto segnale %s", sig)
        sistema.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if sistema.avvia():
        sistema.loop()
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
