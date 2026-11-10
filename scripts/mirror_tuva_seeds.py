"""Download the Tuva public seed files to a local folder.

Tuva's DuckDB loader reads seeds straight from S3 using DuckDB's httpfs
extension. If that extension can't be installed (offline machines, locked-down
networks), mirror the files once with this script and point dbt at the mirror:

    python scripts/mirror_tuva_seeds.py data/tuva_seeds
    cd dbt && dbt build --vars '{tuva_seed_mirror: ../data/tuva_seeds}'

Uses only the Python standard library and anonymous HTTPS reads.
"""
import argparse
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BUCKET = "tuva-public-resources"
BASE = f"https://{BUCKET}.s3.amazonaws.com"

# Prefixes used by the_tuva_project 0.17.x and the demo project's seeds.
DEFAULT_PREFIXES = [
    "concept-library/1.0.1/",
    "reference-data/1.0.0/",
    "terminology/1.0.0/",
    "value-sets/1.0.0/",
    "provider-data/1.0.0/",
    "versioned_tuva_synthetic_data/0.15.0/",
    "versioned_tuva_synthetic_data/0.16.0/eligibility",
]


def list_keys(prefix):
    token = None
    while True:
        query = {"list-type": "2", "prefix": prefix}
        if token:
            query["continuation-token"] = token
        xml = urllib.request.urlopen(f"{BASE}/?{urllib.parse.urlencode(query)}").read().decode()
        yield from re.findall(r"<Key>([^<]*)</Key>.*?<Size>(\d+)</Size>", xml)
        match = re.search(r"<NextContinuationToken>([^<]*)", xml)
        if not match:
            return
        token = match.group(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dest", type=Path, help="local mirror folder, e.g. data/tuva_seeds")
    parser.add_argument("--prefix", action="append", help="S3 prefix to mirror (repeatable)")
    args = parser.parse_args()

    for prefix in args.prefix or DEFAULT_PREFIXES:
        for key, size in list_keys(prefix):
            if key.endswith("/"):
                continue
            target = args.dest / BUCKET / key
            if target.exists() and target.stat().st_size == int(size):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            print(f"{key} ({int(size) / 1e6:.1f} MB)", file=sys.stderr)
            tmp = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(f"{BASE}/{urllib.parse.quote(key)}") as resp, open(tmp, "wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
            tmp.rename(target)


if __name__ == "__main__":
    main()
