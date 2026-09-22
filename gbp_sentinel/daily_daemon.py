"""Daily automated watchdog daemon for GBP Sentinel."""

import asyncio
import argparse
import sys
import datetime
from pathlib import Path

from . import autopilot, lsf_poster, db

WATCHDOG_NICHES = [
    ("dakdekker", "Roofer"),
    ("loodgieter", "Plumber"),
    ("elektricien", "Electrician"),
    ("airco", "Air Conditioning"),
    ("verhuisbedrijf", "Moving Company"),
    ("gevelreiniging", "Facade Cleaning"),
    ("autoinkoop", "Auto Purchase"),
    ("schoorsteenveger", "Chimney Sweep"),
    ("schilder", "Painter"),
    ("stukadoor", "Plasterer"),
    ("kozijnen", "Window Frames")
]


async def run_daily_sweep(target_niche: str = None, auto_post_forum: bool = False):
    """Run an automated sweep across targeted trade niches."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"==================================================================")
    print(f"GBP SENTINEL DAILY WATCHDOG: SWEEP STARTED AT {now}")
    print(f"==================================================================")

    niches_to_run = WATCHDOG_NICHES
    if target_niche:
        niches_to_run = [item for item in WATCHDOG_NICHES if item[0] == target_niche]
        if not niches_to_run:
            niches_to_run = [(target_niche, target_niche.capitalize())]

    print(f"Aantal te scannen branches vandaag: {len(niches_to_run)}")

    for niche, display_name in niches_to_run:
        print(f"\n>>> WATCHDOG RUN: {display_name} ({niche}) <<<")
        try:
            await autopilot.run_autopilot_pipeline(niche, display_name)
        except Exception as e:
            print(f"Fout tijdens watchdog run voor '{niche}': {e}")

    print("\n==================================================================")
    print("DAGELIJKSE SWEEP VOLTOOID")
    print("Mogelijke overtredingen zijn verzameld; controleer dossiers en Google Case ID's voor vervolgactie.")
    print("==================================================================")


def main():
    parser = argparse.ArgumentParser(description="GBP Sentinel Daily Watchdog Daemon")
    parser.add_argument("--niche", help="Optional single niche to sweep (defaults to full rotation)")
    parser.add_argument("--post-forum", action="store_true", help="Auto-post escalation to Local Search Forum if logged in")
    args = parser.parse_args()

    asyncio.run(run_daily_sweep(target_niche=args.niche, auto_post_forum=args.post_forum))


if __name__ == "__main__":
    main()
