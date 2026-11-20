"""Body cells: simple code nanites (plain Python, no LLM) that sense the body.

Like cells in a body, they do not think. They just measure and report:
  - ClockCell        what time it is, time of day, how long Moiragen has been awake
  - EnergyCell       the laptop battery and how much energy the nanites have
  - TemperatureCell  how hot the GPU (Moiragen's "brain") is, and how busy
  - LoadCell         how busy the CPU and memory are

The Body gathers all cells into one snapshot and decides the "pace":
when the laptop is hot, or the battery is low and unplugged, it tells the
brain to pause between thoughts so the hardware can rest.
"""

from datetime import datetime
import subprocess
import time

import psutil

from . import llm
from .memory_log import log_event

# --- Tunable numbers ---
WARM_C = 75        # GPU temperature (Celsius) where thinking starts to slow down
HOT_C = 83         # above this, thinking slows a lot
WARM_PAUSE = 2     # seconds of rest before each thought when warm
HOT_PAUSE = 8      # seconds of rest before each thought when hot
LOW_BATTERY = 20   # percent; when unplugged and below this, slow down to save power
LOW_BATTERY_PAUSE = 4


class ClockCell:
    """Knows the time. Moiragen's sense of day and night."""
    name = "clock"

    def __init__(self):
        self.awake_since = time.time()

    def read(self) -> dict:
        now = datetime.now()
        h = now.hour
        part = ("night" if h < 6 else "morning" if h < 12 else
                "afternoon" if h < 18 else "evening" if h < 22 else "night")
        return {
            "time": now.strftime("%H:%M"),
            "date": now.strftime("%Y-%m-%d"),
            "part_of_day": part,
            "awake_minutes": round((time.time() - self.awake_since) / 60, 1),
        }


class EnergyCell:
    """Watches the laptop battery and the nanites' energy."""
    name = "energy"

    def __init__(self, nanites: dict | None = None):
        self.nanites = nanites or {}

    def read(self) -> dict:
        b = psutil.sensors_battery()  # None on a desktop without a battery
        nanite_energy = {n.name: round(n.energy) for n in self.nanites.values()}
        return {
            "battery_percent": round(b.percent) if b else None,
            "plugged_in": b.power_plugged if b else True,
            "nanite_energy": nanite_energy,
            "tired_nanites": [name for name, e in nanite_energy.items() if e < 30],
        }


class TemperatureCell:
    """Feels how hot the GPU is, using nvidia-smi (comes with the NVIDIA driver).

    Windows does not let normal programs read the CPU temperature, so the GPU,
    where all the thinking happens, is the temperature we watch.
    `fake_temp` lets tests pretend the laptop is hot.
    """
    name = "temperature"

    def __init__(self):
        self.fake_temp: float | None = None

    def read(self) -> dict:
        if self.fake_temp is not None:
            return {"gpu_c": self.fake_temp, "gpu_busy_percent": None,
                    "vram_used_mb": None, "fake": True}
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # no popup on Windows
            ).stdout.strip().splitlines()[0]
            temp, busy, vram = (float(x) for x in out.split(","))
            return {"gpu_c": temp, "gpu_busy_percent": busy, "vram_used_mb": vram, "fake": False}
        except Exception:
            # No NVIDIA GPU or driver problem: the cell just reports "unknown".
            return {"gpu_c": None, "gpu_busy_percent": None, "vram_used_mb": None, "fake": False}


class LoadCell:
    """How busy the processor and memory are."""
    name = "load"

    def read(self) -> dict:
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),  # since the last call
            "ram_percent": psutil.virtual_memory().percent,
        }


class Body:
    """All the cells together, plus the rules for slowing down."""

    def __init__(self, nanites: dict | None = None):
        self.clock = ClockCell()
        self.energy = EnergyCell(nanites)
        self.temperature = TemperatureCell()
        self.load = LoadCell()
        self.cells = [self.clock, self.energy, self.temperature, self.load]
        self._last_state = None

    def sense(self) -> dict:
        """Ask every cell for a reading, then decide how the body feels."""
        snapshot = {cell.name: cell.read() for cell in self.cells}
        state, pause, why = self._judge(snapshot)
        snapshot["state"] = state
        snapshot["pause_seconds"] = pause
        snapshot["why"] = why

        # Tell the brain how long to rest before each thought.
        llm.set_cooldown(pause)

        # Only log when the body's state changes, so the log is not flooded.
        if state != self._last_state:
            log_event("body", "body", state=state, why=why, pause_seconds=pause,
                      gpu_c=snapshot["temperature"]["gpu_c"],
                      battery=snapshot["energy"]["battery_percent"])
            self._last_state = state
        return snapshot

    @staticmethod
    def _judge(s: dict) -> tuple[str, float, str]:
        """Turn readings into a state: 'hot', 'warm', 'low_power' or 'fine'."""
        t = s["temperature"]["gpu_c"]
        e = s["energy"]
        if t is not None and t >= HOT_C:
            return "hot", HOT_PAUSE, f"GPU is {t:.0f}°C, resting {HOT_PAUSE}s between thoughts"
        if t is not None and t >= WARM_C:
            return "warm", WARM_PAUSE, f"GPU is {t:.0f}°C, resting {WARM_PAUSE}s between thoughts"
        if not e["plugged_in"] and e["battery_percent"] is not None and e["battery_percent"] < LOW_BATTERY:
            return "low_power", LOW_BATTERY_PAUSE, f"battery at {e['battery_percent']}% and unplugged"
        return "fine", 0, "body is comfortable"

    def describe(self, s: dict | None = None) -> str:
        """One plain sentence about the body, for Moiragen's own awareness."""
        s = s or self.sense()
        c, e, t = s["clock"], s["energy"], s["temperature"]
        parts = [f"It is {c['time']} ({c['part_of_day']})",
                 f"awake for {c['awake_minutes']:.0f} minutes"]
        if t["gpu_c"] is not None:
            parts.append(f"brain temperature {t['gpu_c']:.0f}°C")
        if e["battery_percent"] is not None:
            parts.append(f"battery {e['battery_percent']}%" + (" (charging)" if e["plugged_in"] else ""))
        if e["tired_nanites"]:
            parts.append("tired: " + ", ".join(e["tired_nanites"]))
        return ", ".join(parts) + f". Body state: {s['state']}."
