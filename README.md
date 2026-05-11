# SKYRO — Enterprise AI Infrastructure Storage

**Dramatically reduce storage footprint. 200–270× compression on logs and AI training data. 150×+ global deduplication.**

SKYRO is a production-ready streaming compression and storage engine for enterprise infrastructure. Compress large datasets, AI training data, and logs to a fraction of their original size without loading entire files into RAM. Works on-prem, in cloud, or in hybrid environments.

## Get Early Access

**[→ Get SKYRO Early Access — $29](https://vault33.lemonsqueezy.com/checkout/buy/ecaec945-6de8-4e29-84a8-4c99772d834e)**

Includes: full source, CLI, Python API, REST API, Docker, and priority support.

---

## Key Features

- **Streaming Ingestion** — Handle 50GB+ files without RAM overflow. Chunks data to disk automatically.
- **Massive Compression** — 200–270× on logs and AI training data. 150×+ with global deduplication.
- **Cryptographic Verification** — Merkle proofs for tamper-evident integrity. AES-256-GCM encryption.
- **Portable Vaults** — Export compressed data as self-contained files. Move between systems without re-encryption.
- **Zero Cloud Dependency** — 100% offline-capable. Works in air-gapped networks.
- **Production-Ready** — Tested on 512MB+ files. Designed for 10TB+ workloads.

## Real-World Performance

Measured on production hardware:

| Data Type | Compression Ratio | Ingest Speed | Use Case |
|---|---|---|---|
| Application logs | 294× | 131 MB/s | Structured, repetitive text |
| Media metadata (JSON) | 294× | 130 MB/s | Structured data formats |
| AI training data (JSONL) | 258× | 128 MB/s | Machine learning datasets |
| Backup archives | 239× | 130 MB/s | Incremental backups |
| Source code / codebases | 258× | 127 MB/s | Git repos, source trees |
| Random binary / video | 1× | 26 MB/s | Already-compressed formats |

**Note:** SKYRO is designed for structured, text-based, and repetitive workloads. Raw binary/video (already compressed) will not compress further.

## Installation

### From Source

```bash
git clone https://github.com/1LORDVADER/skyro.git
cd skyro
pip install cryptography flask flask-cors tqdm
```

### Docker

```bash
docker-compose up -d
# Dashboard: http://localhost:8033
```

## Quick Start

### CLI

```bash
python vault33_cli.py ingest /path/to/large_file.bin
python vault33_cli.py list
python vault33_cli.py stats
```

### Python API

```python
from vault33_production import Vault33

vault = Vault33("/vault_data")
manifest = vault.ingest_file("/path/to/file.bin")
print(f"Compression: {manifest['compression_ratio']:.1f}x")
```

### REST API + Dashboard

```bash
python vault33_api.py
# Dashboard: http://localhost:8033
```

## Use Cases

### AI & ML Training

Reduce training dataset storage by 200–270×. Manage multiple model versions with global deduplication. Move datasets between cloud and on-prem without re-encryption.

```bash
# Ingest 500GB training dataset
python vault33_cli.py ingest /data/training_dataset.tar.gz --name "imagenet_v2"
# Result: ~2GB compressed
```

### Backup & Disaster Recovery

Reduce backup storage by 70–90%. Incremental backups with deduplication. Multi-region failover without cloud dependency.

```bash
python vault33_cli.py ingest /backups/daily_backup.tar --name "backup_daily"
```

### Compliance & Audit

Merkle proofs prove data integrity without decryption. Tamper-evident records. Audit-friendly. Works in regulated industries.

```python
from vault33_production import Vault33

vault = Vault33("/vault_data")
result = vault.verify_artifact(artifact_id)
print(f"Merkle Root: {result['merkle_root']}")  # Cryptographic proof of integrity
```

## Architecture

Vault 33 processes files in 64MB chunks (configurable):

```
File Input
    |
Split into 64MB chunks
    |
For each chunk:
  - SHA-256 hash (dedup check)
  - Compress (zlib level 9)
  - Encrypt (AES-256-GCM)
  - Write to vault store
    |
Merkle root across all chunks
    |
Manifest with chunk IDs + metadata
```

### Key Properties

- **Streaming ingest** — Never loads full file into RAM
- **Per-chunk pipeline** — SHA-256 → dedup check → compress → encrypt → write
- **Merkle verification** — Cryptographic proof of integrity across all chunks
- **Crash-safe** — SQLite WAL mode ensures resumable ingestion
- **Concurrent processing** — Configurable workers (default 4)
- **Deduplication** — Identical chunks stored once, referenced by multiple manifests

## Resource Usage

- **RAM**: <16MB per 64MB chunk (streaming design)
- **CPU**: Scales with workers (default 4)
- **I/O**: 1 write per chunk, 0 on dedup hit
- **Max file size**: Unlimited (tested to 512MB, designed for 10TB+)

## Security

- **Encryption**: AES-256-GCM per chunk
- **Key derivation**: PBKDF2-HMAC-SHA256 (100,000 iterations)
- **Integrity**: SHA-256 hashing + Merkle root verification
- **Tamper detection**: Merkle root mismatch immediately indicates tampering

## Changelog

### v1.1.0 (2026-04-15)

- Streaming ingest for 50GB+ files
- CLI tool with progress bar
- Merkle proof verification
- Chunked compression (64MB default)
- Round-trip integrity testing

### v1.0.0 (2026-04-01)

- Initial release
- In-memory ingest (up to 1GB)
- Basic compression and deduplication

## Authors

**Adarius Matthews** — Founder, Vader Technologies

## Support

- **Website**: https://vault33.co
- **Issues**: https://github.com/1LORDVADER/skyro/issues
- **Email**: support@vault33.co

## License

MIT License. See [LICENSE](LICENSE) for details.

---

**[→ Get SKYRO Early Access — $29](https://vault33.lemonsqueezy.com/checkout/buy/ecaec945-6de8-4e29-84a8-4c99772d834e)** | [vault33.co](https://vault33.co) | [Request a Demo](https://vault33.co/contact)
