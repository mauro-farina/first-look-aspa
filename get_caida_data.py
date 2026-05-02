import argparse
import bz2
import shutil
import tempfile
import requests

from pathlib import Path


BASE_URL = "https://publicdata.caida.org/datasets/as-relationships/serial-1/20260301"
OUT_DIR = Path("data/caida")

# Original file name --> local file name
REL_FILES = {
    "as-rel.txt.bz2": "2026-03-as-rel-v4.txt",
    "as-rel.v6-stable.txt.bz2": "2026-03-as-rel-v6.txt",
}

CONE_FILES = {
    "ppdc-ases.txt.bz2": "2026-03-cones.txt",
}

PATHS_FILES = {
    "all-paths.bz2": "2026-03-paths-detailed.txt",
}


def process_paths_file():
    input_file = OUT_DIR / "2026-03-paths-detailed.txt"
    output_file = OUT_DIR / "2026-03-paths.txt"

    print(f"Extracting unique AS Paths into {output_file}...")

    with open(input_file, "r") as f:
        values = set(
            line.strip().split(" ")[1]
            for line in f
            if len(line.split(" ")) > 1
        )

    with open(output_file, "w") as f:
        for v in values:
            f.write(v + "\n")


def download_and_unbz2(url: str, out_path: Path):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bz2", dir=out_path.parent) as f:
        tmp_path = Path(f.name)
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)

    with bz2.open(tmp_path, "rb") as fin, open(out_path, "wb") as fout:
        shutil.copyfileobj(fin, fout)

    tmp_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Download CAIDA AS-relationship datasets")

    parser.add_argument(
        "--rel", action="store_true",
        help="Download and extract AS relationship files (v4 and v6)",
    )
    parser.add_argument(
        "--cone", action="store_true",
        help="Download and extract customer cone (ppdc-ases) file",
    )
    parser.add_argument(
        "--paths", action="store_true",
        help="Download, extract, and process all-paths file",
    )

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    selected = {}
    if args.rel:
        selected |= REL_FILES
    if args.cone:
        selected |= CONE_FILES
    if args.paths:
        selected |= PATHS_FILES

    for remote_fname, local_fname in selected.items():
        url = f"{BASE_URL}.{remote_fname}"
        out_path = OUT_DIR / local_fname

        print(f"Downloading and extracting {remote_fname} to {out_path}...")
        download_and_unbz2(url, out_path)

    if args.paths:
        process_paths_file()

    print("Done.")


if __name__ == "__main__":
    main()