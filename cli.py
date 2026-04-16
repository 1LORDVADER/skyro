#!/usr/bin/env python3
"""
VAULT 33 CLI - Command-line interface for NEER ingestion and management.
Usage: vault33 ingest <file> [--name <name>] [--vault <vault_id>]
"""
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
from streaming_ingest import StreamingIngestEngine


class ProgressBar:
    """Simple terminal progress bar."""
    
    def __init__(self, total: int, width: int = 50):
        self.total = total
        self.width = width
        self.current = 0
    
    def update(self, current: int, *args):
        self.current = current
        pct = (current / self.total) * 100
        filled = int((current / self.total) * self.width)
        bar = "█" * filled + "░" * (self.width - filled)
        
        mb_current = current / 1024 / 1024
        mb_total = self.total / 1024 / 1024
        
        sys.stdout.write(f"\r[{bar}] {pct:.1f}% ({mb_current:.1f}MB / {mb_total:.1f}MB)")
        sys.stdout.flush()
    
    def finish(self):
        self.update(self.total)
        print()


def cmd_ingest(args):
    """Handle 'vault33 ingest' command."""
    filepath = Path(args.file)
    
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        return 1
    
    if not filepath.is_file():
        print(f"Error: Not a file: {filepath}")
        return 1
    
    artifact_name = args.name or filepath.name
    vault_id = args.vault or f"V33-CLI-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    storage_dir = args.storage or os.path.expanduser("~/.vault33/storage")
    
    print(f"\n{'=' * 60}")
    print(f"VAULT 33 - Streaming Ingest")
    print(f"{'=' * 60}")
    print(f"File: {filepath}")
    print(f"Size: {filepath.stat().st_size / 1024 / 1024:.1f}MB")
    print(f"Artifact Name: {artifact_name}")
    print(f"Vault ID: {vault_id}")
    print(f"Storage: {storage_dir}")
    print(f"{'=' * 60}\n")
    
    engine = StreamingIngestEngine(vault_id, storage_dir)
    file_size = filepath.stat().st_size
    progress_bar = ProgressBar(file_size)
    
    try:
        metadata = engine.ingest_file(str(filepath), artifact_name, progress_bar.update)
        progress_bar.finish()
        
        print(f"\n{'=' * 60}")
        print(f"✓ Ingest Complete")
        print(f"{'=' * 60}")
        print(f"Artifact ID: {metadata['id']}")
        print(f"Original Size: {metadata['original_size'] / 1024 / 1024:.1f}MB")
        print(f"Compressed Size: {metadata['compressed_size'] / 1024 / 1024:.1f}MB")
        print(f"Compression Ratio: {metadata['compression_ratio']}:1")
        print(f"Chunks: {metadata['chunks']}")
        print(f"Merkle Root: {metadata['merkle_root']}")
        print(f"Storage Path: {metadata['storage_path']}")
        print(f"{'=' * 60}\n")
        
        return 0
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return 1


def cmd_retrieve(args):
    """Handle 'vault33 retrieve' command."""
    artifact_id = args.artifact_id
    output_path = Path(args.output)
    storage_dir = args.storage or os.path.expanduser("~/.vault33/storage")
    
    print(f"\n{'=' * 60}")
    print(f"VAULT 33 - Retrieve Artifact")
    print(f"{'=' * 60}")
    print(f"Artifact ID: {artifact_id}")
    print(f"Output: {output_path}")
    print(f"Storage: {storage_dir}")
    print(f"{'=' * 60}\n")
    
    engine = StreamingIngestEngine("V33-CLI", storage_dir)
    
    try:
        engine.retrieve_file(artifact_id, str(output_path))
        print(f"✓ Artifact retrieved to: {output_path}")
        return 0
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1


def cmd_verify(args):
    """Handle 'vault33 verify' command."""
    artifact_id = args.artifact_id
    storage_dir = args.storage or os.path.expanduser("~/.vault33/storage")
    
    print(f"\n{'=' * 60}")
    print(f"VAULT 33 - Verify Artifact")
    print(f"{'=' * 60}")
    print(f"Artifact ID: {artifact_id}")
    print(f"Storage: {storage_dir}")
    print(f"{'=' * 60}\n")
    
    engine = StreamingIngestEngine("V33-CLI", storage_dir)
    
    try:
        result = engine.verify_artifact(artifact_id)
        
        if result["status"] == "PASSED":
            print(f"✓ Verification PASSED")
            print(f"  Chunks Verified: {result['chunks_verified']}")
            print(f"  Merkle Root: {result['merkle_root']}")
            print(f"  Compression Ratio: {result['compression_ratio']}:1")
            return 0
        else:
            print(f"✗ Verification FAILED")
            print(f"  Reason: {result['reason']}")
            return 1
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1


def cmd_list(args):
    """Handle 'vault33 list' command."""
    storage_dir = Path(args.storage or os.path.expanduser("~/.vault33/storage"))
    
    print(f"\n{'=' * 60}")
    print(f"VAULT 33 - List Artifacts")
    print(f"{'=' * 60}\n")
    
    if not storage_dir.exists():
        print("No artifacts found.")
        return 0
    
    artifacts = []
    for artifact_dir in storage_dir.iterdir():
        if artifact_dir.is_dir():
            metadata_file = artifact_dir / "metadata.json"
            if metadata_file.exists():
                import json
                with open(metadata_file, "r") as f:
                    metadata = json.load(f)
                    artifacts.append(metadata)
    
    if not artifacts:
        print("No artifacts found.")
        return 0
    
    print(f"{'ID':<20} {'Name':<30} {'Size':<15} {'Ratio':<10}")
    print("-" * 75)
    
    for a in artifacts:
        size_mb = a["original_size"] / 1024 / 1024
        ratio = f"{a['compression_ratio']}:1"
        print(f"{a['id']:<20} {a['name']:<30} {size_mb:>6.1f}MB {ratio:>10}")
    
    print(f"\nTotal artifacts: {len(artifacts)}")
    print(f"{'=' * 60}\n")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="vault33",
        description="VAULT 33 - Streaming compression and storage engine",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a file")
    ingest_parser.add_argument("file", help="File to ingest")
    ingest_parser.add_argument("--name", help="Artifact name (defaults to filename)")
    ingest_parser.add_argument("--vault", help="Vault ID (auto-generated if not provided)")
    ingest_parser.add_argument("--storage", help="Storage directory (default: ~/.vault33/storage)")
    ingest_parser.set_defaults(func=cmd_ingest)
    
    # retrieve command
    retrieve_parser = subparsers.add_parser("retrieve", help="Retrieve an artifact")
    retrieve_parser.add_argument("artifact_id", help="Artifact ID to retrieve")
    retrieve_parser.add_argument("output", help="Output file path")
    retrieve_parser.add_argument("--storage", help="Storage directory (default: ~/.vault33/storage)")
    retrieve_parser.set_defaults(func=cmd_retrieve)
    
    # verify command
    verify_parser = subparsers.add_parser("verify", help="Verify artifact integrity")
    verify_parser.add_argument("artifact_id", help="Artifact ID to verify")
    verify_parser.add_argument("--storage", help="Storage directory (default: ~/.vault33/storage)")
    verify_parser.set_defaults(func=cmd_verify)
    
    # list command
    list_parser = subparsers.add_parser("list", help="List all artifacts")
    list_parser.add_argument("--storage", help="Storage directory (default: ~/.vault33/storage)")
    list_parser.set_defaults(func=cmd_list)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
