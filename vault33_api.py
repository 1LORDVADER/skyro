"""
Vault 33 - REST API + Dashboard Server

Endpoints:
GET  /health                          - Health check
GET  /api/stats                       - Vault statistics
GET  /api/files                       - List all files
POST /api/ingest                      - Ingest a file (multipart upload)
GET  /api/retrieve/<manifest_id>      - Download a file
GET  /api/proof/<manifest_id>         - Integrity proof (real Merkle verification)
DELETE /api/files/<manifest_id>       - Delete a file (full cleanup: chunks + DB)
GET  /                                - Web dashboard

Authentication:
Set VAULT33_API_KEY env var to require X-API-Key header on all API calls.
If not set, the API is open (suitable for local/trusted networks only).
"""

import io
import os
import sys
import json
import tempfile
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from flask import Flask, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent))
from vault33_production import Vault33, _fmt, _merkle_root, VERSION

# Config
PORT = int(os.environ.get("VAULT33_PORT", 8033))
VAULT_DIR = os.environ.get("VAULT33_DIR", "/tmp/vault33")
MASTER_KEY = os.environ.get("VAULT33_KEY", None)
API_KEY = os.environ.get("VAULT33_API_KEY", None)  # Optional API key for authentication

if MASTER_KEY:
    MASTER_KEY = MASTER_KEY.encode()

app = Flask(__name__)
CORS(app)

# Initialize vault
vault = Vault33(VAULT_DIR, master_key=MASTER_KEY)


# ── Authentication middleware ──────────────────────────────────────────────────
@app.before_request
def require_api_key():
    """Require X-API-Key header on all /api/* routes if VAULT33_API_KEY is set."""
    if not API_KEY:
        return  # No key configured — open access (local/trusted network only)
    if request.path in ("/", "/health"):
        return  # Dashboard and health check are always public
    if request.path.startswith("/api/"):
        provided = request.headers.get("X-API-Key") or request.args.get("api_key")
        if provided != API_KEY:
            return jsonify({"error": "Unauthorized — provide X-API-Key header"}), 401


# Dashboard HTML
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vault 33 - Production Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Monaco', 'Menlo', monospace; background: #0a0a0a; color: #e0e0e0; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #fff; margin-bottom: 30px; font-size: 28px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 40px; }
.stat-box { background: #1a1a1a; border: 1px solid #333; padding: 20px; border-radius: 4px; }
.stat-label { color: #888; font-size: 12px; text-transform: uppercase; margin-bottom: 8px; }
.stat-value { color: #0f0; font-size: 24px; font-weight: bold; }
.upload-section { background: #1a1a1a; border: 1px solid #333; padding: 30px; border-radius: 4px; margin-bottom: 40px; }
.upload-label { color: #fff; font-size: 14px; margin-bottom: 15px; display: block; }
.upload-input { display: block; margin-bottom: 15px; padding: 10px; background: #0a0a0a; border: 1px solid #333; color: #e0e0e0; width: 100%; }
.upload-btn { background: #0f0; color: #000; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold; border-radius: 2px; }
.upload-btn:hover { background: #0c0; }
.progress { margin-top: 15px; display: none; }
.progress-bar { background: #333; height: 4px; border-radius: 2px; overflow: hidden; }
.progress-fill { background: #0f0; height: 100%; width: 0%; transition: width 0.1s; }
.files-section { background: #1a1a1a; border: 1px solid #333; padding: 20px; border-radius: 4px; }
.files-title { color: #fff; margin-bottom: 20px; font-size: 16px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px; border-bottom: 1px solid #333; color: #888; font-size: 12px; text-transform: uppercase; }
td { padding: 10px; border-bottom: 1px solid #222; }
tr:hover { background: #0f0f0f; }
.log { background: #0a0a0a; border: 1px solid #333; padding: 15px; border-radius: 4px; margin-top: 20px; max-height: 300px; overflow-y: auto; font-size: 11px; }
.log-entry { margin-bottom: 5px; }
.log-info { color: #0f0; }
.log-error { color: #f00; }
.log-warn { color: #ff0; }
</style>
</head>
<body>
<div class="container">
<h1>Vault 33 - Production Dashboard</h1>

<div class="stats">
<div class="stat-box">
<div class="stat-label">Total Files</div>
<div class="stat-value" id="stat-files">0</div>
</div>
<div class="stat-box">
<div class="stat-label">Original Size</div>
<div class="stat-value" id="stat-original">0 B</div>
</div>
<div class="stat-box">
<div class="stat-label">Compressed Size</div>
<div class="stat-value" id="stat-compressed">0 B</div>
</div>
<div class="stat-box">
<div class="stat-label">Compression Ratio</div>
<div class="stat-value" id="stat-ratio">0x</div>
</div>
</div>

<div class="upload-section">
<label class="upload-label">Upload File</label>
<input type="file" id="file-input" class="upload-input">
<button class="upload-btn" onclick="uploadFile()">Ingest File</button>
<div class="progress" id="progress">
<div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
<div id="progress-text" style="margin-top: 5px; font-size: 12px; color: #888;"></div>
</div>
</div>

<div class="files-section">
<div class="files-title">Ingested Files</div>
<table>
<thead>
<tr>
<th>Name</th>
<th>Original</th>
<th>Compressed</th>
<th>Ratio</th>
<th>Created</th>
<th>Actions</th>
</tr>
</thead>
<tbody id="files-table">
<tr><td colspan="6" style="text-align: center; color: #666; padding: 20px;">No files yet</td></tr>
</tbody>
</table>
</div>

<div class="log" id="log"></div>
</div>

<script>
function log(msg, type = 'info') {
  const logEl = document.getElementById('log');
  const entry = document.createElement('div');
  entry.className = 'log-entry log-' + type;
  const ts = new Date().toLocaleTimeString();
  entry.textContent = '[' + ts + '] ' + msg;
  logEl.appendChild(entry);
  logEl.scrollTop = logEl.scrollHeight;
}

function formatBytes(b) {
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = b;
  for (let u of units) {
    if (size < 1024) return size.toFixed(1) + u;
    size /= 1024;
  }
  return size.toFixed(1) + 'TB';
}

function updateStats() {
  fetch('/api/stats')
    .then(r => r.json())
    .then(d => {
      document.getElementById('stat-files').textContent = d.total_files;
      document.getElementById('stat-original').textContent = formatBytes(d.total_original_size);
      document.getElementById('stat-compressed').textContent = formatBytes(d.total_compressed_size);
      document.getElementById('stat-ratio').textContent = d.overall_compression_ratio.toFixed(1) + 'x';
    });
}

function updateFiles() {
  fetch('/api/files')
    .then(r => r.json())
    .then(files => {
      const tb = document.getElementById('files-table');
      if (!files.length) {
        tb.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #666; padding: 20px;">No files yet</td></tr>';
        return;
      }
      tb.innerHTML = files.map(f => `
        <tr>
        <td>${f.original_name}</td>
        <td>${formatBytes(f.original_size)}</td>
        <td>${formatBytes(f.compressed_size)}</td>
        <td>${f.compression_ratio.toFixed(1)}x</td>
        <td>${f.created_at.split('T')[0]}</td>
        <td>
          <a href="/api/retrieve/${f.manifest_id}" style="color:#0f0;margin-right:10px;">Download</a>
          <a href="#" onclick="deleteFile('${f.manifest_id}')" style="color:#f44;">Delete</a>
        </td>
        </tr>
      `).join('');
    });
}

function deleteFile(manifestId) {
  if (!confirm('Delete this file? This cannot be undone.')) return;
  fetch('/api/files/' + manifestId, { method: 'DELETE' })
    .then(r => r.json())
    .then(d => {
      log('Deleted: ' + manifestId, 'warn');
      updateStats();
      updateFiles();
    })
    .catch(e => log('Delete error: ' + e.message, 'error'));
}

function uploadFile() {
  const input = document.getElementById('file-input');
  if (!input.files.length) {
    log('No file selected', 'warn');
    return;
  }
  
  const file = input.files[0];
  const formData = new FormData();
  formData.append('file', file);
  
  log('Ingesting ' + file.name + '...', 'info');
  document.getElementById('progress').style.display = 'block';
  
  fetch('/api/ingest', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(d => {
      log('Ingested: ' + d.original_name + ' (' + d.compression_ratio.toFixed(1) + 'x compression)', 'info');
      input.value = '';
      document.getElementById('progress').style.display = 'none';
      updateStats();
      updateFiles();
    })
    .catch(e => {
      log('Error: ' + e.message, 'error');
      document.getElementById('progress').style.display = 'none';
    });
}

log('Vault 33 production dashboard connected', 'info');
updateStats();
updateFiles();
setInterval(updateStats, 5000);
setInterval(updateFiles, 5000);
</script>
</body>
</html>"""

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    return Response(DASHBOARD_HTML, mimetype="text/html")


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': VERSION})


@app.route('/api/stats')
def api_stats():
    # FIX BUG-02: was vault.get_stats() — method is named get_stats() in Vault33
    stats = vault.get_stats()
    return jsonify(stats)


@app.route('/api/files')
def api_files():
    """List all ingested files. Reads from SQLite via vault.get_stats() for consistency."""
    import sqlite3
    db_path = Path(VAULT_DIR) / "vault.db"
    if not db_path.exists():
        return jsonify([])
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # FIX GAP-03: use DB fields which match vault33_production.py schema exactly
    c.execute('''SELECT manifest_id, original_name, original_size, compressed_size,
                        compression_ratio, created_at
                 FROM manifests ORDER BY created_at DESC''')
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/ingest', methods=['POST'])
def api_ingest():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name
    
    try:
        manifest = vault.ingest_file(tmp_path)
        return jsonify(manifest)
    finally:
        os.unlink(tmp_path)


@app.route('/api/retrieve/<manifest_id>')
def api_retrieve(manifest_id):
    try:
        data = vault.retrieve_file(manifest_id)
        # FIX BUG-01: io was not imported — added at top of file
        manifest_path = Path(VAULT_DIR) / "manifests" / f"{manifest_id}.json"
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=manifest['original_name']
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 404


@app.route('/api/proof/<manifest_id>')
def api_proof(manifest_id):
    """
    FIX SEC-02: Previously returned verified=True unconditionally.
    Now performs real Merkle root verification against stored manifest.
    """
    try:
        manifest_path = Path(VAULT_DIR) / "manifests" / f"{manifest_id}.json"
        if not manifest_path.exists():
            return jsonify({'error': 'Manifest not found'}), 404

        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        stored_root = manifest.get('merkle_root', '')
        chunk_hashes = []

        # Re-read each chunk from disk and hash it to verify integrity
        import hashlib
        for chunk_id in manifest.get('chunk_ids', []):
            chunk_path = Path(VAULT_DIR) / "chunks" / chunk_id[:2] / f"{chunk_id}.bin"
            if not chunk_path.exists():
                return jsonify({
                    'manifest_id': manifest_id,
                    'verified': False,
                    'error': f'Missing chunk: {chunk_id[:8]}...',
                    'merkle_root': stored_root,
                    'chunk_count': manifest.get('chunk_count', 0),
                }), 200
            with open(chunk_path, 'rb') as cf:
                chunk_data = cf.read()
            chunk_hashes.append(hashlib.sha256(chunk_data).hexdigest())

        computed_root = _merkle_root(chunk_hashes)
        verified = computed_root == stored_root

        return jsonify({
            'manifest_id': manifest_id,
            'merkle_root': stored_root,
            'computed_root': computed_root,
            'chunk_count': manifest.get('chunk_count', 0),
            'verified': verified,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/files/<manifest_id>', methods=['DELETE'])
def api_delete(manifest_id):
    """
    FIX SEC-03: Previously only deleted manifest JSON, leaving chunks and DB rows.
    Now: decrements chunk ref_counts, deletes orphaned chunks from disk + DB,
    removes manifest row from DB, and removes manifest JSON file.
    """
    import sqlite3
    try:
        manifest_path = Path(VAULT_DIR) / "manifests" / f"{manifest_id}.json"
        if not manifest_path.exists():
            return jsonify({'error': 'Not found'}), 404

        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        chunk_ids = manifest.get('chunk_ids', [])
        db_path = Path(VAULT_DIR) / "vault.db"
        chunks_deleted = 0

        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()

            # Remove manifest row
            c.execute('DELETE FROM manifests WHERE manifest_id = ?', (manifest_id,))

            # For each chunk, check if any other manifest still references it
            for chunk_id in chunk_ids:
                # Count remaining manifests that reference this chunk_id
                c.execute('SELECT chunk_ids FROM manifests')
                still_referenced = any(
                    chunk_id in json.loads(row[0])
                    for row in c.fetchall()
                    if row[0]
                )
                if not still_referenced:
                    # Safe to delete chunk from disk and DB
                    chunk_path = Path(VAULT_DIR) / "chunks" / chunk_id[:2] / f"{chunk_id}.bin"
                    if chunk_path.exists():
                        chunk_path.unlink()
                        chunks_deleted += 1
                    # Remove from chunks table (keyed by chunk_hash — look up by chunk_id)
                    c.execute('DELETE FROM chunks WHERE chunk_id = ?', (chunk_id,))

            conn.commit()
            conn.close()

        # Remove manifest JSON
        manifest_path.unlink()

        return jsonify({
            'status': 'deleted',
            'manifest_id': manifest_id,
            'chunks_deleted': chunks_deleted,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print(f"Vault 33 v2 - REST API + Dashboard")
    print(f"Vault directory: {VAULT_DIR}")
    print(f"API auth: {'ENABLED (X-API-Key required)' if API_KEY else 'DISABLED (set VAULT33_API_KEY to enable)'}")
    print(f"Dashboard: http://localhost:{PORT}")
    print(f"API: http://localhost:{PORT}/api/...")
    app.run(host='0.0.0.0', port=PORT, debug=False)
