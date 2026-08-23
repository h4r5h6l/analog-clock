"""Hardware statistics polling: CPU, RAM, GPU, VRAM, and battery.

GPU stats come from GPUtil when installed, falling back to parsing
``nvidia-smi`` output; battery prefers psutil's sensors with the proven
sysfs readers as a fallback chain.
"""

import shutil
import subprocess
from pathlib import Path

import psutil

try:
    import GPUtil
    HAS_GPU_SUPPORT = True
except ImportError:
    HAS_GPU_SUPPORT = False


class HardwareMonitor:
    """Samples system stats; call poll() on a timer (widget uses 2 s)."""

    def __init__(self):
        self.cpu_percent = 0
        self.ram_percent = 0
        self.gpu_percent = 0
        self.gpu_vram_percent = 0
        self.gpu_available = False
        # Cached display label so painting never touches sensors directly.
        self.battery_label = "--%"

    def poll(self):
        """Update CPU, RAM, GPU, VRAM usage percentages and battery label."""
        try:
            self.cpu_percent = psutil.cpu_percent(interval=0.1)
        except Exception:
            self.cpu_percent = 0

        try:
            self.ram_percent = psutil.virtual_memory().percent
        except Exception:
            self.ram_percent = 0

        self._poll_gpu()
        self.battery_label = self.battery_text()

    def _poll_gpu(self):
        """GPUtil first, then the nvidia-smi subprocess fallback."""
        self.gpu_available = False
        if HAS_GPU_SUPPORT:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    # GPUtil provides load as a float 0..1
                    self.gpu_percent = (gpu.load or 0.0) * 100
                    # memoryUsed and memoryTotal may be provided (MB)
                    total = getattr(gpu, 'memoryTotal', 0) or 0
                    used = getattr(gpu, 'memoryUsed', 0) or 0
                    self.gpu_vram_percent = (used / total) * 100 if total > 0 else 0.0
                    self.gpu_available = True
            except Exception:
                self.gpu_available = False

        # Fallback: try nvidia-smi if GPUtil is unavailable or didn't return data
        if not self.gpu_available:
            try:
                if shutil.which('nvidia-smi'):
                    cmd = [
                        'nvidia-smi',
                        '--query-gpu=utilization.gpu,memory.total,memory.used',
                        '--format=csv,noheader,nounits',
                    ]
                    out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
                    first_line = out.strip().splitlines()[0]
                    parts = [p.strip() for p in first_line.split(',')]
                    if len(parts) >= 3:
                        util = 0.0 if parts[0] in ('N/A', '') else float(parts[0])
                        mem_total = 0.0 if parts[1] in ('N/A', '') else float(parts[1])
                        mem_used = 0.0 if parts[2] in ('N/A', '') else float(parts[2])
                        self.gpu_percent = util
                        self.gpu_vram_percent = (mem_used / mem_total) * 100 if mem_total > 0 else 0.0
                        self.gpu_available = True
            except Exception:
                # any errors mean GPU info is not available via this fallback
                self.gpu_available = False

    # ---- Battery -------------------------------------------------------------

    @staticmethod
    def _psutil_battery():
        try:
            return psutil.sensors_battery()
        except Exception:
            return None

    def battery_percent(self):
        batt = self._psutil_battery()
        if batt is not None:
            return max(0, min(100, int(round(batt.percent))))

        power_supply_path = Path("/sys/class/power_supply")
        if not power_supply_path.exists():
            return None

        for battery_path in sorted(power_supply_path.glob("BAT*")):
            capacity_path = battery_path / "capacity"
            if not capacity_path.exists():
                continue

            try:
                return max(0, min(100, int(capacity_path.read_text().strip())))
            except (OSError, ValueError):
                continue

        return None

    def battery_power_state(self):
        """Return 'AC' or 'BAT', or None when no battery is present."""
        batt = self._psutil_battery()
        if batt is not None:
            return "AC" if batt.power_plugged else "BAT"

        power_supply_path = Path("/sys/class/power_supply")
        if not power_supply_path.exists():
            return None

        for battery_path in sorted(power_supply_path.glob("BAT*")):
            status_path = battery_path / "status"
            if not status_path.exists():
                continue

            try:
                status = status_path.read_text().strip().lower()
            except OSError:
                continue

            if status == "discharging":
                return "BAT"
            if status in ("charging", "full", "not charging"):
                return "AC"

        return None

    def battery_text(self):
        """Rendered battery label, e.g. '76% AC' or '--%' when unknown."""
        percent = self.battery_percent()
        power_state = self.battery_power_state()
        text = "--%" if percent is None else f"{percent}%"
        if power_state is not None:
            text = f"{text} {power_state}"
        return text

    # ---- Snapshot for rendering ------------------------------------------------

    def stats_snapshot(self):
        """Dict of everything draw_hardware_specs renders for one frame."""
        return {
            "cpu_percent": self.cpu_percent,
            "ram_percent": self.ram_percent,
            "gpu_percent": self.gpu_percent,
            "gpu_vram_percent": self.gpu_vram_percent,
            "gpu_available": self.gpu_available,
            "battery_text": self.battery_label,
        }
