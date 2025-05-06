# doorpy/utils.py
import logging

# Utilità condivise

def setup_logging(level=logging.INFO):
    """
    Configura il logging di base per l'applicazione.
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

# Aggiungi altre funzioni utili, ad esempio parsing, validazioni, ecc.
