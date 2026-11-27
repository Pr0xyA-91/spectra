#!/usr/bin/env python3
"""SPECTRA HMI host hardware/GPU probing and managed local Ollama runtime lifecycle."""

import os
import sys
import re
import stat
import time
import glob
import json
import shutil
import platform
import threading
import subprocess
import urllib.request
from typing import Dict, List, Tuple, Optional, Any


class HmiOllamaMixin:
    """Host CPU/RAM/GPU diagnostics and local Ollama engine download, pull, and control."""

    @classmethod
    def probe_host_hardware(
        cls,
        override_ram_mb: Optional[int] = None,
        override_avx2: Optional[bool] = None,
        override_gpu: Optional[Dict[str, Any]] = None,
        override_installed_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically probe host hardware (CPU, RAM, GPU, SIMD, Disk) and compute
        the optimal offline AI model recommendation and system capability profile.
        Zero hardcoded machine assumptions.
        """
        # 1. CPU Info
        cpu_model = "Generic CPU"
        simd_flags = []
        try:
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if any(line.startswith(k) for k in ["model name", "Hardware", "Processor"]):
                            cpu_model = line.split(":", 1)[1].strip()
                            break
                    f.seek(0)
                    for line in f:
                        if line.startswith("flags") or line.startswith("Features"):
                            raw_flags = line.split(":", 1)[1].strip().split()
                            wanted = {"avx512f", "avx2", "fma", "avx", "sse4_2", "neon", "asimd"}
                            simd_flags = [fl for fl in raw_flags if fl in wanted]
                            break
        except Exception:
            pass

        if cpu_model == "Generic CPU":
            cpu_model = platform.processor() or platform.machine() or "Generic CPU"

        # Windows CPU / SIMD detection via ctypes and environment
        if os.name == "nt":
            try:
                import ctypes
                # PF_AVX_INSTRUCTIONS_AVAILABLE = 39, PF_AVX2_INSTRUCTIONS_AVAILABLE = 40
                if ctypes.windll.kernel32.IsProcessorFeaturePresent(39):
                    simd_flags.append("avx")
                if ctypes.windll.kernel32.IsProcessorFeaturePresent(40):
                    simd_flags.append("avx2")
            except Exception:
                pass
            if cpu_model == "Generic CPU":
                proc_id = os.environ.get("PROCESSOR_IDENTIFIER")
                if proc_id:
                    cpu_model = proc_id

        logical_cores = os.cpu_count() or 2
        has_avx2 = bool("avx2" in simd_flags or "neon" in simd_flags or "asimd" in simd_flags)
        if override_avx2 is not None:
            has_avx2 = override_avx2

        # 2. Memory Info
        ram_total_mb = 8192
        ram_available_mb = 4096
        try:
            if os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            ram_total_mb = int(line.split(":")[1].split()[0]) // 1024
                        elif line.startswith("MemAvailable:"):
                            ram_available_mb = int(line.split(":")[1].split()[0]) // 1024
        except Exception:
            pass

        # Windows RAM detection via GlobalMemoryStatusEx
        if os.name == "nt":
            try:
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                m_stat = MEMORYSTATUSEX()
                m_stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m_stat)):
                    ram_total_mb = int(m_stat.ullTotalPhys // (1024 * 1024))
                    ram_available_mb = int(m_stat.ullAvailPhys // (1024 * 1024))
            except Exception:
                pass

        if override_ram_mb is not None:
            ram_available_mb = override_ram_mb
            ram_total_mb = max(ram_total_mb, override_ram_mb + 2048)

        # 3. GPU / Accelerator Info
        has_discrete_gpu = False
        gpu_vendor = "none"
        gpu_name = "Integrated / CPU"
        vram_total_mb = 0
        vram_free_mb = 0
        create_no_window = 0x08000000 if os.name == "nt" else 0

        # NVIDIA probe via nvidia-smi (Linux/Windows)
        nvsmi = shutil.which("nvidia-smi")
        if not nvsmi and os.name == "nt":
            for cand in [r"C:\Windows\System32\nvidia-smi.exe", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"]:
                if os.path.isfile(cand):
                    nvsmi = cand
                    break

        if nvsmi:
            try:
                cmd_kwargs: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": 1.5}
                if os.name == "nt":
                    cmd_kwargs["creationflags"] = create_no_window
                p = subprocess.run(
                    [nvsmi, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                    **cmd_kwargs
                )
                if p.returncode == 0 and p.stdout.strip():
                    parts = p.stdout.strip().splitlines()[0].split(",")
                    if len(parts) >= 3:
                        gpu_vendor = "nvidia"
                        gpu_name = parts[0].strip()
                        vram_total_mb = int(parts[1].strip())
                        vram_free_mb = int(parts[2].strip())
                        has_discrete_gpu = True
            except Exception:
                pass

        # AMD discrete GPU probe via DRM sysfs (Linux)
        if not has_discrete_gpu:
            for p in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
                try:
                    with open(p, "r", encoding="utf-8") as vf:
                        v = int(vf.read().strip()) // (1024 * 1024)
                    if v >= 2048:
                        gpu_vendor = "amd"
                        vram_total_mb = v
                        has_discrete_gpu = True
                        break
                except Exception:
                    pass

        # lspci controller check (Linux)
        if not has_discrete_gpu and shutil.which("lspci"):
            try:
                p = subprocess.run(["lspci"], capture_output=True, text=True, timeout=1.5)
                if p.returncode == 0:
                    for line in p.stdout.splitlines():
                        lower = line.lower()
                        if any(t in lower for t in ["vga compatible controller", "3d controller", "display controller"]):
                            clean_name = line.split(":", 2)[-1].strip() if line.count(":") >= 2 else line
                            gpu_name = clean_name
                            if any(d in lower for d in ["nvidia", "geforce", "quadro", "rtx", "radeon rx", "radeon pro", "arc a"]):
                                has_discrete_gpu = True
                                gpu_vendor = "nvidia" if ("nvidia" in lower or "geforce" in lower) else ("intel" if "arc" in lower else "amd")
                            break
            except Exception:
                pass

        # Windows WMIC video controller fallback
        if not has_discrete_gpu and os.name == "nt":
            try:
                p = subprocess.run(
                    ["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:csv"],
                    capture_output=True, text=True, timeout=2.0,
                    creationflags=create_no_window
                )
                if p.returncode == 0:
                    for line in p.stdout.splitlines():
                        parts = [pt.strip() for pt in line.split(",") if pt.strip()]
                        if len(parts) >= 2 and parts[0] != "Node":
                            name_cand = parts[-1]
                            ram_cand = parts[-2] if len(parts) >= 3 else "0"
                            if any(d in name_cand.lower() for d in ["nvidia", "geforce", "quadro", "rtx", "radeon rx", "radeon pro", "arc"]):
                                has_discrete_gpu = True
                                gpu_name = name_cand
                                gpu_vendor = "nvidia" if ("nvidia" in name_cand.lower() or "geforce" in name_cand.lower()) else "amd"
                                try:
                                    vram_total_mb = int(ram_cand) // (1024 * 1024)
                                except Exception:
                                    pass
                                break
                            elif gpu_name == "Integrated / CPU":
                                gpu_name = name_cand
            except Exception:
                pass

        if override_gpu is not None:
            has_discrete_gpu = override_gpu.get("has_discrete_gpu", False)
            vram_total_mb = override_gpu.get("vram_total_mb", 0)
            vram_free_mb = override_gpu.get("vram_free_mb", vram_total_mb // 2)
            gpu_name = override_gpu.get("gpu_name", gpu_name)
            gpu_vendor = override_gpu.get("gpu_vendor", gpu_vendor)

        # 4. Disk Free Space
        try:
            disk_free_gb = round(shutil.disk_usage(os.path.expanduser("~")).free / (1024 ** 3), 1)
        except Exception:
            disk_free_gb = 10.0

        # 5. Hardware Tier & Adaptive Model Recommendation
        if (has_discrete_gpu and vram_total_mb >= 8000) or ram_available_mb >= 20000:
            hw_tier = "HIGH_END_GPU"
            recommended_model = "qwen2.5:7b"
            tier_desc = "High-End Discrete GPU / High-Capacity Workstation (Full 7B/8B Support)"
        elif (has_discrete_gpu and vram_total_mb >= 4000) or (has_avx2 and ram_available_mb >= 9000):
            hw_tier = "WORKSTATION_MID"
            recommended_model = "qwen2.5:3b"
            tier_desc = "Mid-Range GPU / High-Memory AVX2 Workstation (Optimal 3B Accuracy)"
        elif has_avx2 and ram_available_mb >= 4500:
            hw_tier = "BALANCED_CPU"
            recommended_model = "qwen2.5:1.5b"
            tier_desc = "Balanced CPU Inference with AVX2 Acceleration (Responsive 1.5B)"
        else:
            hw_tier = "ULTRA_LIGHT_CPU"
            recommended_model = "qwen2.5:0.5b"
            tier_desc = "Ultra-Light CPU Inference (Optimized for Legacy/Low-Power CPUs without AVX2)"

        # Installed models list
        if override_installed_models is not None:
            installed_models = list(override_installed_models)
        else:
            ollama_status = cls.check_local_ollama()
            installed_models = ollama_status.get("models", [])

        # Catalog definition
        catalog_defs = [
            {
                "id": "qwen2.5:0.5b",
                "name": "Qwen 2.5 0.5B (Ultra-Light)",
                "disk_mb": 398,
                "min_ram_mb": 800,
                "languages": "29+ incl. CS/EN/DE/ZH",
                "speed_cpu": "Fast (~1.5s/phrase)",
                "supports_vision": False,
                "description": "Ultra-lightweight model optimized for low-power or 4GB RAM CPUs without AVX2.",
            },
            {
                "id": "gemma3:1b",
                "name": "Gemma 3 1B (Google Ultra-Light)",
                "disk_mb": 815,
                "min_ram_mb": 1100,
                "languages": "140+ Multilingual",
                "speed_cpu": "Fast (~2.5s/phrase)",
                "supports_vision": False,
                "description": "Compact Google Gemma 3 1B model tailored for 4GB+ machines and snappy triage.",
            },
            {
                "id": "qwen2.5:1.5b",
                "name": "Qwen 2.5 1.5B (Balanced)",
                "disk_mb": 986,
                "min_ram_mb": 1600,
                "languages": "29+ incl. CS/EN/DE/ZH",
                "speed_cpu": "Medium (~3.5s/phrase)",
                "supports_vision": False,
                "description": "Recommended balanced choice for modern laptops and PCs with AVX2.",
            },
            {
                "id": "gemma2:2b",
                "name": "Gemma 2 2B (Google)",
                "disk_mb": 1600,
                "min_ram_mb": 2600,
                "languages": "Multilingual",
                "speed_cpu": "Moderate (~5s/phrase)",
                "supports_vision": False,
                "description": "Compact Google multilingual model with strong general reasoning.",
            },
            {
                "id": "qwen2.5:3b",
                "name": "Qwen 2.5 3B (High Accuracy)",
                "disk_mb": 1900,
                "min_ram_mb": 3200,
                "languages": "29+ High Accuracy",
                "speed_cpu": "Slow without AVX2/GPU",
                "supports_vision": False,
                "description": "High accuracy domain translator. Best with mid-range GPU or fast AVX2 multi-core CPU.",
            },
            {
                "id": "gemma3:4b",
                "name": "Gemma 3 4B (Google Vision + Text)",
                "disk_mb": 3300,
                "min_ram_mb": 3400,
                "languages": "140+ Multilingual + Screenshots",
                "speed_cpu": "Slow on CPU (Vision-Capable)",
                "supports_vision": True,
                "description": "Multimodal Gemma 3 model: reads J.O.E. / legacy software screenshots directly.",
            },
            {
                "id": "qwen2.5:7b",
                "name": "Qwen 2.5 7B (Studio Grade)",
                "disk_mb": 4700,
                "min_ram_mb": 5800,
                "languages": "29+ Studio Grade",
                "speed_cpu": "Requires GPU or >=16GB RAM",
                "supports_vision": False,
                "description": "State-of-the-art multilingual model. Requires discrete GPU (>=8GB VRAM) or >=16GB RAM.",
            },
            {
                "id": "llama3.1:8b",
                "name": "Llama 3.1 8B (Meta)",
                "disk_mb": 4900,
                "min_ram_mb": 6200,
                "languages": "Multilingual",
                "speed_cpu": "Requires GPU or >=16GB RAM",
                "supports_vision": False,
                "description": "Meta benchmark model. Requires discrete GPU (>=8GB VRAM) or >=16GB RAM.",
            },
        ]

        # Annotate catalog
        model_catalog = []
        for m in catalog_defs:
            is_rec = (m["id"] == recommended_model)
            is_ins = any(m["id"] == ins or ins.startswith(m["id"]) for ins in installed_models)
            if is_rec:
                compat = "RECOMMENDED"
            elif m["min_ram_mb"] > ram_available_mb * 0.90:
                compat = "INSUFFICIENT_RAM"
            elif not has_discrete_gpu and (m["min_ram_mb"] > 2200 or (not has_avx2 and m["min_ram_mb"] > 1800)):
                compat = "HEAVY_FOR_CPU"
            else:
                compat = "COMPATIBLE"

            item = dict(m)
            item["is_recommended"] = is_rec
            item["is_installed"] = is_ins
            item["compatibility"] = compat
            model_catalog.append(item)

        # Merge custom local models
        for ins in installed_models:
            if not any(m["id"] == ins or ins.startswith(m["id"].split(":")[0]) for m in model_catalog):
                ins_low = ins.lower()
                is_vision = any(tok in ins_low for tok in ("gemma3:4b", "gemma3:12b", "gemma3:27b", "vl", "llava", "minicpm-v", "vision", "moondream"))
                model_catalog.append({
                    "id": ins,
                    "name": f"Custom Local: {ins}",
                    "disk_mb": 0,
                    "min_ram_mb": 2048,
                    "languages": "User Local Model",
                    "speed_cpu": "Custom",
                    "supports_vision": is_vision,
                    "description": "Locally installed model in SPECTRA Local AI runtime.",
                    "is_recommended": False,
                    "is_installed": True,
                    "compatibility": "COMPATIBLE" if ram_available_mb >= 2500 else "INSUFFICIENT_RAM",
                })

        # Determine default_selected_model
        rec_item = next((m for m in model_catalog if m["id"] == recommended_model), None)
        if rec_item and rec_item["is_installed"]:
            default_selected = recommended_model
        else:
            compat_installed = next((m["id"] for m in model_catalog if m["is_installed"] and m["compatibility"] in ("RECOMMENDED", "COMPATIBLE")), None)
            if compat_installed:
                default_selected = compat_installed
            else:
                default_selected = recommended_model

        auto_unload_rec = bool(ram_available_mb < 8192 or not has_discrete_gpu)

        return {
            "cpu": {
                "model": cpu_model,
                "logical_cores": logical_cores,
                "simd_flags": simd_flags,
                "has_avx2": has_avx2,
            },
            "memory": {
                "ram_total_mb": ram_total_mb,
                "ram_available_mb": ram_available_mb,
            },
            "gpu": {
                "has_discrete_gpu": has_discrete_gpu,
                "vendor": gpu_vendor,
                "name": gpu_name,
                "vram_total_mb": vram_total_mb,
                "vram_free_mb": vram_free_mb,
            },
            "disk": {
                "disk_free_gb": disk_free_gb,
            },
            "tier": hw_tier,
            "tier_description": tier_desc,
            "recommended_model": recommended_model,
            "default_selected_model": default_selected,
            "auto_unload_recommended": auto_unload_rec,
            "model_catalog": model_catalog,
        }

    @staticmethod
    def _discover_local_ollama_models_on_disk() -> List[str]:
        """Scan standard Ollama manifest directories so installed models appear even when daemon is idle."""
        manifest_roots: List[str] = []
        env_models = (os.environ.get("OLLAMA_MODELS") or "").strip()
        if env_models:
            exp_env = os.path.expanduser(env_models)
            manifest_roots.append(os.path.join(exp_env, "manifests"))
            manifest_roots.append(exp_env)

        if os.name == "nt":
            manifest_roots.extend([
                os.path.expandvars(r"%USERPROFILE%\.ollama\models\manifests"),
                os.path.expandvars(r"%LOCALAPPDATA%\SPECTRA\ollama\models\manifests"),
                os.path.expandvars(r"%LOCALAPPDATA%\Ollama\models\manifests"),
            ])
        else:
            manifest_roots.extend([
                os.path.expanduser("~/.ollama/models/manifests"),
                os.path.expanduser("~/.local/share/spectra/ollama/models/manifests"),
                os.path.expanduser("~/.local/share/spectra/ollama/.ollama/models/manifests"),
                "/usr/share/ollama/.ollama/models/manifests",
                "/var/lib/ollama/.ollama/models/manifests",
            ])

        seen: set = set()
        found: List[str] = []
        for root in manifest_roots:
            try:
                if not root or not os.path.isdir(root):
                    continue
                for dirpath, _dirnames, filenames in os.walk(root):
                    for fname in filenames:
                        if fname.startswith("."):
                            continue
                        full_path = os.path.join(dirpath, fname)
                        rel = os.path.relpath(full_path, root).replace("\\", "/")
                        parts = [p for p in rel.split("/") if p]
                        if any(p.startswith(".") for p in parts):
                            continue
                        if len(parts) < 4:
                            continue
                        namespace, model_name, tag = parts[-3], parts[-2], parts[-1]
                        if not model_name or not tag:
                            continue
                        model_tag = f"{model_name}:{tag}" if namespace == "library" else f"{namespace}/{model_name}:{tag}"
                        if model_tag not in seen:
                            seen.add(model_tag)
                            found.append(model_tag)
            except OSError:
                continue
        return found

    @staticmethod
    def check_local_ollama(timeout: float = 0.35) -> Dict[str, Any]:
        """
        Tier 3: Check if local Ollama daemon is running on http://127.0.0.1:11434.
        STRICTLY localhost only (127.0.0.1). Never connects to external networks.
        Merges on-disk manifest tags so installed models are reported even when daemon is stopped.
        """
        endpoint = "http://127.0.0.1:11434"
        from spectra_hmi.inspector import KalermHmiInspector
        disk_models = KalermHmiInspector._discover_local_ollama_models_on_disk()
        try:
            req = urllib.request.Request(f"{endpoint}/api/tags", headers={"User-Agent": "SPECTRA-Offline-Auditor"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    api_models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                    merged: List[str] = []
                    seen: set = set()
                    for m in api_models + disk_models:
                        if m not in seen:
                            seen.add(m)
                            merged.append(m)
                    loaded_models = []
                    try:
                        req_ps = urllib.request.Request(f"{endpoint}/api/ps", headers={"User-Agent": "SPECTRA-Offline-Auditor"})
                        with urllib.request.urlopen(req_ps, timeout=timeout) as resp_ps:
                            if resp_ps.status == 200:
                                data_ps = json.loads(resp_ps.read().decode("utf-8"))
                                for m in data_ps.get("models", []):
                                    if m.get("name"):
                                        loaded_models.append(m["name"])
                    except Exception:
                        pass
                    return {
                        "available": True,
                        "endpoint": endpoint,
                        "models": merged,
                        "loaded_models": loaded_models,
                    }
        except Exception:
            pass
        return {
            "available": False,
            "endpoint": endpoint,
            "models": disk_models,
            "loaded_models": [],
        }

    @staticmethod
    def _find_ollama_binary() -> Optional[str]:
        """
        Locates the local Ollama binary across Linux, macOS, and Windows.
        Checks system PATH, user-space portable installations, and platform standard paths.
        """
        # 1. System PATH
        bin_path = shutil.which("ollama")
        if bin_path:
            return bin_path

        # 2. Linux / macOS user-space portable installations
        if os.name != "nt":
            candidates = [
                os.path.expanduser("~/.local/share/spectra/ollama/usr/bin/ollama"),
                os.path.expanduser("~/.local/share/spectra/ollama/bin/ollama"),
            ]
            for cand in candidates:
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    return cand

        # 3. Windows locations
        if os.name == "nt":
            portable_root = os.path.expandvars(r"%LOCALAPPDATA%\SPECTRA\ollama")
            candidates = [
                os.path.join(portable_root, "ollama.exe"),
                os.path.join(portable_root, "bin", "ollama.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Ollama\ollama.exe"),
            ]
            for cand in candidates:
                if os.path.isfile(cand):
                    return cand
            if os.path.isdir(portable_root):
                for root_dir, _dirs, files in os.walk(portable_root):
                    if "ollama.exe" in files:
                        return os.path.join(root_dir, "ollama.exe")

        return None

    @classmethod
    def get_ollama_download_progress(cls) -> Dict[str, Any]:
        """Returns a snapshot of the current engine install / model pull progress."""
        with cls._download_lock:
            return dict(cls._download_state)

    @classmethod
    def _update_download_progress(cls, **kwargs):
        with cls._download_lock:
            cls._download_state.update(kwargs)

    @classmethod
    def _download_engine_archive(cls, url: str, archive_path: str) -> bool:
        """Download portable AI runtime archive with verified TLS and Windows SChannel fallback.

        Returns False if cancelled by user; raises on unrecoverable download errors.
        """
        import tls_utils
        ssl_ctx = tls_utils.get_ssl_context()
        req = urllib.request.Request(url, headers={"User-Agent": "SPECTRA-Offline-Auditor"})

        def _is_cancel() -> bool:
            with cls._download_lock:
                return bool(cls._download_state.get("cancel_requested"))

        try:
            with urllib.request.urlopen(req, timeout=30.0, context=ssl_ctx) as resp:
                tot_len = int(resp.headers.get("Content-Length") or 0)
                dl_bytes = 0
                t0 = time.time()
                last_t = t0
                last_b = 0
                rolling_speed = 0.0

                cancelled = False
                with open(archive_path, "wb") as f_out:
                    while True:
                        if _is_cancel():
                            cancelled = True
                            break
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        dl_bytes += len(chunk)
                        now = time.time()
                        dt = now - last_t
                        if dt >= 0.25:
                            spd = (dl_bytes - last_b) / dt
                            mbps = spd / (1024.0 * 1024.0)
                            rolling_speed = round(mbps if rolling_speed == 0 else (0.7 * rolling_speed + 0.3 * mbps), 2)
                            last_b = dl_bytes
                            last_t = now

                        pct = round(min(99.0, (dl_bytes / float(tot_len)) * 100.0), 1) if tot_len > 0 else 0.0
                        eta = int((tot_len - dl_bytes) / (rolling_speed * 1024 * 1024)) if (tot_len > dl_bytes and rolling_speed > 0) else 0
                        cls._update_download_progress(
                            status="INSTALLING_ENGINE",
                            phase_label="Step 1/3: Installing Portable Local AI Engine",
                            status_text=f"Downloading engine ({dl_bytes / (1024*1024):.1f} MB / {tot_len / (1024*1024):.1f} MB)",
                            completed_bytes=dl_bytes,
                            total_bytes=tot_len,
                            percent=pct,
                            speed_mbps=rolling_speed,
                            eta_sec=eta,
                        )
                if cancelled:
                    if os.path.exists(archive_path):
                        try:
                            os.remove(archive_path)
                        except Exception:
                            pass
                    return False
            return True
        except Exception as url_err:
            # Fallback to Windows SChannel-backed curl.exe when Python hits local CA store issues
            is_tls_err = "CERTIFICATE_VERIFY_FAILED" in str(url_err) or "ssl" in str(url_err).lower()
            if os.name == "nt" and is_tls_err:
                cls._update_download_progress(
                    status="INSTALLING_ENGINE",
                    phase_label="Step 1/3: Installing Portable Local AI Engine",
                    status_text="Downloading engine via Windows SChannel TLS...",
                    percent=5.0,
                )

                def _on_prog(sz):
                    mb = sz / (1024.0 * 1024.0)
                    cls._update_download_progress(
                        status="INSTALLING_ENGINE",
                        phase_label="Step 1/3: Installing Portable Local AI Engine",
                        status_text=f"Downloading engine ({mb:.1f} MB downloaded)...",
                        completed_bytes=sz,
                        percent=min(95.0, round((mb / 600.0) * 95.0, 1)),
                    )

                tls_utils.windows_schannel_download(url, archive_path, cancel_check=_is_cancel, progress_cb=_on_prog)
                return not _is_cancel()
            raise

    @classmethod
    def _install_portable_ollama(cls) -> bool:
        """
        Installs a user-space portable copy of the Local AI runtime without requiring root/sudo.
        Linux: Uses pacman -Sp if available (Arch/Omarchy) or official Linux tgz.
        Windows: Downloads official Windows zip into %LOCALAPPDATA%\\SPECTRA\\ollama.
        """
        if cls._find_ollama_binary():
            return True

        cls._update_download_progress(
            status="INSTALLING_ENGINE",
            phase_label="Step 1/3: Installing Portable Local AI Engine",
            status_text="Preparing portable user-space runtime...",
            percent=0.0,
            completed_bytes=0,
            total_bytes=0,
            speed_mbps=0.0,
            eta_sec=0,
        )

        if os.name != "nt":
            dest_dir = os.path.expanduser("~/.local/share/spectra/ollama")
            os.makedirs(dest_dir, exist_ok=True)

            pkg_url = None
            if shutil.which("pacman"):
                try:
                    res = subprocess.run(["pacman", "-Sp", "ollama"], capture_output=True, text=True, timeout=5)
                    if res.returncode == 0:
                        lines = [line.strip() for line in res.stdout.splitlines() if line.strip().startswith("http")]
                        if lines:
                            pkg_url = lines[0]
                except Exception:
                    pass

            if pkg_url:
                if not str(pkg_url).lower().startswith("https://"):
                    cls._update_download_progress(
                        status="ERROR",
                        active=False,
                        error=f"Refusing insecure non-HTTPS Ollama package URL: {pkg_url}",
                        status_text="Refused insecure non-HTTPS download URL",
                    )
                    return False
                archive_path = os.path.join(dest_dir, "ollama_pkg.tar.zst")
                url = pkg_url
                is_zst = True
            else:
                archive_path = os.path.join(dest_dir, "ollama-linux-amd64.tgz")
                url = "https://ollama.com/download/ollama-linux-amd64.tgz"
                is_zst = False

            if not str(url).lower().startswith("https://"):
                return False

            try:
                if not cls._download_engine_archive(url, archive_path):
                    return False
            except Exception as e:
                cls._update_download_progress(
                    status="ERROR",
                    active=False,
                    error=f"Engine download failed: {e}",
                    status_text=f"Failed to download Local AI engine: {e}"
                )
                return False

            cls._update_download_progress(status_text="Extracting engine files...", percent=99.0)
            try:
                extract_cmd = [
                    "tar",
                    "--no-same-owner",
                    "--no-same-permissions",
                    "-xf" if is_zst else "-xzf",
                    archive_path,
                    "-C",
                    dest_dir,
                ]
                subprocess.run(extract_cmd, check=True, timeout=60)
            except Exception as e:
                cls._update_download_progress(
                    status="ERROR",
                    active=False,
                    error=f"Failed to extract engine archive: {e}",
                    status_text=f"Extraction error: {e}"
                )
                return False
            finally:
                if os.path.exists(archive_path):
                    try:
                        os.remove(archive_path)
                    except Exception:
                        pass

        else:
            dest_dir = os.path.expandvars(r"%LOCALAPPDATA%\SPECTRA\ollama")
            os.makedirs(dest_dir, exist_ok=True)
            archive_path = os.path.join(dest_dir, "ollama-windows-amd64.zip")
            url = "https://ollama.com/download/ollama-windows-amd64.zip"

            try:
                if not cls._download_engine_archive(url, archive_path):
                    return False

                import zipfile
                cls._update_download_progress(status_text="Extracting engine files...", percent=99.0)
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(dest_dir)
            except Exception as e:
                cls._update_download_progress(
                    status="ERROR",
                    active=False,
                    error=f"Windows engine download/extract failed: {e}",
                    status_text=f"Failed to install Local AI engine: {e}"
                )
                return False
            finally:
                if os.path.exists(archive_path):
                    try:
                        os.remove(archive_path)
                    except Exception:
                        pass

        return bool(cls._find_ollama_binary())

    @classmethod
    def _pull_worker(cls, target_model: str):
        try:
            # 1. Step 1: Ensure Local AI Binary is Installed
            if not cls._find_ollama_binary():
                ok = cls._install_portable_ollama()
                if not ok or not cls._find_ollama_binary():
                    with cls._download_lock:
                        if cls._download_state.get("cancel_requested"):
                            cls._download_state.update({
                                "status": "CANCELLED",
                                "active": False,
                                "phase_label": "Installation Cancelled",
                                "status_text": "Installation cancelled by user.",
                            })
                        elif cls._download_state.get("status") != "ERROR":
                            cls._download_state.update({
                                "status": "ERROR",
                                "active": False,
                                "error": "Portable Local AI engine could not be installed.",
                                "status_text": "Installation failed.",
                            })
                    return

            # 2. Step 2: Ensure Local Daemon is Running
            cls._update_download_progress(
                status="STARTING_ENGINE",
                phase_label="Step 2/3: Starting Local AI Engine (127.0.0.1:11434)",
                status_text="Verifying background runtime...",
                percent=0.0,
                completed_bytes=0,
                total_bytes=0,
            )

            chk = cls.check_local_ollama()
            if not chk.get("available"):
                cls.control_local_ollama("start")
                t0 = time.time()
                while time.time() - t0 < 25.0:
                    with cls._download_lock:
                        if cls._download_state.get("cancel_requested"):
                            cls._download_state.update({
                                "status": "CANCELLED",
                                "active": False,
                                "phase_label": "Download Cancelled",
                                "status_text": "Cancelled by user.",
                            })
                            return
                    if cls.check_local_ollama()["available"]:
                        break
                    time.sleep(0.4)

            chk = cls.check_local_ollama()
            if not chk.get("available"):
                cls._update_download_progress(
                    status="ERROR",
                    active=False,
                    error="Local AI runtime failed to start on 127.0.0.1:11434",
                    status_text="Runtime startup failed.",
                )
                return

            # 3. Step 3: Stream Model Pull with stream: True
            cls._update_download_progress(
                status="PULLING_MODEL",
                phase_label=f"Step 3/3: Downloading Model: {target_model}",
                status_text="Connecting to model registry...",
                percent=0.0,
                completed_bytes=0,
                total_bytes=0,
                speed_mbps=0.0,
                eta_sec=0,
            )

            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/pull",
                data=json.dumps({"name": target_model, "stream": True}).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "SPECTRA-Offline-Auditor"}
            )

            with urllib.request.urlopen(req, timeout=3600.0) as resp:
                t_start = time.time()
                last_completed = 0
                last_time = t_start
                rolling_speed = 0.0

                for raw_line in resp:
                    with cls._download_lock:
                        if cls._download_state.get("cancel_requested"):
                            cls._download_state.update({
                                "status": "CANCELLED",
                                "active": False,
                                "phase_label": "Download Cancelled",
                                "status_text": "Model pull cancelled by user.",
                            })
                            return

                    if not raw_line:
                        continue
                    line_str = raw_line.decode("utf-8", "ignore").strip()
                    if not line_str:
                        continue
                    try:
                        obj = json.loads(line_str)
                    except Exception:
                        continue

                    if "error" in obj:
                        cls._update_download_progress(
                            status="ERROR",
                            active=False,
                            error=str(obj["error"]),
                            status_text=f"Error: {obj['error']}",
                        )
                        return

                    status_str = obj.get("status", "")
                    total = int(obj.get("total") or 0)
                    completed = int(obj.get("completed") or 0)

                    now = time.time()
                    dt = now - last_time
                    if dt >= 0.25 and completed > last_completed:
                        speed_bytes = (completed - last_completed) / dt
                        mbps = speed_bytes / (1024.0 * 1024.0)
                        rolling_speed = round(mbps if rolling_speed == 0 else (0.7 * rolling_speed + 0.3 * mbps), 2)
                        last_completed = completed
                        last_time = now

                    pct = 0.0
                    eta = 0
                    if total > 0:
                        pct = round(min(99.9, (completed / float(total)) * 100.0), 1)
                        if rolling_speed > 0:
                            remaining_bytes = max(0, total - completed)
                            eta = int(remaining_bytes / (rolling_speed * 1024.0 * 1024.0))

                    if total > 0:
                        comp_mb = round(completed / (1024.0 * 1024.0), 1)
                        tot_mb = round(total / (1024.0 * 1024.0), 1)
                        disp_text = f"{status_str} ({comp_mb} MB / {tot_mb} MB)"
                    else:
                        disp_text = status_str

                    cls._update_download_progress(
                        status="PULLING_MODEL",
                        phase_label=f"Downloading Model: {target_model}",
                        status_text=disp_text,
                        completed_bytes=completed,
                        total_bytes=total,
                        percent=pct,
                        speed_mbps=rolling_speed,
                        eta_sec=eta,
                    )

            cls._update_download_progress(
                status="COMPLETED",
                phase_label="Model Download Complete",
                status_text=f"Model '{target_model}' downloaded and ready for offline use!",
                percent=100.0,
                active=False,
                eta_sec=0,
            )

        except Exception as e:
            cls._update_download_progress(
                status="ERROR",
                active=False,
                error=str(e),
                status_text=f"Pull error: {e}",
            )

    @classmethod
    def start_async_model_pull(cls, model: Optional[str] = None) -> Dict[str, Any]:
        """Initiates an asynchronous portable engine install & streaming model download."""
        with cls._download_lock:
            if cls._download_state.get("active"):
                return {
                    "status": "ALREADY_ACTIVE",
                    "message": f"Download already in progress for '{cls._download_state.get('model')}'",
                    "progress": dict(cls._download_state),
                }
            target_model = model or "qwen2.5:0.5b"
            cls._download_state = {
                "active": True,
                "status": "INITIALIZING",
                "model": target_model,
                "phase_label": "Initializing download task...",
                "status_text": "Preparing environment...",
                "completed_bytes": 0,
                "total_bytes": 0,
                "percent": 0.0,
                "speed_mbps": 0.0,
                "eta_sec": 0,
                "error": "",
                "cancel_requested": False,
            }

        worker = threading.Thread(
            target=cls._pull_worker,
            args=(target_model,),
            daemon=True,
            name="SpectraOllamaPullWorker"
        )
        worker.start()

        return {
            "status": "STARTED",
            "message": f"Started downloading '{target_model}'...",
            "progress": cls.get_ollama_download_progress(),
        }

    @classmethod
    def get_ai_system_status(cls) -> Dict[str, Any]:
        """
        Combines host hardware self-check, local Ollama daemon reachability,
        binary installation check, and managed subprocess tracking.
        """
        ollama = cls.check_local_ollama()
        installed_models = [
            m.get("name") if isinstance(m, dict) else str(m)
            for m in (ollama.get("models") or [])
        ]
        try:
            hw = cls.probe_host_hardware(override_installed_models=installed_models)
        except Exception:
            hw = {
                "cpu": {"model": "Host CPU", "logical_cores": 4, "has_avx2": True},
                "memory": {"ram_total_mb": 8192, "ram_available_mb": 4096},
                "gpu": {"has_discrete_gpu": False, "name": "CPU Inference"},
                "disk": {"disk_free_gb": 20.0},
                "tier": "BALANCED_CPU",
                "recommended_model": "qwen2.5:0.5b",
                "default_selected_model": installed_models[0] if installed_models else "qwen2.5:0.5b",
                "model_catalog": [
                    {"id": "qwen2.5:0.5b", "name": "Qwen 2.5 0.5B (Ultra-Light)", "min_ram_mb": 800, "supports_vision": False, "compatibility": "RECOMMENDED", "is_recommended": True, "is_installed": "qwen2.5:0.5b" in installed_models},
                    {"id": "gemma3:1b", "name": "Gemma 3 1B (Google Ultra-Light)", "min_ram_mb": 1100, "supports_vision": False, "compatibility": "COMPATIBLE", "is_recommended": False, "is_installed": "gemma3:1b" in installed_models},
                    {"id": "qwen2.5:1.5b", "name": "Qwen 2.5 1.5B (Balanced)", "min_ram_mb": 1600, "supports_vision": False, "compatibility": "COMPATIBLE", "is_recommended": False, "is_installed": "qwen2.5:1.5b" in installed_models},
                    {"id": "llama3.2:1b", "name": "Llama 3.2 1B (Meta)", "min_ram_mb": 1200, "supports_vision": False, "compatibility": "COMPATIBLE", "is_recommended": False, "is_installed": "llama3.2:1b" in installed_models},
                    {"id": "gemma2:2b", "name": "Gemma 2 2B (Google)", "min_ram_mb": 2600, "supports_vision": False, "compatibility": "COMPATIBLE", "is_recommended": False, "is_installed": "gemma2:2b" in installed_models},
                    {"id": "qwen2.5:3b", "name": "Qwen 2.5 3B (High Accuracy)", "min_ram_mb": 3200, "supports_vision": False, "compatibility": "COMPATIBLE", "is_recommended": False, "is_installed": "qwen2.5:3b" in installed_models},
                    {"id": "gemma3:4b", "name": "Gemma 3 4B (Google Vision + Text)", "min_ram_mb": 3400, "supports_vision": True, "compatibility": "HEAVY_FOR_CPU", "is_recommended": False, "is_installed": "gemma3:4b" in installed_models},
                    {"id": "qwen2.5:7b", "name": "Qwen 2.5 7B (Studio Grade)", "min_ram_mb": 5800, "supports_vision": False, "compatibility": "HEAVY_FOR_CPU", "is_recommended": False, "is_installed": "qwen2.5:7b" in installed_models},
                    {"id": "llama3.1:8b", "name": "Llama 3.1 8B (Meta)", "min_ram_mb": 6200, "supports_vision": False, "compatibility": "HEAVY_FOR_CPU", "is_recommended": False, "is_installed": "llama3.1:8b" in installed_models},
                ],
            }
        bin_path = cls._find_ollama_binary()
        is_managed = bool(cls._ollama_process and cls._ollama_process.poll() is None)
        return {
            "hardware": hw,
            "ollama": ollama,
            "binary_installed": bool(bin_path),
            "binary_path": bin_path or "",
            "is_managed_process": is_managed,
        }

    @classmethod
    def control_local_ollama(cls, action: str, model: Optional[str] = None) -> Dict[str, Any]:
        """
        Embedded Ollama controller: starts, unloads, stops, or pulls local models.
        """
        action = (action or "").lower().strip()
        endpoint = "http://127.0.0.1:11434"

        if action == "start":
            chk = cls.check_local_ollama()
            if chk.get("available"):
                return {
                    "status": "ALREADY_RUNNING",
                    "message": "Local AI engine is already active on http://127.0.0.1:11434",
                    "models": chk.get("models", []),
                    "ai_status": cls.get_ai_system_status(),
                }

            bin_path = cls._find_ollama_binary()
            if not bin_path:
                return {
                    "status": "BINARY_NOT_FOUND",
                    "message": "Local AI binary not found. Click 'Pull Model' to auto-install the portable engine.",
                    "install_cmd": "Auto-install available",
                    "ai_status": cls.get_ai_system_status(),
                }

            env = os.environ.copy()
            env["OLLAMA_HOST"] = "127.0.0.1:11434"
            if not (env.get("OLLAMA_MODELS") or "").strip():
                default_manifests = os.path.expanduser("~/.ollama/models/manifests")
                portable_models = os.path.expanduser("~/.local/share/spectra/ollama/models")
                portable_manifests = os.path.join(portable_models, "manifests")
                has_default = os.path.isdir(default_manifests) and any(
                    bool(files) for _, _, files in os.walk(default_manifests)
                )
                has_portable = os.path.isdir(portable_manifests) and any(
                    bool(files) for _, _, files in os.walk(portable_manifests)
                )
                if not has_default and has_portable:
                    env["OLLAMA_MODELS"] = portable_models
            bin_dir = os.path.dirname(os.path.abspath(bin_path))

            # Auto-configure library/DLL search paths if running portable engine
            if os.name == "nt":
                win_paths = [bin_dir, os.path.join(bin_dir, "lib", "ollama")]
                existing_path = env.get("PATH", "")
                prepend_win = ";".join([p for p in win_paths if os.path.isdir(p)])
                if prepend_win:
                    env["PATH"] = f"{prepend_win};{existing_path}" if existing_path else prepend_win
            elif ".local/share/spectra/ollama" in bin_path or "~/.local/share/spectra/ollama" in bin_path:
                base_dir = os.path.expanduser("~/.local/share/spectra/ollama")
                lib_paths = [
                    os.path.join(base_dir, "usr", "lib", "ollama"),
                    os.path.join(base_dir, "lib", "ollama"),
                    os.path.join(base_dir, "usr", "lib"),
                    os.path.join(base_dir, "lib"),
                ]
                existing_ld = env.get("LD_LIBRARY_PATH", "")
                prepend_str = ":".join([p for p in lib_paths if os.path.isdir(p)])
                if prepend_str:
                    env["LD_LIBRARY_PATH"] = f"{prepend_str}:{existing_ld}" if existing_ld else prepend_str

            spawn_kwargs: Dict[str, Any] = {
                "env": env,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                spawn_kwargs["creationflags"] = 0x08000000
                spawn_kwargs["cwd"] = bin_dir
            else:
                spawn_kwargs["start_new_session"] = True

            try:
                proc = subprocess.Popen([bin_path, "serve"], **spawn_kwargs)
                cls._ollama_process = proc
            except Exception as e:
                return {"status": "ERROR", "message": f"Failed to start Local AI engine: {e}", "ai_status": cls.get_ai_system_status()}

            t0 = time.time()
            while time.time() - t0 < 12.0:
                time.sleep(0.35)
                chk = cls.check_local_ollama(timeout=0.25)
                if chk.get("available"):
                    return {
                        "status": "SUCCESS",
                        "message": "Local AI engine started successfully on 127.0.0.1:11434",
                        "models": chk.get("models", []),
                        "ai_status": cls.get_ai_system_status(),
                    }

            return {
                "status": "START_TIMEOUT",
                "message": "Local AI process launched but endpoint did not respond within 12.0s",
                "ai_status": cls.get_ai_system_status(),
            }

        elif action == "unload":
            models_to_unload = []
            if model:
                models_to_unload.append(model)
            else:
                try:
                    req = urllib.request.Request(f"{endpoint}/api/ps", headers={"User-Agent": "SPECTRA-Offline-Auditor"})
                    with urllib.request.urlopen(req, timeout=1.0) as resp:
                        if resp.status == 200:
                            ps_data = json.loads(resp.read().decode("utf-8"))
                            for m in ps_data.get("models", []):
                                if m.get("name"):
                                    models_to_unload.append(m["name"])
                except Exception:
                    pass

            unloaded = []
            for m in models_to_unload:
                try:
                    payload = json.dumps({"model": m, "keep_alive": 0}).encode("utf-8")
                    req = urllib.request.Request(
                        f"{endpoint}/api/generate",
                        data=payload,
                        headers={"Content-Type": "application/json", "User-Agent": "SPECTRA-Offline-Auditor"}
                    )
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        if resp.status == 200:
                            unloaded.append(m)
                except Exception:
                    pass

            return {
                "status": "SUCCESS",
                "message": f"Evicted {len(unloaded)} model(s) from memory" if unloaded else "No active models in memory to unload",
                "unloaded_models": unloaded,
                "ai_status": cls.get_ai_system_status(),
            }

        elif action == "stop":
            cls.control_local_ollama("unload")
            if cls._ollama_process and cls._ollama_process.poll() is None:
                try:
                    cls._ollama_process.terminate()
                    cls._ollama_process.wait(timeout=2.0)
                except Exception:
                    try:
                        cls._ollama_process.kill()
                    except Exception:
                        pass
                cls._ollama_process = None

            # Also stop any user/external 'ollama serve' processes on 127.0.0.1:11434
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/IM", "ollama.exe"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=0x08000000,
                    )
                else:
                    subprocess.run(["pkill", "-f", "ollama serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            # Wait up to 2.0s confirming 127.0.0.1:11434 is actually offline
            t_stop0 = time.time()
            while time.time() - t_stop0 < 2.0:
                chk = cls.check_local_ollama(timeout=0.15)
                if not chk.get("available"):
                    break
                time.sleep(0.2)

            chk_final = cls.check_local_ollama(timeout=0.15)
            if chk_final.get("available"):
                return {
                    "status": "EXTERNAL_DAEMON",
                    "message": "Local AI is running as an external system service (RAM unloaded; stop system service separately)",
                    "ai_status": cls.get_ai_system_status(),
                }

            return {
                "status": "SUCCESS",
                "message": "Local AI engine stopped and memory unloaded",
                "ai_status": cls.get_ai_system_status(),
            }

        elif action in ("pull", "pull_async"):
            return cls.start_async_model_pull(model)

        elif action == "cancel_pull":
            with cls._download_lock:
                cls._download_state["cancel_requested"] = True
            return {
                "status": "CANCEL_REQUESTED",
                "message": "Cancelling model download...",
                "progress": cls.get_ollama_download_progress(),
            }

        elif action == "delete":
            target_model = (model or "").strip()
            if not target_model:
                return {"status": "ERROR", "message": "No model specified to delete."}

            was_offline = not cls.check_local_ollama(timeout=0.3).get("available")
            if was_offline:
                start_res = cls.control_local_ollama("start")
                if start_res.get("status") not in ("ALREADY_RUNNING", "STARTED", "SUCCESS"):
                    return {
                        "status": "ERROR",
                        "message": start_res.get("message") or "Local AI runtime must be installed to delete local models.",
                        "ai_status": cls.get_ai_system_status(),
                    }

            try:
                payload = json.dumps({"name": target_model}).encode("utf-8")
                req = urllib.request.Request(
                    f"{endpoint}/api/delete",
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "SPECTRA-Offline-Auditor"},
                    method="DELETE",
                )
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    if resp.status not in (200, 204):
                        return {"status": "ERROR", "message": f"Delete returned HTTP {resp.status}", "ai_status": cls.get_ai_system_status()}
                return {
                    "status": "SUCCESS",
                    "message": f"Deleted local model '{target_model}' from disk.",
                    "deleted_model": target_model,
                    "ai_status": cls.get_ai_system_status(),
                }
            except urllib.error.HTTPError as he:
                return {"status": "ERROR", "message": f"Failed to delete '{target_model}': HTTP {he.code}", "ai_status": cls.get_ai_system_status()}
            except Exception as e:
                return {"status": "ERROR", "message": f"Failed to delete '{target_model}': {e}", "ai_status": cls.get_ai_system_status()}

        return {"status": "UNKNOWN_ACTION", "message": f"Action '{action}' is not supported"}

