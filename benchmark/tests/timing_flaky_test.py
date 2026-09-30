import random
import time

def run():
    delay = random.uniform(0.001, 0.010)
    time.sleep(delay)
    return delay < 0.007
