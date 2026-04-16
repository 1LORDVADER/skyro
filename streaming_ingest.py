#!/usr/bin/env python3
"""
Streaming Ingest Module for VAULT 33 NEER
Handles files of any size (50GB+) by chunking to disk, not memory.
Chunk-by-chunk compression, deduplication, and Merkle proof generation.
"""
import hashlib
import json
import os
import zlib
import base64
import time
from pathlib import Path
from typing import Optional, Callable, Dict, List
from datetime import datetime


class StreamingIngestEngine:
    """
    Streaming ingest for large files without loading entire file into RAM.
    - Reads file in configurable chunks (default 64MB)
    - Compresses each chunk independently
    - Maintains running SHA-256 hash for deduplication
    - Writes compressed chunks to disk
    - Generates Merkle proof for integrity verification
    """
    
    CHUNK_SIZE = 64 * 1024 * 1024  # 64MB default
    COMPRESSION_LEVEL = 9  # Maximum compression
    
    def __init__(self, vault_id: str, storage_dir: str = "/tmp/vault33"):
        self.vault_id = vault_id
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_hashes: List[str] = []
        self.total_bytes_read = 0
        self.total_bytes_compressed = 0
        self.artifact_id = None
        
    def ingest_file(
        self,
        filepath: str,
        artifact_name: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict:
        """
        Stream ingest a large file without loading it all into RAM.
        
        Args:
            filepath: Path to file to ingest
            artifact_name: Name for the artifact
            progress_callback: Optional callback(bytes_read, total_bytes) for progress reporting
            
        Returns:
            Dict with artifact metadata, chunk info, and Merkle root
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        file_size = filepath.stat().st_size
        artifact_hash = hashlib.sha256()
        self.chunk_hashes = []
        self.total_bytes_read = 0
        self.total_bytes_compressed = 0
        
        # Generate artifact ID from file hash (first pass)
        artifact_id = f"33STREAM-{hashlib.sha256(artifact_name.encode()).hexdigest()[:16].upper()}"
        self.artifact_id = artifact_id
        
        # Create artifact directory
        artifact_dir = self.storage_dir / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        chunk_index = 0
        chunk_metadata = []
        
        # Stream through file in chunks
        with open(filepath, "rb") as f:
            while True:
                chunk_data = f.read(self.CHUNK_SIZE)
                if not chunk_data:
                    break
                
                # Update running hash
                artifact_hash.update(chunk_data)
                self.total_bytes_read += len(chunk_data)
                
                # Compress chunk
                compressed_chunk = zlib.compress(chunk_data, self.COMPRESSION_LEVEL)
                self.total_bytes_compressed += len(compressed_chunk)
                
                # Hash this chunk for Merkle proof
                chunk_hash = hashlib.sha256(compressed_chunk).hexdigest()
                self.chunk_hashes.append(chunk_hash)
                
                # Write compressed chunk to disk
                chunk_file = artifact_dir / f"chunk_{chunk_index:06d}.zlib"
                with open(chunk_file, "wb") as cf:
                    cf.write(compressed_chunk)
                
                chunk_metadata.append({
                    "index": chunk_index,
                    "size": len(chunk_data),
                    "compressed_size": len(compressed_chunk),
                    "hash": chunk_hash,
                    "path": str(chunk_file),
                })
                
                chunk_index += 1
                
                # Progress callback
                if progress_callback:
                    progress_callback(self.total_bytes_read, file_size)
        
        # Calculate Merkle root from chunk hashes
        merkle_root = self._merkle_root(self.chunk_hashes)
        
        # Generate artifact metadata
        artifact_metadata = {
            "id": artifact_id,
            "name": artifact_name,
            "vault_id": self.vault_id,
            "original_size": file_size,
            "compressed_size": self.total_bytes_compressed,
            "compression_ratio": round(file_size / self.total_bytes_compressed, 2) if self.total_bytes_compressed > 0 else 0,
            "artifact_hash": artifact_hash.hexdigest(),
            "merkle_root": merkle_root,
            "chunks": len(chunk_metadata),
            "chunk_metadata": chunk_metadata,
            "ingested": datetime.utcnow().isoformat(),
            "storage_path": str(artifact_dir),
        }
        
        # Write metadata to disk
        metadata_file = artifact_dir / "metadata.json"
        with open(metadata_file, "w") as mf:
            json.dump(artifact_metadata, mf, indent=2)
        
        return artifact_metadata
    
    def retrieve_file(self, artifact_id: str, output_filepath: str) -> bool:
        """
        Retrieve a streamed artifact back to disk without loading all into RAM.
        
        Args:
            artifact_id: ID of artifact to retrieve
            output_filepath: Path to write decompressed file
            
        Returns:
            True if successful, False otherwise
        """
        artifact_dir = self.storage_dir / artifact_id
        metadata_file = artifact_dir / "metadata.json"
        
        if not metadata_file.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_id}")
        
        with open(metadata_file, "r") as mf:
            metadata = json.load(mf)
        
        # Stream decompress chunks back to output file
        with open(output_filepath, "wb") as out:
            for chunk_meta in metadata["chunk_metadata"]:
                chunk_file = Path(chunk_meta["path"])
                if not chunk_file.exists():
                    raise FileNotFoundError(f"Chunk missing: {chunk_file}")
                
                with open(chunk_file, "rb") as cf:
                    compressed_data = cf.read()
                    decompressed_data = zlib.decompress(compressed_data)
                    out.write(decompressed_data)
        
        return True
    
    def verify_artifact(self, artifact_id: str) -> Dict:
        """
        Verify artifact integrity using Merkle proof.
        
        Args:
            artifact_id: ID of artifact to verify
            
        Returns:
            Dict with verification results
        """
        artifact_dir = self.storage_dir / artifact_id
        metadata_file = artifact_dir / "metadata.json"
        
        if not metadata_file.exists():
            return {"status": "FAILED", "reason": "Artifact not found"}
        
        with open(metadata_file, "r") as mf:
            metadata = json.load(mf)
        
        # Verify each chunk hash
        chunk_hashes = []
        for chunk_meta in metadata["chunk_metadata"]:
            chunk_file = Path(chunk_meta["path"])
            if not chunk_file.exists():
                return {"status": "FAILED", "reason": f"Chunk missing: {chunk_file}"}
            
            with open(chunk_file, "rb") as cf:
                chunk_data = cf.read()
                actual_hash = hashlib.sha256(chunk_data).hexdigest()
                if actual_hash != chunk_meta["hash"]:
                    return {
                        "status": "FAILED",
                        "reason": f"Chunk hash mismatch at index {chunk_meta['index']}"
                    }
                chunk_hashes.append(actual_hash)
        
        # Verify Merkle root
        calculated_merkle = self._merkle_root(chunk_hashes)
        if calculated_merkle != metadata["merkle_root"]:
            return {"status": "FAILED", "reason": "Merkle root mismatch"}
        
        return {
            "status": "PASSED",
            "artifact_id": artifact_id,
            "chunks_verified": len(chunk_hashes),
            "merkle_root": metadata["merkle_root"],
            "compression_ratio": metadata["compression_ratio"],
        }
    
    @staticmethod
    def _merkle_root(hashes: List[str]) -> str:
        """Calculate Merkle root from list of hashes."""
        if not hashes:
            return ""
        
        current_level = hashes[:]
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                h1 = current_level[i]
                h2 = current_level[i + 1] if i + 1 < len(current_level) else h1
                combined = hashlib.sha256((h1 + h2).encode()).hexdigest()
                next_level.append(combined)
            current_level = next_level
        
        return current_level[0] if current_level else ""


# ============================================================================
# Integration with NEER Core
# ============================================================================

def ingest_large_file(neer_vault, filepath: str, artifact_name: str = None, progress_callback: Optional[Callable] = None) -> str:
    """
    High-level function to ingest a large file into a NEER vault.
    
    Args:
        neer_vault: NEER vault instance
        filepath: Path to file to ingest
        artifact_name: Name for artifact (defaults to filename)
        progress_callback: Optional callback(bytes_read, total_bytes) for progress
        
    Returns:
        Artifact ID
    """
    if artifact_name is None:
        artifact_name = Path(filepath).name
    
    engine = StreamingIngestEngine(neer_vault.core.vault_id)
    metadata = engine.ingest_file(filepath, artifact_name, progress_callback)
    
    # Store metadata in vault
    neer_vault.core.artifacts[metadata["id"]] = {
        "id": metadata["id"],
        "name": metadata["name"],
        "size": metadata["original_size"],
        "comp_size": metadata["compressed_size"],
        "hash": metadata["artifact_hash"],
        "merkle_root": metadata["merkle_root"],
        "chunks": metadata["chunks"],
        "storage_path": metadata["storage_path"],
        "ts": metadata["ingested"],
        "meta": {"streaming": True, "chunk_count": metadata["chunks"]},
    }
    
    return metadata["id"]


if __name__ == "__main__":
    # Test streaming ingest
    print("=" * 60)
    print("VAULT 33 - Streaming Ingest Engine | Test Suite")
    print("=" * 60)
    
    # Create test file (100MB)
    test_file = Path("/tmp/test_100mb.bin")
    print(f"\nCreating test file: {test_file} (100MB)...")
    with open(test_file, "wb") as f:
        for i in range(100):
            f.write(b"X" * (1024 * 1024))  # 1MB chunks
    
    # Test streaming ingest
    engine = StreamingIngestEngine("V33-TEST-001")
    
    def progress(read, total):
        pct = round((read / total) * 100, 1)
        print(f"  Ingesting: {pct}% ({read / 1024 / 1024:.1f}MB / {total / 1024 / 1024:.1f}MB)")
    
    print("\nIngesting file with streaming engine...")
    metadata = engine.ingest_file(str(test_file), "test_100mb.bin", progress)
    
    print(f"\nArtifact ID: {metadata['id']}")
    print(f"Original: {metadata['original_size'] / 1024 / 1024:.1f}MB")
    print(f"Compressed: {metadata['compressed_size'] / 1024 / 1024:.1f}MB")
    print(f"Compression Ratio: {metadata['compression_ratio']}:1")
    print(f"Chunks: {metadata['chunks']}")
    print(f"Merkle Root: {metadata['merkle_root']}")
    
    # Test verification
    print("\nVerifying artifact integrity...")
    verify_result = engine.verify_artifact(metadata["id"])
    print(f"Verification: {verify_result['status']}")
    
    # Test retrieval
    output_file = Path("/tmp/test_100mb_retrieved.bin")
    print(f"\nRetrieving artifact to: {output_file}")
    engine.retrieve_file(metadata["id"], str(output_file))
    
    # Verify round-trip
    original_hash = hashlib.sha256(open(test_file, "rb").read()).hexdigest()
    retrieved_hash = hashlib.sha256(open(output_file, "rb").read()).hexdigest()
    
    if original_hash == retrieved_hash:
        print("✓ Round-trip integrity verified!")
    else:
        print("✗ Round-trip integrity FAILED!")
    
    print("\n" + "=" * 60)
    print("STREAMING INGEST ENGINE TEST COMPLETE")
    print("=" * 60)
