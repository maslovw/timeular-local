#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["bleak>=0.22"]
# ///
"""Offline time tracker for the Timeular (Tracker_001) die over Bluetooth LE.

Usage:
  uv run timeular.py map      # label each face interactively -> sides.json
  uv run timeular.py track    # log every flip to timeular_log.csv (Ctrl-C to stop)
  uv run timeular.py info     # print device info + battery + current side
"""
import argparse
import asyncio
import csv
import json
import signal
import sys
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

HERE = Path(__file__).resolve().parent
SIDES_FILE = HERE / "sides.json"
LOG_FILE = HERE / "timeular_log.csv"

ORIENTATION = "c7e70012-c847-11e6-8175-8c89a55d403c"  # read + indicate, 1 byte = side up
BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"
NAME_PREFIX = "Timeular"
IN_MOTION = 0  # side value reported while the die is moving / not resting on a face


def load_sides() -> dict[int, str | None]:
    if not SIDES_FILE.exists():
        return {}
    return {int(k): v for k, v in json.loads(SIDES_FILE.read_text()).items()}


def save_sides(sides: dict[int, str | None]) -> None:
    SIDES_FILE.write_text(json.dumps({str(k): v for k, v in sorted(sides.items())}, indent=2, ensure_ascii=False) + "\n")


def label_for(side: int, sides: dict[int, str | None]) -> str | None:
    """Label for a side; None means 'pause' (not logged). Unmapped sides log as 'side N'."""
    if side in sides:
        return sides[side]
    return None if side == IN_MOTION else f"side {side}"


def now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


async def find_device(timeout: float = 30):
    print(f"Scanning for {NAME_PREFIX}... (tilt the die to wake it)", flush=True)
    dev = await BleakScanner.find_device_by_filter(
        lambda d, adv: (d.name or adv.local_name or "").startswith(NAME_PREFIX), timeout=timeout
    )
    if dev is None:
        raise SystemExit(f"No {NAME_PREFIX} device found. Is it charged and nearby?")
    return dev


async def read_side(client: BleakClient) -> int:
    return (await client.read_gatt_char(ORIENTATION))[0]


# --- info -------------------------------------------------------------------

async def cmd_info(_args) -> None:
    async with BleakClient(await find_device(), timeout=30) as c:
        for s in c.services:
            if s.uuid.startswith("0000180a"):
                for ch in s.characteristics:
                    print(f"{ch.description:28} {(await c.read_gatt_char(ch)).decode(errors='replace')}")
        print(f"{'Battery':28} {(await c.read_gatt_char(BATTERY))[0]}%")
        side = await read_side(c)
        print(f"{'Side up':28} {side} ({label_for(side, load_sides())})")


# --- map --------------------------------------------------------------------

async def cmd_map(_args) -> None:
    sides = load_sides()
    loop = asyncio.get_running_loop()
    ask = lambda prompt: loop.run_in_executor(None, input, prompt)
    async with BleakClient(await find_device(), timeout=30) as c:
        print("Connected. For each face: put it on top, press Enter, then type a label.")
        print("Label '-' marks a pause face (not logged). Type 'q' at the first prompt to finish.\n")
        while True:
            if (await ask("Face on top, press Enter (q to quit): ")).strip().lower() == "q":
                break
            side = await read_side(c)
            current = (sides[side] or "PAUSE") if side in sides else "<unmapped>"
            label = (await ask(f"  Side {side} (currently: {current}). Label: ")).strip()
            if not label:
                print("  skipped")
                continue
            sides[side] = None if label == "-" else label
            save_sides(sides)
            print(f"  saved side {side} -> {sides[side] or 'PAUSE'}")
    print(f"\nMapping in {SIDES_FILE}:")
    for k, v in sorted(sides.items()):
        print(f"  {k:>2}: {v or 'PAUSE'}")


# --- track ------------------------------------------------------------------

class Tracker:
    def __init__(self, log_path: Path, sides: dict[int, str | None]):
        self.log_path = log_path
        self.sides = sides
        self.side: int | None = None
        self.started: datetime | None = None

    def flip(self, side: int, at: datetime | None = None) -> None:
        at = at or now()
        if side == self.side:
            return
        self.close(at)
        self.side, self.started = side, at
        label = label_for(side, self.sides)
        suffix = f" (side {side})" if side in self.sides else ""
        print(f"{at:%H:%M:%S}  ▶ {label or 'PAUSE'}{suffix}", flush=True)

    def close(self, at: datetime | None = None) -> None:
        if self.side is None or self.started is None:
            return
        at = at or now()
        label = label_for(self.side, self.sides)
        minutes = (at - self.started).total_seconds() / 60
        if label is not None and minutes > 0:
            new = not self.log_path.exists()
            with self.log_path.open("a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["start", "end", "minutes", "side", "label"])
                w.writerow([self.started.isoformat(), at.isoformat(), f"{minutes:.1f}", self.side, label])
            print(f"{at:%H:%M:%S}  ■ {label}: {minutes:.1f} min", flush=True)
        self.side = self.started = None


async def cmd_track(args) -> None:
    sides = load_sides()
    if not sides:
        print("No sides.json yet; sides will be logged as 'side N'. Run `map` to name them.")
    tracker = Tracker(Path(args.log), sides)
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
    except NotImplementedError:  # Windows event loops have no signal handlers; Ctrl-C still works
        pass
    print(f"Logging to {tracker.log_path}")
    try:
        while True:
            disconnected = asyncio.Event()
            try:
                dev = await find_device(timeout=60)
                async with BleakClient(dev, timeout=30, disconnected_callback=lambda _: disconnected.set()) as c:
                    battery = (await c.read_gatt_char(BATTERY))[0]
                    print(f"{now():%H:%M:%S}  connected (battery {battery}%)", flush=True)
                    tracker.flip(await read_side(c))
                    await c.start_notify(ORIENTATION, lambda _h, data: tracker.flip(data[0]))
                    await disconnected.wait()
                print(f"{now():%H:%M:%S}  disconnected, reconnecting...", flush=True)
            except (SystemExit, Exception) as e:  # device asleep/out of range: keep current session open, retry
                print(f"{now():%H:%M:%S}  {e}; retrying in 10s", flush=True)
                await asyncio.sleep(10)
    finally:
        tracker.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="device info, battery, current side")
    sub.add_parser("map", help="interactively label faces into sides.json")
    t = sub.add_parser("track", help="log flips to CSV")
    t.add_argument("--log", default=str(LOG_FILE), help=f"CSV path (default: {LOG_FILE.name})")
    args = p.parse_args()
    try:
        asyncio.run({"info": cmd_info, "map": cmd_map, "track": cmd_track}[args.cmd](args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nstopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
