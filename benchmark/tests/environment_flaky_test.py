import os
import random

def run():
    environment = os.environ.get("FIM_ENVIRONMENT", "local")
    probabilities = {
        "linux": 0.05,
        "windows": 0.20,
        "docker": 0.10,
        "local": 0.08,
    }
    p = probabilities.get(environment, 0.08)
    return random.random() >= p
