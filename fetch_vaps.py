import sys
import os
import json
import lzma
import csv
import urllib.request
from datetime import date, timedelta

OUTPUT_FILE = "data/vaps.csv"
RIRS = ["arin", "apnic", "lacnic", "afrinic", "ripencc"]


def fetch_and_parse(rir: str, year: str, month: str, day: str) -> list[dict]:
    url = f"https://ftp.ripe.net/rpki/{rir}.tal/{year}/{month}/{day}/output.json.xz"
    try:
        with urllib.request.urlopen(url) as response:
            compressed = response.read()
        decompressed = lzma.decompress(compressed)
        data = json.loads(decompressed)
        return data.get("aspas", [])
    except Exception as e:
        print(f"Warning: Could not fetch {rir} RPKI data for {year}-{month}-{day}: {e}")
        return []


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <start-date> <end-date>")
        print(f"Example: {sys.argv[0]} 2024-01-01 2024-12-31")
        sys.exit(1)

    try:
        start_date = date.fromisoformat(sys.argv[1])
        end_date = date.fromisoformat(sys.argv[2])
    except ValueError as e:
        print(f"Error: Invalid date format. Use YYYY-MM-DD. ({e})")
        sys.exit(1)

    if start_date > end_date:
        print("Error: start-date must be on or before end-date.")
        sys.exit(1)

    # Create file with header if it doesn't exist or is empty
    if not os.path.exists(OUTPUT_FILE) or os.path.getsize(OUTPUT_FILE) == 0:
        with open(OUTPUT_FILE, "w", newline="") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerow(["date", "rir", "customer", "providers"])

    with open(OUTPUT_FILE, "a", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)

        current_date = start_date

        while current_date <= end_date:
            year  = current_date.strftime("%Y")
            month = current_date.strftime("%m")
            day   = current_date.strftime("%d")
            date_str = f"{year}-{month}-{day}"

            for rir in RIRS:
                aspas = fetch_and_parse(rir, year, month, day)
                for aspa in aspas:
                    customer  = aspa.get("customer", "")
                    providers = " ".join(aspa.get("providers", []))
                    writer.writerow([date_str, rir, customer, providers])

            current_date += timedelta(days=1)

    print(f"Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
