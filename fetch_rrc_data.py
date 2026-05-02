import argparse
import json
import subprocess
import sys
import shutil
import pandas as pd

from multiprocessing import Pool
from pathlib import Path
from datetime import datetime


BGPKIT_BIN = shutil.which("bgpkit-parser") or shutil.which(
    "bgpkit-parser", path=str(Path.home() / ".cargo/bin")
)

RIB_TIME = "0000"
OUT_DIR = Path("rrc/out")
CACHE_DIR = Path("rrc/cache")
LOG_DIR = Path("rrc/logs")
LOG_FILE: Path | None = None

CACHE_WORKERS = 8 # Phase 1
PARSE_WORKERS = 40  # Phase 2

ROUTEVIEWS_VP_NAMES: dict[str, str] = {
    "routeviews1": "route-views1",
    "routeviews2": "route-views2",
    "routeviews3": "route-views3",
    "routeviews4": "route-views4",
    "routeviews5": "route-views5",
    "routeviews6": "route-views6",
    "linx": "route-views.linx",
    "eqix": "route-views.eqix",
    "isc": "route-views.isc",
    "kixp": "route-views.kixp",
    "napafrica": "route-views.napafrica",
    "nwax": "route-views.nwax",
    "perth": "route-views.perth",
    "saopaulo": "route-views.saopaulo",
    "sfmix": "route-views.sfmix",
    "sg": "route-views.sg",
    "soxrs": "route-views.soxrs",
    "sydney": "route-views.sydney",
    "telxatl": "route-views.telxatl",
    "wide": "route-views.wide",
}


def init_log_file(yyyy: str, mm: str, dd: str) -> None:
    global LOG_FILE
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOG_DIR / f"{yyyy}-{mm}-{dd}.log"


def log_message(message: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {message}\n"
    if LOG_FILE is None:
        sys.stderr.write(line)
        return
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def build_url(org: str, vp_id: str, yyyy: str, mm: str, dd: str) -> str | None:
    if org == "ripe":
        return f"https://data.ris.ripe.net/{vp_id}/{yyyy}.{mm}/bview.{yyyy}{mm}{dd}.{RIB_TIME}.gz"
    elif org == "routeviews":
        vp_name = ROUTEVIEWS_VP_NAMES.get(vp_id)
        if not vp_name:
            log_message(
                f"vantage point '{vp_id}' not mapped to a repository archive",
                level="ERROR",
            )
            return None
        return f"https://archive.routeviews.org/{vp_name}/bgpdata/{yyyy}.{mm}/RIBS/rib.{yyyy}{mm}{dd}.{RIB_TIME}.bz2"
    else:
        log_message(f"Skipped unknown org: {org}", level="WARN")
        return None


# Phase 1 worker: cache warm-up
def warm_cache(args: tuple) -> None:
    org, vp_id, yyyy, mm, dd = args
    url = build_url(org, vp_id, yyyy, mm, dd)
    if url is None:
        return

    log_message(f"CACHE  {org}/{vp_id}")
    cmd = [
        "bgpkit-parser", url,
        "--cache-dir", CACHE_DIR.as_posix(),
        "--peer-ip", "0.0.0.0",
        "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log_message(
                f"Cache warm-up failed for {url}. stderr: {result.stderr.strip()}",
                level="ERROR",
            )
    except FileNotFoundError:
        log_message(
            "bgpkit-parser not found. Make sure it is installed and on PATH.",
            level="ERROR",
        )
        sys.exit(1)


def compress(path: list[int]) -> tuple[int, ...]:
    compressed = [path[0],]
    for asn in path:
        if asn != compressed[-1]:
            compressed.append(asn)

    return tuple(compressed)


def get_all_subpaths_as_str(path: tuple[int]) -> set[str]:
    subpaths = set()
    for i in range(len(path)):
        subpath = path[i:]
        subpath_str = '|'.join(str(s) for s in subpath)
        subpaths.add(subpath_str)
    
    return subpaths


# Phase 2 worker
def process_vp_ip(args: tuple) -> set[str]:
    org, vp_id, vp_ip, yyyy, mm, dd = args
    url = build_url(org, vp_id, yyyy, mm, dd)
    if url is None:
        return set()

    log_message(f"PARSE  {org}/{vp_id}  peer={vp_ip}")
    cmd = [
        "bgpkit-parser", url,
        "--cache-dir", CACHE_DIR.as_posix(),
        "--peer-ip", vp_ip,
        "--json",

    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        log_message(
            "bgpkit-parser not found. Make sure it is installed and on PATH.",
            level="ERROR",
        )
        sys.exit(1)

    if result.returncode != 0:
        log_message(
            f"bgpkit-parser exited {result.returncode} for {url} peer={vp_ip}. "
            f"stderr: {result.stderr.strip()}",
            level="ERROR",
        )
        return set()

    paths: set[str] = set()
    output = result.stdout.strip()
    if not output:
        return paths

    for line in output.splitlines():
        elem = json.loads(line)
        path_list = elem.get("as_path", [])
        path_compressed = compress(path_list)
        all_subpaths = get_all_subpaths_as_str(path_compressed)
        paths |= all_subpaths

    return paths


def main():
    parser = argparse.ArgumentParser(description="Fetch RRC data and retain only invalid paths.")

    parser.add_argument("yyyy", metavar="YYYY")
    parser.add_argument("mm",   metavar="MM")
    parser.add_argument("dd",   metavar="DD")
    args = parser.parse_args()

    init_log_file(args.yyyy, args.mm, args.dd)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if BGPKIT_BIN is None:
        log_message("bgpkit-parser not found on PATH or in ~/.cargo/bin", level="ERROR")
        sys.exit(1)


    df = pd.read_csv('data/target_rrc_vps.csv', names=["org", "peer", "vp_ip"])
    df = df.dropna(subset=["vp_ip"])
    df = df.sample(frac=1)

    # Phase 1 tasks
    cache_tasks: list[tuple] = []
    for vp_id, group in df.groupby("peer"):
        org = group["org"].iloc[0]
        cache_tasks.append((org, vp_id, args.yyyy, args.mm, args.dd))

    # Phase 2 tasks
    parse_tasks: list[tuple] = [
        (row.org, row.peer, row.vp_ip, args.yyyy, args.mm, args.dd)
        for row in df.itertuples(index=False)
    ]

    # Phase 1: cache warm up
    log_message("Phase 1: Cache warm up")
    with Pool(processes=CACHE_WORKERS) as pool:
        # consume the iterator so we block until all downloads are done
        list(pool.imap_unordered(warm_cache, cache_tasks))

    # Phase 2: parse, one task per vp_ip
    log_message("Phase 2: extracting AS Paths")
    all_paths: set[str] = set()

    with Pool(processes=PARSE_WORKERS) as pool:
        for vp_paths in pool.imap_unordered(process_vp_ip, parse_tasks):
            all_paths |= vp_paths


    # Phase 3: cleanup and output
    invalid_paths: set[str] = set()
    with open("data/2026-03-invalid-paths.txt", "r") as f:
        for line in f:
            path = line.strip()
            invalid_paths.add(path)

    matched_paths: set[str] = set()
    for path in all_paths:
        if path in invalid_paths:
            matched_paths.add(path)
            
    # Write final output
    date_tag = f"{args.yyyy}-{args.mm}-{args.dd}"
    out_path = OUT_DIR / f"{date_tag}.txt"
    with open(out_path, "w") as f:
        for p in matched_paths:
            f.write(f"{p}\n")

    # Clear cache
    date_token = f"{args.yyyy}{args.mm}{args.dd}.{RIB_TIME}"
    for cache_path in CACHE_DIR.glob(f"*{date_token}*"):
        try:
            if cache_path.is_file() or cache_path.is_symlink():
                cache_path.unlink()
            else:
                log_message(
                    f"Skipped non-file cache entry: {cache_path}",
                    level="WARN",
                )
        except OSError as exc:
            log_message(
                f"Failed removing cache entry {cache_path}: {exc}",
                level="ERROR",
            )

    log_message("Cache cleanup complete")
    print(f"Done: {date_tag}")
    log_message("Done")


if __name__ == "__main__":
    main()
