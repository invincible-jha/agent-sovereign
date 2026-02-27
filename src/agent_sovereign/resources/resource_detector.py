"""Resource-aware execution detector.

Detects available hardware resources (CPU cores, RAM, GPU) and produces
a :class:`ResourceProfile` that can be used to auto-select appropriate
model sizes and batch sizes for on-device inference.

Detection is done via standard-library modules only (``os``, ``shutil``,
``platform``) so there are no optional dependencies.
"""
from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ModelSizeRecommendation(str, Enum):
    """Recommended model size tier based on available resources."""

    NANO = "nano"        # <1 GB RAM — tiny quantised models only
    SMALL = "small"      # 1-4 GB RAM
    MEDIUM = "medium"    # 4-16 GB RAM
    LARGE = "large"      # 16-64 GB RAM
    XLARGE = "xlarge"    # 64+ GB RAM or GPU available


class BatchSizeRecommendation(str, Enum):
    """Recommended inference batch size tier."""

    SINGLE = "single"    # batch_size=1
    SMALL = "small"      # batch_size=2-4
    MEDIUM = "medium"    # batch_size=4-8
    LARGE = "large"      # batch_size=8-32


# ---------------------------------------------------------------------------
# Resource profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceProfile:
    """Snapshot of the hardware resources available at detection time.

    Attributes
    ----------
    cpu_cores_logical:
        Total number of logical CPU cores (including hyper-threading).
    cpu_cores_physical:
        Physical CPU cores, or None if not detectable.
    ram_total_mb:
        Total installed RAM in megabytes.
    ram_available_mb:
        Currently available (free + buffers) RAM in megabytes.
    has_gpu:
        True when a GPU is detected via standard tools.
    gpu_name:
        Name of the detected GPU, or None.
    gpu_vram_mb:
        Estimated GPU VRAM in MB, or None if not detected.
    os_name:
        Operating system name (e.g. "Linux", "Windows", "Darwin").
    architecture:
        CPU architecture string (e.g. "x86_64", "arm64").
    model_recommendation:
        Auto-selected :class:`ModelSizeRecommendation`.
    batch_recommendation:
        Auto-selected :class:`BatchSizeRecommendation`.
    extra:
        Additional key/value metadata captured during detection.
    """

    cpu_cores_logical: int
    cpu_cores_physical: int | None
    ram_total_mb: int
    ram_available_mb: int
    has_gpu: bool
    gpu_name: str | None
    gpu_vram_mb: int | None
    os_name: str
    architecture: str
    model_recommendation: ModelSizeRecommendation
    batch_recommendation: BatchSizeRecommendation
    extra: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class ResourceDetector:
    """Detect hardware resources and recommend model/batch sizes.

    The detector uses only the Python standard library, so it works in
    any deployment environment without optional dependencies.

    Example
    -------
    ::

        detector = ResourceDetector()
        profile = detector.detect()
        print(profile.model_recommendation)
        print(profile.batch_recommendation)
    """

    def detect(self) -> ResourceProfile:
        """Perform hardware detection and return a :class:`ResourceProfile`.

        Returns
        -------
        ResourceProfile
            A frozen snapshot of detected hardware and recommendations.
        """
        cpu_logical = self._detect_cpu_logical()
        cpu_physical = self._detect_cpu_physical()
        ram_total, ram_available = self._detect_ram()
        has_gpu, gpu_name, gpu_vram = self._detect_gpu()
        os_name = platform.system()
        architecture = platform.machine()

        model_rec = self._recommend_model_size(ram_total, has_gpu, gpu_vram)
        batch_rec = self._recommend_batch_size(cpu_logical, ram_available, has_gpu)

        return ResourceProfile(
            cpu_cores_logical=cpu_logical,
            cpu_cores_physical=cpu_physical,
            ram_total_mb=ram_total,
            ram_available_mb=ram_available,
            has_gpu=has_gpu,
            gpu_name=gpu_name,
            gpu_vram_mb=gpu_vram,
            os_name=os_name,
            architecture=architecture,
            model_recommendation=model_rec,
            batch_recommendation=batch_rec,
        )

    # ------------------------------------------------------------------
    # Recommendation helpers (public so they can be called directly)
    # ------------------------------------------------------------------

    @staticmethod
    def recommend_model_size(
        ram_total_mb: int,
        has_gpu: bool = False,
        gpu_vram_mb: int | None = None,
    ) -> ModelSizeRecommendation:
        """Select a model size tier based on resource constraints.

        Parameters
        ----------
        ram_total_mb:
            Total RAM in megabytes.
        has_gpu:
            Whether a GPU is available.
        gpu_vram_mb:
            GPU VRAM in MB, or None.

        Returns
        -------
        ModelSizeRecommendation
            The recommended model size tier.
        """
        return ResourceDetector._recommend_model_size(ram_total_mb, has_gpu, gpu_vram_mb)

    @staticmethod
    def recommend_batch_size(
        cpu_cores: int,
        ram_available_mb: int,
        has_gpu: bool = False,
    ) -> BatchSizeRecommendation:
        """Select a batch size tier based on available resources.

        Parameters
        ----------
        cpu_cores:
            Number of logical CPU cores.
        ram_available_mb:
            Available RAM in megabytes.
        has_gpu:
            Whether a GPU is available.

        Returns
        -------
        BatchSizeRecommendation
            The recommended batch size tier.
        """
        return ResourceDetector._recommend_batch_size(cpu_cores, ram_available_mb, has_gpu)

    # ------------------------------------------------------------------
    # Private detection methods
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_cpu_logical() -> int:
        """Return the number of logical CPU cores."""
        count = os.cpu_count()
        return count if count is not None else 1

    @staticmethod
    def _detect_cpu_physical() -> int | None:
        """Attempt to detect physical CPU core count.

        Falls back to None on platforms where this is not available without
        third-party libraries.
        """
        try:
            # On Linux, parse /proc/cpuinfo
            if platform.system() == "Linux":
                seen_ids: set[str] = set()
                with open("/proc/cpuinfo", "r", encoding="utf-8") as fh:
                    for line in fh:
                        if line.startswith("core id"):
                            seen_ids.add(line.split(":")[1].strip())
                if seen_ids:
                    return len(seen_ids)
        except OSError:
            pass
        return None

    @staticmethod
    def _detect_ram() -> tuple[int, int]:
        """Return (total_mb, available_mb) RAM.

        On Linux reads ``/proc/meminfo``; on other platforms falls back to
        a heuristic using ``shutil.disk_usage`` as a proxy (not RAM).
        Returns (0, 0) when detection is not possible.
        """
        try:
            if platform.system() == "Linux":
                return ResourceDetector._read_proc_meminfo()
            # Windows / macOS — attempt ctypes approach without dependencies
            return ResourceDetector._detect_ram_generic()
        except Exception:
            return 0, 0

    @staticmethod
    def _read_proc_meminfo() -> tuple[int, int]:
        """Parse /proc/meminfo for MemTotal and MemAvailable."""
        total_kb = 0
        available_kb = 0
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
        return total_kb // 1024, available_kb // 1024

    @staticmethod
    def _detect_ram_generic() -> tuple[int, int]:
        """Generic RAM detection via ctypes on Windows or sysctl on macOS."""
        system = platform.system()
        if system == "Windows":
            try:
                import ctypes

                class _MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                mem_status = _MEMORYSTATUSEX()
                mem_status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_status))  # type: ignore[attr-defined]
                total_mb = mem_status.ullTotalPhys // (1024 * 1024)
                available_mb = mem_status.ullAvailPhys // (1024 * 1024)
                return int(total_mb), int(available_mb)
            except Exception:
                pass
        if system == "Darwin":
            try:
                import subprocess

                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    total_bytes = int(result.stdout.strip())
                    total_mb = total_bytes // (1024 * 1024)
                    # Available not trivially available on macOS; approximate
                    return total_mb, total_mb // 2
            except Exception:
                pass
        return 0, 0

    @staticmethod
    def _detect_gpu() -> tuple[bool, str | None, int | None]:
        """Detect GPU availability via nvidia-smi or standard paths.

        Returns
        -------
        tuple[bool, str | None, int | None]
            (has_gpu, gpu_name, gpu_vram_mb)
        """
        # Try nvidia-smi
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi is not None:
            try:
                import subprocess

                result = subprocess.run(
                    [
                        nvidia_smi,
                        "--query-gpu=name,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    line = result.stdout.strip().splitlines()[0]
                    parts = [p.strip() for p in line.split(",")]
                    gpu_name = parts[0] if parts else None
                    gpu_vram_mb = int(parts[1]) if len(parts) > 1 else None
                    return True, gpu_name, gpu_vram_mb
            except Exception:
                pass

        # Check for ROCm (AMD)
        if shutil.which("rocm-smi") is not None:
            return True, "AMD GPU (ROCm)", None

        # Check common GPU device paths on Linux
        if platform.system() == "Linux":
            import glob

            if glob.glob("/dev/nvidia*") or glob.glob("/dev/dri/card*"):
                return True, "GPU detected (device node)", None

        return False, None, None

    # ------------------------------------------------------------------
    # Private recommendation methods
    # ------------------------------------------------------------------

    @staticmethod
    def _recommend_model_size(
        ram_total_mb: int,
        has_gpu: bool,
        gpu_vram_mb: int | None,
    ) -> ModelSizeRecommendation:
        """Map resource figures to a model size recommendation."""
        # GPU with large VRAM → xlarge
        if has_gpu and gpu_vram_mb is not None and gpu_vram_mb >= 16_000:
            return ModelSizeRecommendation.XLARGE
        if has_gpu:
            return ModelSizeRecommendation.LARGE

        if ram_total_mb >= 64_000:
            return ModelSizeRecommendation.XLARGE
        if ram_total_mb >= 16_000:
            return ModelSizeRecommendation.LARGE
        if ram_total_mb >= 4_000:
            return ModelSizeRecommendation.MEDIUM
        if ram_total_mb >= 1_000:
            return ModelSizeRecommendation.SMALL
        return ModelSizeRecommendation.NANO

    @staticmethod
    def _recommend_batch_size(
        cpu_cores: int,
        ram_available_mb: int,
        has_gpu: bool,
    ) -> BatchSizeRecommendation:
        """Map resource figures to a batch size recommendation."""
        if has_gpu:
            return BatchSizeRecommendation.LARGE
        if cpu_cores >= 8 and ram_available_mb >= 8_000:
            return BatchSizeRecommendation.MEDIUM
        if cpu_cores >= 4 and ram_available_mb >= 2_000:
            return BatchSizeRecommendation.SMALL
        return BatchSizeRecommendation.SINGLE


__all__ = [
    "BatchSizeRecommendation",
    "ModelSizeRecommendation",
    "ResourceDetector",
    "ResourceProfile",
]
