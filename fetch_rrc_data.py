import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

BGPKIT_BIN = shutil.which("bgpkit-parser") or shutil.which(
    "bgpkit-parser", path=str(Path.home() / ".cargo/bin")
)

RIB_TIME = "0000"
OUT_DIR = Path("rrc-new/out")
LOG_DIR = Path("rrc-new/logs")
LOG_FILE: Path | None = None

NVALID_PATHS: set[str] = set()

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


def compress(path: list[int]) -> tuple[int, ...]:
    compressed = [path[0],]
    for asn in path:
        if asn != compressed[-1]:
            compressed.append(asn)

    return tuple(compressed)


def get_all_subpaths_as_str(path: tuple[int, ...]) -> set[str]:
    subpaths = set()
    for i in range(len(path)):
        subpath = path[i:]
        subpath_str = '|'.join(str(s) for s in subpath)
        subpaths.add(subpath_str)
    
    return subpaths


# Phase 2 worker
# org, vp_id, peer_ips, args.yyyy, args.mm, args.dd
def process_mrt(args: tuple) -> set[str]:
    org, vp_id, peer_ips, yyyy, mm, dd = args
    url = build_url(org, vp_id, yyyy, mm, dd)
    if url is None:
        return set()

    log_message(f"PARSE  {org}/{vp_id}  peer={vp_id}")
    cmd = ["bgpkit-parser", url, "--psv"]
    for peer_ip in peer_ips:
        cmd += ["--peer-ip", peer_ip]

    matched = set()

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as err_log:
            result = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=err_log, text=True
            )
            assert result.stdout is not None

            for line in result.stdout:
                parts = line.strip().split("|")
                # type|timestamp|peer_ip|peer_asn|prefix|as_path|origin_asns|origin|next_hop|...
                if len(parts) < 6:
                    continue

                path = compress(parts[5].split())
                for i in range(len(path) - 2):
                    subpath = path[i:]
                    subpath_str = '|'.join(str(s) for s in subpath)
                    if subpath_str in INVALID_PATHS:
                        matched.add(subpath_str)

    except FileNotFoundError:
        log_message(
            "bgpkit-parser not found. Make sure it is installed and on PATH.",
            level="ERROR",
        )
        sys.exit(1)

    return matched


def init_worker(invalid_paths: set[str], log_file: Path) -> None:
    """Sub-processes need the invalid_paths set."""
    global INVALID_PATHS, LOG_FILE
    INVALID_PATHS = invalid_paths
    LOG_FILE = log_file


def main():
    parser = argparse.ArgumentParser(description="Fetch RRC data and retain only invalid paths.")

    parser.add_argument("yyyy", metavar="YYYY")
    parser.add_argument("mm", metavar="MM")
    parser.add_argument("dd", metavar="DD")
    parser.add_argument(
        "--parse-workers",
        type=int, default=6,
        help="parallel worker processes for parsing (default: 6)"
    )
    
    args = parser.parse_args()

    init_log_file(args.yyyy, args.mm, args.dd)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if BGPKIT_BIN is None:
        log_message("bgpkit-parser not found on PATH or in ~/.cargo/bin", level="ERROR")
        sys.exit(1)

    #  LOAD INVALID PATHS
    invalid_paths: set[str] = set()
    with open("data/2026-03-invalid-paths.txt", "r") as f:
        for line in f:
            invalid_paths.add(line.strip())

    df = pd.read_csv('data/target_rrc_vps.csv', names=["org", "peer", "vp_ip"])
    df = df.dropna(subset=["vp_ip"])
    # df = df.sample(frac=1)

    tasks: list[tuple] = []
    for vp_id, group in df.groupby("peer"):
        org = group["org"].iloc[0]
        peer_ips = frozenset(group["vp_ip"].astype(str))
        tasks.append((org, vp_id, peer_ips, args.yyyy, args.mm, args.dd))

    matched_paths: set[str] = set()

    with Pool(
        processes=args.parse_workers,
        initializer=init_worker,
        initargs=(invalid_paths, LOG_FILE),
    ) as pool:
        for paths in pool.imap_unordered(process_mrt, tasks):
            matched_paths |= paths

    # Write final output
    date_tag = f"{args.yyyy}-{args.mm}-{args.dd}"
    out_path = OUT_DIR / f"{date_tag}.txt"
    with open(out_path, "w") as f:
        for p in matched_paths:
            f.write(f"{p}\n")


if __name__ == "__main__":
    main()
