# doorpy/config.py
import yaml
import os

def load_config():
    path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(path) as f:
        return yaml.safe_load(f)
