# README.md

## Funzionalità principali
- Interfaccia GPIO per rilevare squillo dal citofono
- Registrazione SIP e chiamata all'interno VoIP configurato
- Bridge audio tra citofono e chiamata SIP usando PJSIP
- Gestione DTMF: pressione di `unlock_code` apre la porta

## Hardware Audio

Per gestire l’audio tra il citofono analogico e il sistema VoIP è necessario un'interfaccia audio compatibile con Raspberry Pi.

Il sistema ora supporta **rilevazione automatica** del primo dispositivo ALSA disponibile se `audio_device_index` è impostato a `null` nel config:

- Se non sono presenti schede audio il servizio si interrompe con errore e log chiaro.
- Per specificare manualmente usa `audio_device_index: [capture, playback]`.

Per verificare i dispositivi:
1. `arecord -l`
2. `aplay -l`

## Testing e CI

Il progetto include una suite di test automatizzati con `pytest` e configura GitHub Actions per:

- Linting (flake8, black)
- Esecuzione test
- Build del pacchetto

Consulta il file `.github/workflows/ci.yml` per i dettagli sulla pipeline.

## Setup
1. Modifica `config/config.yaml` con credenziali SIP, pin GPIO e indici audio.
2. Installa dipendenze:
   ```bash
   pip install .
