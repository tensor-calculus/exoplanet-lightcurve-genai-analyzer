"""
Fetch exoplanet data from NASA Exoplanet Archive TAP API
and download real phase-folded transit light curves using lightkurve.
Falls back to synthetic light curves when real data is unavailable.
"""

import os
import json
import requests
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from io import StringIO
import csv
import warnings
warnings.filterwarnings("ignore")

try:
    import lightkurve as lk
    HAS_LIGHTKURVE = True
except ImportError:
    HAS_LIGHTKURVE = False
    print("WARNING: lightkurve not installed. Will use synthetic light curves only.")
    print("Install it with: pip install lightkurve")

# --- Configuration ---
NUM_PLANETS = 55  # fetch a few extra in case of issues
IMAGE_DIR = "data/images"
META_DIR = "data/metadata"

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)


def fetch_planets_from_nasa(limit=55):
    """Query NASA Exoplanet Archive for confirmed transiting planets with good parameters."""

    base_url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

    # Get transiting planets with known period, temperature, and radius
    # Also fetch transit midpoint (pl_tranmid) for phase folding
    query = f"""
    SELECT TOP {limit}
        pl_name, pl_orbper, pl_eqt, pl_rade, pl_bmasse,
        pl_orbsmax, hostname, disc_facility, pl_radj, st_rad, st_teff,
        pl_tranmid
    FROM pscomppars
    WHERE pl_orbper IS NOT NULL
        AND pl_eqt IS NOT NULL
        AND pl_rade IS NOT NULL
        AND pl_radj IS NOT NULL
        AND st_rad IS NOT NULL
        AND discoverymethod = 'Transit'
    ORDER BY pl_name
    """

    params = {
        "query": query,
        "format": "csv"
    }

    print("Querying NASA Exoplanet Archive...")
    response = requests.get(base_url, params=params, timeout=60)

    if response.status_code != 200:
        print(f"Error: HTTP {response.status_code}")
        print(response.text[:500])
        return []

    # Parse CSV response
    reader = csv.DictReader(StringIO(response.text))
    planets = []
    for row in reader:
        try:
            planet = {
                "name": row["pl_name"].strip(),
                "period": round(float(row["pl_orbper"]), 4),
                "temp": round(float(row["pl_eqt"]), 1),
                "radius_earth": round(float(row["pl_rade"]), 2),
                "radius_jupiter": round(float(row["pl_radj"]), 4),
                "star_radius_solar": round(float(row["st_rad"]), 3),
                "host_star": row["hostname"].strip(),
                "discovery_facility": row["disc_facility"].strip() if row.get("disc_facility") else "Unknown",
                "mass_earth": round(float(row["pl_bmasse"]), 2) if row.get("pl_bmasse") and row["pl_bmasse"].strip() else None,
                "semi_major_axis": round(float(row["pl_orbsmax"]), 4) if row.get("pl_orbsmax") and row["pl_orbsmax"].strip() else None,
                "star_temp": round(float(row["st_teff"]), 0) if row.get("st_teff") and row["st_teff"].strip() else None,
                "transit_midpoint": float(row["pl_tranmid"]) if row.get("pl_tranmid") and row["pl_tranmid"].strip() else None,
            }
            planets.append(planet)
        except (ValueError, KeyError) as e:
            print(f"  Skipping row due to parse error: {e}")
            continue

    print(f"Fetched {len(planets)} planets from NASA Exoplanet Archive.")
    return planets


def download_real_lightcurve(planet, save_path):
    """
    Download a real light curve using lightkurve, phase-fold it,
    and save as a transit plot image.
    
    Returns (success: bool, mission: str or None)
    """
    if not HAS_LIGHTKURVE:
        return False, None

    hostname = planet["host_star"]
    period = planet["period"]
    t0 = planet.get("transit_midpoint")

    # Try different pipelines: Kepler, K2, then TESS (SPOC)
    for author in ["Kepler", "K2", "SPOC"]:
        try:
            search = lk.search_lightcurve(hostname, author=author)

            if search is None or len(search) == 0:
                continue

            # Download the first available quarter/sector
            lc = search[0].download()
            if lc is None:
                continue

            # Clean the light curve
            lc = lc.remove_nans().remove_outliers(sigma=5).normalize()

            if len(lc.flux) < 50:
                continue

            # Phase-fold using known orbital period (and epoch if available)
            if t0 is not None:
                folded = lc.fold(period=period, epoch_time=t0)
            else:
                folded = lc.fold(period=period)

            phase = folded.phase.value
            flux = folded.flux.value

            # Normalize phase to -0.5 to 0.5 if values are in day units
            if np.nanmax(np.abs(phase)) > 1.0:
                phase = phase / period

            # Remove any remaining NaN/inf values
            mask = np.isfinite(phase) & np.isfinite(flux)
            phase = phase[mask]
            flux = flux[mask]

            if len(phase) < 50:
                continue

            # --- Plot ---
            fig, ax = plt.subplots(figsize=(4, 4))
            ax.scatter(phase, flux, s=1, color="#4A90D9", alpha=0.6, rasterized=True)
            ax.set_xlim(-0.5, 0.5)

            # Set y-limits to show the transit clearly
            median_flux = np.nanmedian(flux)
            std_flux = np.nanstd(flux)
            ax.set_ylim(median_flux - 5 * std_flux, median_flux + 3 * std_flux)

            ax.axis("off")
            fig.patch.set_facecolor("white")
            plt.savefig(save_path, bbox_inches="tight", pad_inches=0, dpi=100, facecolor="white")
            plt.close(fig)

            return True, author

        except Exception as e:
            continue

    return False, None


def generate_synthetic_lightcurve(planet, save_path):
    """
    Generate a synthetic folded transit light curve image (fallback).
    Uses planet radius ratio to determine transit depth,
    and orbital period to set transit duration.
    """

    # Transit parameters from real data
    rp_rstar = planet["radius_jupiter"] * 0.10045 / planet["star_radius_solar"]  # Rp/Rs (Jupiter radii -> Solar radii)
    transit_depth = rp_rstar ** 2  # (Rp/Rs)^2

    # Clamp depth to reasonable range
    transit_depth = min(transit_depth, 0.05)
    transit_depth = max(transit_depth, 0.0001)

    period = planet["period"]

    # Transit duration (approximate) as fraction of period
    # Typical: few hours for a few-day period planet
    duration_fraction = min(0.08, max(0.01, 0.03 * (period ** -0.3)))

    # Generate phase-folded data
    np.random.seed(hash(planet["name"]) % (2**31))
    n_points = 800

    # Phase from -0.5 to 0.5
    phase = np.random.uniform(-0.5, 0.5, n_points)
    phase = np.sort(phase)

    # Create transit signal
    flux = np.ones(n_points)

    # Ingress/egress width
    ingress_width = duration_fraction * 0.15

    for i, p in enumerate(phase):
        abs_p = abs(p)
        half_dur = duration_fraction / 2

        if abs_p < half_dur - ingress_width:
            # Full transit
            flux[i] = 1.0 - transit_depth
        elif abs_p < half_dur:
            # Ingress/egress (linear ramp)
            frac = (half_dur - abs_p) / ingress_width
            flux[i] = 1.0 - transit_depth * frac

    # Add realistic noise (scales with transit depth)
    noise_level = max(transit_depth * 0.3, 0.0005)
    noise = np.random.normal(0, noise_level, n_points)
    flux += noise

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.scatter(phase, flux, s=1, color="#4A90D9", alpha=0.6, rasterized=True)
    ax.set_xlim(-0.5, 0.5)

    y_margin = max(transit_depth * 2, 0.005)
    ax.set_ylim(1.0 - transit_depth - y_margin, 1.0 + y_margin)

    ax.axis("off")
    fig.patch.set_facecolor("white")

    plt.savefig(save_path, bbox_inches="tight", pad_inches=0, dpi=100, facecolor="white")
    plt.close(fig)


def classify_planet(planet):
    """Classify planet type based on radius."""
    r = planet["radius_earth"]
    if r < 1.25:
        return "Terrestrial (Earth-like)"
    elif r < 2.0:
        return "Super-Earth"
    elif r < 4.0:
        return "Sub-Neptune"
    elif r < 10.0:
        return "Neptune-like"
    else:
        return "Gas Giant (Jupiter-like)"


def main():
    print("=" * 60)
    print("  Exoplanet Data Fetcher & Light Curve Downloader")
    print("=" * 60)

    # Step 1: Fetch real planet data from NASA
    planets = fetch_planets_from_nasa(limit=NUM_PLANETS)

    if len(planets) == 0:
        print("ERROR: No planets fetched. Check internet connection.")
        return

    # Step 2: Download/generate light curves and save metadata
    success_count = 0
    real_count = 0
    synthetic_count = 0

    for i, planet in enumerate(planets):
        name = planet["name"]
        safe_name = name.replace(" ", "_").replace("/", "_")

        img_path = os.path.join(IMAGE_DIR, f"{safe_name}.png")
        meta_path = os.path.join(META_DIR, f"{safe_name}.json")

        try:
            # Add classification
            planet["type"] = classify_planet(planet)

            # Try downloading real light curve first
            is_real, mission = download_real_lightcurve(planet, img_path)

            if is_real:
                lc_source = f"Real ({mission})"
                real_count += 1
                source_tag = f"✓ REAL [{mission}]"
            else:
                # Fall back to synthetic
                generate_synthetic_lightcurve(planet, img_path)
                lc_source = "Synthetic"
                synthetic_count += 1
                source_tag = "~ SYNTHETIC"

            # Build metadata (ChromaDB requires string values)
            metadata = {
                "name": planet["name"],
                "period": planet["period"],
                "temp": planet["temp"],
                "radius_earth": planet["radius_earth"],
                "type": planet["type"],
                "host_star": planet["host_star"],
                "discovery_facility": planet["discovery_facility"],
                "lightcurve_source": lc_source,
            }

            # Add optional fields
            if planet.get("mass_earth") is not None:
                metadata["mass_earth"] = planet["mass_earth"]
            if planet.get("star_temp") is not None:
                metadata["star_temp"] = planet["star_temp"]

            # Save full metadata JSON
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2)

            success_count += 1
            print(f"  [{success_count:3d}/{len(planets)}] {name} — period={planet['period']:.2f}d, "
                  f"temp={planet['temp']:.0f}K, type={planet['type']} {source_tag}")

        except Exception as e:
            print(f"  SKIP {name}: {e}")
            continue

    print(f"\nDone! Generated {success_count} planets.")
    print(f"  Real light curves:      {real_count}")
    print(f"  Synthetic light curves:  {synthetic_count}")
    print(f"  Images:   {IMAGE_DIR}/")
    print(f"  Metadata: {META_DIR}/")


if __name__ == "__main__":
    main()