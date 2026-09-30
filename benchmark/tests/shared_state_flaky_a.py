import random

def run():
    # Two tests intentionally share the same synthetic external resource.
    # This creates a controlled systemic-flakiness experiment.
    return random.random() > 0.25
