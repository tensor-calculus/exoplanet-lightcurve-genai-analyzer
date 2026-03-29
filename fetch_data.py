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
    search_resut = lk.search_lightcurve(name, author="Kepler", quarter=1)
    lc = search_resut.download()

    # flatten and fold lightkurve
    flat_lc = lc.flatten(window_length=401)
    folded_lc = flat_lc.fold(period=target["period"])

    fig, ax = plt.subplots(figsize=(4,4))
    folded_lc.scatter(ax=ax, s=1)
    plt.axis("off")
    img_path = f"data/images/{name}.png"
    plt.savefig(img_path, bbox_inches="tight", pad_inches=0)
    plt.close()

    # save metadata
    meta_path = f"data/metadata/{name}.json"
    with open(meta_path, "w") as f:
        json.dump(target, f)

    print("Data fetching complete!")
    