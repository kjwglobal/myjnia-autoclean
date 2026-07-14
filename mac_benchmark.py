#!/usr/bin/env python3
"""
Small local benchmark for macOS.

This is meant for repeatable before/after checks on the same machine, not for
official cross-machine rankings. It uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any


MIB = 1024 * 1024
GIB = 1024 * 1024 * 1024


def run_command(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def sysctl(name: str) -> str | None:
    return run_command(["sysctl", "-n", name])


def thermal_status() -> str | None:
    output = run_command(["pmset", "-g", "therm"])
    if not output:
        return None
    return " | ".join(line.strip() for line in output.splitlines() if line.strip())


def system_info() -> dict[str, Any]:
    memory_bytes = sysctl("hw.memsize")
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "system": platform.platform(),
        "machine": platform.machine(),
        "macos": run_command(["sw_vers", "-productVersion"]),
        "cpu": sysctl("machdep.cpu.brand_string") or platform.processor() or "unknown",
        "logical_cpus": os.cpu_count(),
        "memory_gib": round(int(memory_bytes) / GIB, 2) if memory_bytes else None,
        "python": sys.version.split()[0],
        "thermal_status": thermal_status(),
    }


def time_call(fn, repeats: int = 3) -> dict[str, Any]:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        value = fn()
        elapsed = time.perf_counter() - start
        samples.append((elapsed, value))
    times = [sample[0] for sample in samples]
    return {
        "best_seconds": min(times),
        "median_seconds": statistics.median(times),
        "samples_seconds": [round(t, 6) for t in times],
        "last_value": samples[-1][1],
    }


def integer_crunch(duration: float) -> int:
    deadline = time.perf_counter() + duration
    loops = 0
    state = 0x243F_6A88_85A3_08D3
    mask = (1 << 64) - 1
    while time.perf_counter() < deadline:
        for _ in range(50_000):
            state ^= (state << 13) & mask
            state ^= state >> 7
            state ^= (state << 17) & mask
            state = (state * 0x9E37_79B9_7F4A_7C15 + 0xBF58_476D_1CE4_E5B9) & mask
            loops += 1
    return loops


def hash_crunch(duration: float, block_size: int = 4 * MIB) -> int:
    block = bytes((i * 131 + 17) % 251 for i in range(block_size))
    deadline = time.perf_counter() + duration
    bytes_hashed = 0
    digest = b""
    while time.perf_counter() < deadline:
        digest = hashlib.blake2b(block, digest_size=32).digest()
        bytes_hashed += block_size
    if digest[0] == 256:
        raise RuntimeError("unreachable")
    return bytes_hashed


def run_parallel(fn_name: str, duration: float, workers: int) -> tuple[float, list[int]]:
    fn = integer_crunch if fn_name == "integer" else hash_crunch
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        values = list(pool.map(fn, [duration] * workers))
    elapsed = time.perf_counter() - start
    return elapsed, values


def cpu_integer_suite(duration: float, workers: int) -> dict[str, Any]:
    single_start = time.perf_counter()
    single_loops = integer_crunch(duration)
    single_elapsed = time.perf_counter() - single_start

    multi_elapsed, worker_loops = run_parallel("integer", duration, workers)
    single_rate = single_loops / single_elapsed
    multi_rate = sum(worker_loops) / multi_elapsed
    return {
        "single_loops_per_sec": round(single_rate, 2),
        "multi_loops_per_sec": round(multi_rate, 2),
        "workers": workers,
        "scale_vs_single": round(multi_rate / single_rate, 2) if single_rate else None,
    }


def hash_suite(duration: float, workers: int) -> dict[str, Any]:
    single_start = time.perf_counter()
    single_bytes = hash_crunch(duration)
    single_elapsed = time.perf_counter() - single_start

    multi_elapsed, worker_bytes = run_parallel("hash", duration, workers)
    single_rate = single_bytes / single_elapsed
    multi_rate = sum(worker_bytes) / multi_elapsed
    return {
        "single_gib_per_sec": round(single_rate / GIB, 3),
        "multi_gib_per_sec": round(multi_rate / GIB, 3),
        "workers": workers,
        "scale_vs_single": round(multi_rate / single_rate, 2) if single_rate else None,
    }


def memory_copy_suite(size_mib: int, repeats: int) -> dict[str, Any]:
    size = size_mib * MIB
    source = bytearray((i * 29 + 7) % 251 for i in range(size))
    target = bytearray(size)

    def copy_once() -> int:
        target[:] = source
        return target[0] + target[-1]

    result = time_call(copy_once, repeats=repeats)
    bytes_moved = size * 2
    best_gib_sec = bytes_moved / result["best_seconds"] / GIB
    return {
        "size_mib": size_mib,
        "best_gib_per_sec": round(best_gib_sec, 3),
        "median_seconds": round(result["median_seconds"], 6),
        "samples_seconds": result["samples_seconds"],
    }


def disk_suite(directory: Path, size_mib: int, block_mib: int = 4) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    block = bytes((i * 19 + 11) % 251 for i in range(block_mib * MIB))
    total_bytes = size_mib * MIB
    blocks = math.ceil(total_bytes / len(block))
    path = directory / f".mac_benchmark_{os.getpid()}_{int(time.time())}.tmp"

    try:
        start = time.perf_counter()
        written = 0
        with path.open("wb", buffering=0) as handle:
            for _ in range(blocks):
                remaining = total_bytes - written
                chunk = block if remaining >= len(block) else block[:remaining]
                handle.write(chunk)
                written += len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        write_seconds = time.perf_counter() - start

        start = time.perf_counter()
        read_bytes = 0
        checksum = 0
        with path.open("rb", buffering=0) as handle:
            while True:
                chunk = handle.read(len(block))
                if not chunk:
                    break
                read_bytes += len(chunk)
                checksum ^= chunk[0]
        read_seconds = time.perf_counter() - start
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    return {
        "directory": str(directory),
        "size_mib": size_mib,
        "write_mib_per_sec": round(size_mib / write_seconds, 2),
        "read_mib_per_sec_cached": round((read_bytes / MIB) / read_seconds, 2),
        "write_seconds": round(write_seconds, 4),
        "read_seconds": round(read_seconds, 4),
        "checksum": checksum,
    }


def local_score(cpu: dict[str, Any], hashes: dict[str, Any], memory: dict[str, Any]) -> int:
    # A deliberately simple local score. Use raw metrics for serious comparisons.
    components = [
        cpu["single_loops_per_sec"] / 1_000_000,
        cpu["multi_loops_per_sec"] / 1_000_000,
        hashes["single_gib_per_sec"],
        hashes["multi_gib_per_sec"],
        memory["best_gib_per_sec"],
    ]
    return round(statistics.geometric_mean(max(value, 0.001) for value in components) * 1000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Small repeatable benchmark for macOS.")
    parser.add_argument("--duration", type=float, default=3.0, help="seconds per CPU/hash test")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1, help="parallel workers")
    parser.add_argument("--memory-mib", type=int, default=256, help="memory copy buffer size")
    parser.add_argument("--disk-mib", type=int, default=512, help="temporary disk test size")
    parser.add_argument("--disk-dir", type=Path, default=Path.cwd(), help="directory for disk test")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--no-disk", action="store_true", help="skip disk test")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workers = max(1, args.workers)
    disk_dir = args.disk_dir.expanduser().resolve()

    info = system_info()
    cpu = cpu_integer_suite(args.duration, workers)
    hashes = hash_suite(args.duration, workers)
    memory = memory_copy_suite(args.memory_mib, repeats=3)
    disk = None if args.no_disk else disk_suite(disk_dir, args.disk_mib)

    results = {
        "system": info,
        "cpu_integer": cpu,
        "hash_blake2b": hashes,
        "memory_copy": memory,
        "disk_sequential": disk,
        "local_score": local_score(cpu, hashes, memory),
    }

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    print("Mac Local Benchmark")
    print("===================")
    print(f"System: {info['cpu']} | {info['logical_cpus']} CPUs | macOS {info['macos']}")
    if info.get("memory_gib") is not None:
        print(f"Memory: {info['memory_gib']} GiB")
    if info.get("thermal_status"):
        print(f"Thermal: {info['thermal_status']}")
    print()
    print(f"Local score: {results['local_score']} (compare only with this script)")
    print()
    print("CPU integer:")
    print(f"  Single: {cpu['single_loops_per_sec']:,.0f} loops/s")
    print(f"  Multi:  {cpu['multi_loops_per_sec']:,.0f} loops/s ({cpu['workers']} workers, {cpu['scale_vs_single']}x)")
    print("Hash BLAKE2b:")
    print(f"  Single: {hashes['single_gib_per_sec']} GiB/s")
    print(f"  Multi:  {hashes['multi_gib_per_sec']} GiB/s ({hashes['workers']} workers, {hashes['scale_vs_single']}x)")
    print("Memory copy:")
    print(f"  Best:   {memory['best_gib_per_sec']} GiB/s ({memory['size_mib']} MiB buffer)")
    if disk:
        print("Disk sequential:")
        print(f"  Write:  {disk['write_mib_per_sec']} MiB/s ({disk['size_mib']} MiB, fsync)")
        print(f"  Read:   {disk['read_mib_per_sec_cached']} MiB/s cached read")
        print(f"  Dir:    {disk['directory']}")
    print()
    print("Tip: run 3 times after closing heavy apps. For thermal behavior, use a longer --duration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
