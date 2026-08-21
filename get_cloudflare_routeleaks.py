import argparse
import json
import time
from pathlib import Path

import requests


def get_cloudflare_routeleaks(token):
    base_url = "https://api.cloudflare.com/client/v4/radar/bgp/leaks/events"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "dateStart": "2026-03-01T00:00:00Z",
        "dateEnd": "2026-03-04T23:59:59Z",
        "per_page": 1000,
    }
    
    all_data = []
    page = 1
    
    while True:
        params["page"] = page
        response = requests.get(base_url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if "result" in data:
            all_data.extend(data["result"]['events'])
        
        result_info = data.get("result_info", {})
        count = result_info.get("count", 0)
        total_count = result_info.get("total_count", 0)
        
        if count == 0 or len(all_data) >= total_count:
            break
        
        page += 1
        time.sleep(0.5)
    
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "cloudflare_routeleaks.json"
    
    with open(output_file, "w") as f:
        json.dump(all_data, f, indent=2)
    
    print(f"Saved {len(all_data)} records to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch Cloudflare route leak events and save them to data/cloudflare_routeleaks.json"
    )
    parser.add_argument("token", help="Cloudflare API token")
    args = parser.parse_args()

    get_cloudflare_routeleaks(args.token)
