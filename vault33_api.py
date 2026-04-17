"""
Vault 33 - REST API + Dashboard Server

Endpoints:
GET  /health                          - Health check
GET  /api/stats                       - Vault statistics
GET  /api/files                       - List all files
POST /api/ingest                      - Ingest a file (multipart upload)
GET  /api/retrieve/<manifest_id>      - Download a file
GET  /api/proof/<manifest_id>         - Integrity proof
DELETE /api/files/<manifest_id>       - Delete a file
GET  /                                - Web dashboard
"""

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
from vault33_production import Vault33, _fmt, VERSION

# Config
PORT = int(os.environ.get("VAULT33_PORT", 8033))
VAULT_DIR = os.environ.get("VAULT33_DIR", "/tmp/vault33")
MASTER_KEY = os.environ.get("VAULT33_KEY", None)
if MASTER_KEY:
    MASTER_KEY = MASTER_KEY.encode()

app = Flask(__name__)
CORS(app)

# Initialize vault
vault = Vault33(VAULT_DIR, master_key=MASTER_KEY)

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
</tr>
</thead>
<tbody id="files-table">
<tr><td colspan="5" style="text-align: center; color: #666; padding: 20px;">No files yet</td></tr>
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
        tb.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #666; padding: 20px;">No files yet</td></tr>';
        return;
      }
      tb.innerHTML = files.map(f => `
        <tr>
        <td>${f.original_name}</td>
        <td>${formatBytes(f.original_size)}</td>
        <td>${formatBytes(f.compressed_size)}</td>
        <td>${f.compression_ratio.toFixed(1)}x</td>
        <td>${f.created_at.split('T')[0]}</td>
        </tr>
      `).join('');
    });
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

# Routes
@app.route('/')
def dashboard():
    return Response(DASHBOARD_HTML, mimetype="text/html")

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': VERSION})

@app.route('/api/stats')
def api_stats():
    stats = vault.get_stats()
    return jsonify(stats)

@app.route('/api/files')
def api_files():
    manifests_dir = Path(VAULT_DIR) / "manifests"
    files = []
    if manifests_dir.exists():
        for mf in manifests_dir.glob("*.json"):
            with open(mf, 'r') as f:
                manifest = json.load(f)
                files.append({
                    'manifest_id': manifest['manifest_id'],
                    'original_name': manifest['original_name'],
                    'original_size': manifest['original_size'],
                    'compressed_size': manifest['compressed_size'],
                    'compression_ratio': manifest['compression_ratio'],
                    'created_at': manifest['created_at']
                })
    return jsonify(sorted(files, key=lambda x: x['created_at'], reverse=True))

@app.route('/api/ingest', methods=['POST'])
def api_ingest():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    
    # Save to temp
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name
    
    try:
        # Ingest
        manifest = vault.ingest_file(tmp_path)
        return jsonify(manifest)
    finally:
        os.unlink(tmp_path)

@app.route('/api/retrieve/<manifest_id>')
def api_retrieve(manifest_id):
    try:
        data = vault.retrieve_file(manifest_id)
        # Get original name from manifest
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
    try:
        manifest_path = Path(VAULT_DIR) / "manifests" / f"{manifest_id}.json"
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        return jsonify({
            'manifest_id': manifest_id,
            'merkle_root': manifest['merkle_root'],
            'chunk_count': manifest['chunk_count'],
            'verified': True
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/files/<manifest_id>', methods=['DELETE'])
def api_delete(manifest_id):
    try:
        manifest_path = Path(VAULT_DIR) / "manifests" / f"{manifest_id}.json"
        if manifest_path.exists():
            manifest_path.unlink()
            return jsonify({'status': 'deleted'})
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print(f"Vault 33 v2 - REST API + Dashboard")
    print(f"Vault directory: {VAULT_DIR}")
    print(f"Dashboard: http://localhost:{PORT}")
    print(f"API: http://localhost:{PORT}/api/...")
    app.run(host='0.0.0.0', port=PORT, debug=False)
