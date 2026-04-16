# #!/usr/bin/env python3
“””
vault33 — CLI

Usage:
vault33 ingest  <file> [–vault DIR] [–key KEY] [–name NAME]
vault33 retrieve <manifest_id> [–out PATH] [–vault DIR] [–key KEY]
vault33 list    [–vault DIR]
vault33 stats   [–vault DIR]
vault33 proof   <manifest_id> [–vault DIR]
vault33 delete  <manifest_id> [–vault DIR] [–yes]
vault33 bench   [–vault DIR] [–size MB]

Examples:
vault33 ingest /data/training_set.jsonl –vault ./my_vault
vault33 ingest /data/50gb_dataset.bin –vault ./my_vault –key “my-secret-key”
vault33 retrieve MAN-ABCD1234… –out /tmp/recovered.bin –vault ./my_vault
vault33 list –vault ./my_vault
vault33 stats –vault ./my_vault
vault33 bench –size 512
“””

import sys
import os
import argparse
import json
import time
from pathlib import Path

# Add parent directory to path

sys.path.insert(0, str(Path(**file**).parent))
from vault33_production import Vault33, _fmt, _fmt_time, CHUNK_SIZE

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_key(args) -> bytes:
key = args.key or os.environ.get(“VAULT33_KEY”) or “vault33-default-dev-key-change-me!”
if key == “vault33-default-dev-key-change-me!”:
print(“⚠️  Using default key. Set –key or VAULT33_KEY env var for production.”)
return key.encode() if isinstance(key, str) else key

def _get_vault(args) -> str:
return args.vault or os.environ.get(“VAULT33_DIR”) or “./vault33_data”

def progress_bar(done, total, pct, rate, eta):
filled = int(pct / 2)
bar = “█” * filled + “░” * (50 - filled)
print(f”\r  [{bar}] {pct:5.1f}%  {_fmt(done)}/{_fmt(total)}”
f”  {rate:.1f} MB/s  ETA {_fmt_time(eta)}  “, end=””, flush=True)

# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_ingest(args):
files = args.files
vault_dir = _get_vault(args)
key = _get_key(args)

```
v = Vault33(
    vault_dir=vault_dir,
    master_key=key,
    chunk_size=args.chunk_size * 1024 * 1024 if args.chunk_size else CHUNK_SIZE,
    workers=args.workers or 4,
)

for file_path in files:
    if not Path(file_path).exists():
        print(f"❌ File not found: {file_path}")
        continue
    name = args.name if len(files) == 1 else None
    manifest_id = v.ingest_file(file_path, name=name, progress_callback=progress_bar)
    print(f"\n  Manifest ID: {manifest_id}")
    print(f"  Save this ID to retrieve your file later.\n")

v.print_stats()
```

def cmd_retrieve(args):
vault_dir = _get_vault(args)
key = _get_key(args)
v = Vault33(vault_dir=vault_dir, master_key=key)

```
out = args.out
if not out:
    # Default: use original filename in current dir
    con_path = Path(vault_dir) / "vault.db"
    import sqlite3
    con = sqlite3.connect(str(con_path))
    row = con.execute(
        "SELECT name FROM manifests WHERE manifest_id=?", (args.manifest_id,)
    ).fetchone()
    con.close()
    out = row[0] if row else "retrieved_file.bin"

v.retrieve_file(args.manifest_id, out, progress_callback=progress_bar)
```

def cmd_list(args):
vault_dir = _get_vault(args)
key = _get_key(args)
v = Vault33(vault_dir=vault_dir, master_key=key)
files = v.list_files()

```
if not files:
    print("  Vault is empty.")
    return

print(f"\n  {'NAME':<35} {'SIZE':>10} {'CHUNKS':>8} {'INGESTED':<22} {'MANIFEST ID'}")
print(f"  {'─'*35} {'─'*10} {'─'*8} {'─'*22} {'─'*38}")
for f in files:
    print(f"  {f['name'][:35]:<35} {_fmt(f['size']):>10} {f['chunks']:>8} "
          f"  {f['ingested'][:19]:<22} {f['manifest_id']}")
print(f"\n  {len(files)} file(s)")
```

def cmd_stats(args):
vault_dir = _get_vault(args)
key = _get_key(args)
v = Vault33(vault_dir=vault_dir, master_key=key)
v.print_stats()

def cmd_proof(args):
vault_dir = _get_vault(args)
key = _get_key(args)
v = Vault33(vault_dir=vault_dir, master_key=key)
proof = v.integrity_proof(args.manifest_id)
print(f”\n  INTEGRITY PROOF”)
print(f”  {‘─’*50}”)
for k, val in proof.items():
if k == “chunk_ids”: continue
print(f”  {k:<20} {val}”)
print()

def cmd_delete(args):
vault_dir = _get_vault(args)
key = _get_key(args)

```
if not args.yes:
    confirm = input(f"  Delete {args.manifest_id}? This cannot be undone. [y/N] ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

v = Vault33(vault_dir=vault_dir, master_key=key)
ok = v.delete_file(args.manifest_id)
print(f"  {'✅ Deleted' if ok else '❌ Not found'}: {args.manifest_id}")
```

def cmd_bench(args):
“”“Built-in benchmark — generates synthetic data and measures real throughput.”””
import tempfile, random, math

```
vault_dir = _get_vault(args)
key = _get_key(args)
size_mb = args.size or 256
size_bytes = size_mb * 1024 * 1024

print(f"\n  VAULT 33 BENCHMARK  ({size_mb}MB test data)")
print(f"  {'─'*50}")

datasets = [
    ("log_data",       lambda n: (b"2026-04-13T10:23:41Z INFO [app] Request processed status=200\n") * (n // 66 + 1)),
    ("jsonl_training", lambda n: (b'{"prompt":"Explain climate change.","completion":"Climate change...","score":0.92}\n') * (n // 85 + 1)),
    ("random_data",    lambda n: os.urandom(n)),
]

results = []
for name, gen_fn in datasets:
    import tempfile
    data = gen_fn(size_bytes)[:size_bytes]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tf:
        tf.write(data)
        tmp = tf.name

    v = Vault33(
        vault_dir=vault_dir + f"_bench_{name}",
        master_key=key,
        workers=4,
    )

    t0 = time.time()
    mid = v.ingest_file(tmp, name=name, progress_callback=progress_bar)
    elapsed = time.time() - t0

    s = v.stats()
    ratio = s["compression_ratio"]
    throughput = size_mb / elapsed

    print(f"\n  {name:<20} {ratio:>7.2f}x  {throughput:>7.1f} MB/s")
    results.append({"name": name, "ratio": ratio, "throughput_mbps": throughput})

    os.unlink(tmp)
    import shutil
    shutil.rmtree(vault_dir + f"_bench_{name}", ignore_errors=True)

print(f"\n  {'─'*50}")
print(f"  Best ratio:       {max(r['ratio'] for r in results):.2f}x")
print(f"  Best throughput:  {max(r['throughput_mbps'] for r in results):.1f} MB/s")
print(f"  (Random data expected ~1x — this is correct)\n")
```

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
parser = argparse.ArgumentParser(
prog=“vault33”,
description=“Vault 33 — Encrypted, deduplicated, Merkle-verified storage”,
formatter_class=argparse.RawDescriptionHelpFormatter,
epilog=**doc**,
)
parser.add_argument(”–vault”,   “-v”, help=“Vault directory (default: ./vault33_data or VAULT33_DIR env)”)
parser.add_argument(”–key”,     “-k”, help=“Master encryption key (default: VAULT33_KEY env)”)

```
sub = parser.add_subparsers(dest="command", required=True)

# ingest
p_ingest = sub.add_parser("ingest", help="Ingest one or more files")
p_ingest.add_argument("files", nargs="+", help="File(s) to ingest")
p_ingest.add_argument("--name",       help="Override artifact name (single file only)")
p_ingest.add_argument("--chunk-size", type=int, dest="chunk_size", default=None,
                       help="Chunk size in MB (default: 64)")
p_ingest.add_argument("--workers",    type=int, default=4,
                       help="Parallel chunk workers (default: 4)")

# retrieve
p_ret = sub.add_parser("retrieve", help="Retrieve a file by manifest ID")
p_ret.add_argument("manifest_id")
p_ret.add_argument("--out", "-o", help="Output file path")

# list
sub.add_parser("list", help="List all files in vault")

# stats
sub.add_parser("stats", help="Show vault statistics")

# proof
p_proof = sub.add_parser("proof", help="Generate integrity proof for a file")
p_proof.add_argument("manifest_id")

# delete
p_del = sub.add_parser("delete", help="Delete a file from vault")
p_del.add_argument("manifest_id")
p_del.add_argument("--yes", action="store_true", help="Skip confirmation")

# bench
p_bench = sub.add_parser("bench", help="Run built-in benchmark")
p_bench.add_argument("--size", type=int, default=256, help="Test data size in MB (default: 256)")

args = parser.parse_args()

dispatch = {
    "ingest":   cmd_ingest,
    "retrieve": cmd_retrieve,
    "list":     cmd_list,
    "stats":    cmd_stats,
    "proof":    cmd_proof,
    "delete":   cmd_delete,
    "bench":    cmd_bench,
}

try:
    dispatch[args.command](args)
except KeyboardInterrupt:
    print("\n\n  Interrupted.")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
```

if **name** == “**main**”:
main()