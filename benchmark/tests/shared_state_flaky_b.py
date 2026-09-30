import random

def run():
    # Same synthetic failure signature as shared_state_flaky_a.
    return random.random() > 0.25
