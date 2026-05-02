import argparse
import io
from multiprocessing import Pool, cpu_count
import pandas as pd
import tempfile
import os


def compress(path_str: str) -> str:
    parts = path_str.split('|')
    res = [parts[0],]
    for asn in parts:
        if asn != res[-1]:
            res.append(asn)
    return '|'.join(res)


def load_invalid_paths(filepath: str) -> frozenset:
    with open(filepath, 'r') as f:
        paths = frozenset(line.strip() for line in f)
    return paths


# UNIX child processes inherit it, on Windows (spawn), we have to load it
_INVALID_PATHS: frozenset | None = None
_INVALID_PATH_FILE: str = ''


def _worker_init(invalid_path_file: str) -> None:
    """For Windows-spawned processes."""
    global _INVALID_PATHS, _INVALID_PATH_FILE
    _INVALID_PATH_FILE = invalid_path_file
    if _INVALID_PATHS is None:
        _INVALID_PATHS = load_invalid_paths(invalid_path_file)


def _filter_chunk(chunk: bytes) -> bytes:
    """
    Filter a raw bytes chunk (whole lines only) and return matching lines.
    Runs inside a worker process.
    """
    out = io.BytesIO()
    for raw_line in chunk.splitlines(keepends=True):
        line = raw_line.decode('utf-8', errors='replace')
        cols = line.split(' ', 2)
        if len(cols) < 2:
            continue
        path_str = cols[1]
        if _INVALID_PATHS is not None and compress(path_str) in _INVALID_PATHS:
            out.write(raw_line)
    return out.getvalue()


def iter_chunks(filepath: str, chunk_size: int):
    """
    Yield chunks of `chunk_size` bytes that always end on a newline boundary.
    This lets workers process chunks containing only entire lines.
    """
    with open(filepath, 'rb', buffering=1 << 23) as fh:
        leftover = b''
        while True:
            raw = fh.read(chunk_size)
            if not raw:
                if leftover:
                    yield leftover
                break
            raw = leftover + raw
            cut = raw.rfind(b'\n') + 1
            if cut == 0:
                leftover = raw
            else:
                leftover = raw[cut:]
                yield raw[:cut]


def run(workers: int) -> None:

    paths_file = 'data/caida/2026-03-paths-detailed.txt'
    invalid_file = 'data/2026-03-invalid-paths.txt'
    output_csv = 'data/target_rrc_vps.csv'
    chunk_size = 64 * 1024 * 1024

    global _INVALID_PATHS
    _INVALID_PATHS = load_invalid_paths(invalid_file)

    print("Processing...")

    # Write filtered results to a temporary file
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt') as tmp:
        tmp_path = tmp.name
        with Pool(processes=workers,
                    initializer=_worker_init,
                    initargs=(invalid_file,)) as pool:
            for result in pool.imap(_filter_chunk,
                                    iter_chunks(paths_file, chunk_size),
                                    chunksize=1):
                if result:
                    tmp.write(result)

    try:
        def extract_vp_info(dataf):
            dataf['peer_org'] = dataf['peer|obs'].apply(lambda s: s.split('|')[0])
            dataf['org'] = dataf['peer_org'].apply(lambda s: s.split('/')[0])
            dataf['peer'] = dataf['peer_org'].apply(lambda s: s.split('/')[1])
            dataf.drop('peer|obs', axis=1, inplace=True)
            dataf.drop('peer_org', axis=1, inplace=True)
            return dataf

        (
            pd
                .read_csv(tmp_path, sep=' ', names=['peer|obs', 'path', 'prefix', 'code', 'vp_ip'])
                .pipe(extract_vp_info)
                [['org', 'peer', 'vp_ip']]
                .drop_duplicates()
                .to_csv(output_csv, index=False, header=False)
        )

        print(f"Done. Results saved to {output_csv}")
    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="Extract vantage point information for invalid paths.")
    parser.add_argument('--workers', required=False, type=int, default=max(1, cpu_count()), help='parallel worker processes (default: all CPUs)')

    args = parser.parse_args()

    run(args.workers)


if __name__ == '__main__':
    main()
