import lightkurve as lk
import matplotlib.pyplot as plt
import json
import os

# test planets
targets = [
    {"name": "Kepler-10", "period": 0.837, "temp": 2130},
    {"name": "Kepler-8", "period": 3.522, "temp": 1680}
]

print("Fetching data from NASA using lightkurve...")

for target in targets:
    name = target["name"]
    print(f"Processing {name}")

    # search and download lightkurve data