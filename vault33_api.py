# “””
Vault 33 — REST API + Dashboard Server

Endpoints:
GET  /health                          — Health check
GET  /api/stats                       — Vault statistics
GET  /api/files                       — List all files
POST /api/ingest                      — Ingest a file (multipart upload)
GET  /api/retrieve/<manifest_id>      — Download a file
GET  /api/proof/<manifest_id>         — Integrity proof
DELETE /api/files/<manifest_id>       — Delete a file
GET  /                                — Web dashboard
“””

import os
import sys
import json
import tempfile
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS

sys.path.insert(0, str(Path(**file**).parent))
from vault33_production import Vault33, _fmt, VERSION

# ── Config ───────────────────────────────────────────────────────────────────

VAULT_DIR    = os.environ.get(“VAULT33_DIR”,      “./vault33_data”)
VAULT_KEY    = os.environ.get(“VAULT33_KEY”,      “vault33-default-dev-key-change-me!”)
PORT         = int(os.environ.get(“VAULT33_PORT”, 8033))
CHUNK_MB     = int(os.environ.get(“VAULT33_CHUNK_MB”, 64))
WORKERS      = int(os.environ.get(“VAULT33_WORKERS”,  4))

if VAULT_KEY == “vault33-default-dev-key-change-me!”:
print(“⚠️  WARNING: Using default encryption key. Set VAULT33_KEY env var.”)

# ── Vault instance ───────────────────────────────────────────────────────────

vault = Vault33(
vault_dir=VAULT_DIR,
master_key=VAULT_KEY.encode(),
chunk_size=CHUNK_MB * 1024 * 1024,
workers=WORKERS,
)

# ── Active ingestion tracker ─────────────────────────────────────────────────

active_ingests: dict = {}   # job_id → progress dict
ingest_lock = threading.Lock()

# ── Flask app ────────────────────────────────────────────────────────────────

app = Flask(**name**, static_folder=None)
CORS(app)

# ── Health ───────────────────────────────────────────────────────────────────

@app.route(”/health”)
def health():
return jsonify({“status”: “ok”, “vault_id”: vault.vault_id, “version”: VERSION})

# ── Stats ────────────────────────────────────────────────────────────────────

@app.route(”/api/stats”)
def api_stats():
return jsonify(vault.stats())

# ── List files ───────────────────────────────────────────────────────────────

@app.route(”/api/files”)
def api_list():
return jsonify(vault.list_files())

# ── Ingest ───────────────────────────────────────────────────────────────────

@app.route(”/api/ingest”, methods=[“POST”])
def api_ingest():
“””
Multipart file upload. Streams to temp file then ingests.
Returns job_id for progress polling.
For large files (>1GB) use the streaming endpoint below.
“””
if “file” not in request.files:
return jsonify({“error”: “No file in request”}), 400

```
f    = request.files["file"]
name = request.form.get("name") or f.filename or "upload"

# Write to temp file (Flask buffers uploads to disk automatically)
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
f.save(tmp.name)
tmp.close()

job_id = f"job-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

with ingest_lock:
    active_ingests[job_id] = {
        "status": "running", "name": name,
        "progress_pct": 0, "rate_mbps": 0,
        "started": datetime.now().isoformat(),
    }

def run_ingest():
    def cb(done, total, pct, rate, eta):
        with ingest_lock:
            active_ingests[job_id]["progress_pct"] = round(pct, 1)
            active_ingests[job_id]["rate_mbps"]    = round(rate, 1)
            active_ingests[job_id]["eta_seconds"]  = round(eta)
    try:
        mid = vault.ingest_file(tmp.name, name=name, progress_callback=cb)
        with ingest_lock:
            active_ingests[job_id].update({
                "status": "done", "manifest_id": mid,
                "progress_pct": 100,
                "finished": datetime.now().isoformat(),
            })
    except Exception as e:
        with ingest_lock:
            active_ingests[job_id].update({"status": "error", "error": str(e)})
    finally:
        try: os.unlink(tmp.name)
        except: pass

threading.Thread(target=run_ingest, daemon=True).start()
return jsonify({"job_id": job_id, "status": "running"})
```

@app.route(”/api/ingest/progress/<job_id>”)
def api_ingest_progress(job_id):
with ingest_lock:
info = active_ingests.get(job_id)
if not info:
return jsonify({“error”: “Job not found”}), 404
return jsonify(info)

# ── Retrieve ─────────────────────────────────────────────────────────────────

@app.route(”/api/retrieve/<manifest_id>”)
def api_retrieve(manifest_id):
“”“Stream file back to client. Works for any size.”””
files = vault.list_files()
meta  = next((f for f in files if f[“manifest_id”] == manifest_id), None)
if not meta:
return jsonify({“error”: “Not found”}), 404

```
tmp = tempfile.mktemp(suffix=".bin")

try:
    vault.retrieve_file(manifest_id, tmp)
    return send_file(
        tmp,
        as_attachment=True,
        download_name=meta["name"],
    )
except Exception as e:
    return jsonify({"error": str(e)}), 500
```

# ── Proof ────────────────────────────────────────────────────────────────────

@app.route(”/api/proof/<manifest_id>”)
def api_proof(manifest_id):
proof = vault.integrity_proof(manifest_id)
return jsonify(proof)

# ── Delete ───────────────────────────────────────────────────────────────────

@app.route(”/api/files/<manifest_id>”, methods=[“DELETE”])
def api_delete(manifest_id):
ok = vault.delete_file(manifest_id)
return jsonify({“deleted”: ok, “manifest_id”: manifest_id})

# ── Dashboard (inline HTML) ──────────────────────────────────────────────────

DASHBOARD_HTML = “””<!DOCTYPE html>

<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Vault 33 — Production Dashboard</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@300;400;500&display=swap');
:root{--bg:#08090d;--card:#0e1118;--border:#1a1e2e;--accent:#00cfff;--ok:#00e5a0;--warn:#ff6b35;--text:#c0c8dc;--dim:#3e4560;--white:#eef1f8;--mono:'IBM Plex Mono',monospace;--display:'Bebas Neue',sans-serif;--body:'Inter',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--body);font-size:14px}
.page{max-width:1100px;margin:0 auto;padding:32px 20px 60px}
header{padding-bottom:20px;border-bottom:1px solid var(--border);margin-bottom:28px;display:flex;justify-content:space-between;align-items:flex-end}
.logo{font-family:var(--display);font-size:48px;letter-spacing:3px;color:var(--white);text-shadow:0 0 40px rgba(0,207,255,.15)}
.vault-id{font-family:var(--mono);font-size:10px;color:var(--dim);text-align:right}
.vault-id span{display:block;color:var(--accent);font-size:11px;margin-top:3px}
.stats-row{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:24px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:5px;padding:14px 16px}
.stat-label{font-family:var(--mono);font-size:9px;color:var(--dim);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px}
.stat-val{font-family:var(--display);font-size:28px;letter-spacing:1px;color:var(--accent)}
.stat-val.ok{color:var(--ok)}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.panel{background:var(--card);border:1px solid var(--border);border-radius:5px;overflow:hidden}
.panel-header{padding:10px 16px;border-bottom:1px solid var(--border);font-family:var(--mono);font-size:11px;color:var(--accent);letter-spacing:1px;display:flex;justify-content:space-between;align-items:center}
.panel-body{padding:16px}
.drop-zone{border:2px dashed var(--border);border-radius:5px;padding:24px;text-align:center;cursor:pointer;transition:all .2s;position:relative;margin-bottom:12px}
.drop-zone:hover,.drop-zone.drag{border-color:var(--accent);background:rgba(0,207,255,.03)}
.drop-zone input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.drop-icon{font-size:28px;margin-bottom:6px}
.drop-label{font-family:var(--mono);font-size:11px;color:var(--dim)}
.drop-label strong{color:var(--accent)}
.prog-wrap{display:none;margin-bottom:12px}
.prog-bar-track{background:var(--bg);border-radius:3px;height:6px;overflow:hidden;margin:6px 0}
.prog-bar-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--ok));border-radius:3px;transition:width .4s}
.prog-text{font-family:var(--mono);font-size:10px;color:var(--dim)}
button{background:transparent;border:1px solid var(--accent);color:var(--accent);font-family:var(--mono);font-size:11px;padding:7px 16px;border-radius:4px;cursor:pointer;letter-spacing:1px;transition:all .15s}
button:hover{background:var(--accent);color:var(--bg)}
button.ok{border-color:var(--ok);color:var(--ok)}
button.ok:hover{background:var(--ok);color:var(--bg)}
button.warn{border-color:var(--warn);color:var(--warn)}
button.warn:hover{background:var(--warn);color:var(--bg)}
.files-table{width:100%;border-collapse:collapse}
.files-table th{font-family:var(--mono);font-size:9px;color:var(--dim);letter-spacing:1.5px;text-transform:uppercase;padding:8px 10px;text-align:left;border-bottom:1px solid var(--border)}
.files-table td{padding:9px 10px;border-bottom:1px solid rgba(26,30,46,.5);font-size:12px;vertical-align:middle}
.files-table tr:last-child td{border-bottom:none}
.files-table tr:hover td{background:rgba(0,207,255,.02)}
.mid-cell{font-family:var(--mono);font-size:10px;color:var(--accent)}
.log{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px 12px;font-family:var(--mono);font-size:11px;max-height:160px;overflow-y:auto;margin-top:12px}
.log-line{color:var(--dim);padding:2px 0}
.log-line .ts{color:rgba(0,207,255,.4);margin-right:6px}
.log-line .ok{color:var(--ok)}
.log-line .info{color:var(--accent)}
.log-line .err{color:var(--warn)}
</style>
</head>
<body>
<div class="page">
  <header>
    <div>
      <div class="logo">VAULT 33</div>
      <div style="font-family:var(--mono);font-size:10px;color:var(--accent);letter-spacing:2px;margin-top:4px">PRODUCTION ENGINE — COMPRESS · ENCRYPT · DEDUPLICATE</div>
    </div>
    <div class="vault-id">VAULT ID<span id="vaultId">loading...</span></div>
  </header>

  <div class="stats-row" id="statsRow">
    <div class="stat"><div class="stat-label">Files</div><div class="stat-val" id="sFiles">—</div></div>
    <div class="stat"><div class="stat-label">Original</div><div class="stat-val" id="sOriginal">—</div></div>
    <div class="stat"><div class="stat-label">Stored</div><div class="stat-val" id="sStored">—</div></div>
    <div class="stat"><div class="stat-label">Ratio</div><div class="stat-val ok" id="sRatio">—</div></div>
    <div class="stat"><div class="stat-label">Dedup Chunks</div><div class="stat-val" id="sDedup">—</div></div>
  </div>

  <div class="two-col">
    <div class="panel">
      <div class="panel-header"><span>⬆ INGEST</span><span style="color:var(--dim)">ANY SIZE</span></div>
      <div class="panel-body">
        <div class="drop-zone" id="dropZone">
          <input type="file" id="fileInput" multiple/>
          <div class="drop-icon">🗃</div>
          <div class="drop-label">Drop files or <strong>click to browse</strong><br/>Any size — streamed, not buffered</div>
        </div>
        <div class="prog-wrap" id="progWrap">
          <div class="prog-text" id="progText">Uploading...</div>
          <div class="prog-bar-track"><div class="prog-bar-fill" id="progBar" style="width:0%"></div></div>
          <div class="prog-text" id="progDetail"></div>
        </div>
        <div id="ingestResult" style="font-family:var(--mono);font-size:11px;color:var(--ok);min-height:20px"></div>
      </div>
    </div>

```
<div class="panel">
  <div class="panel-header"><span>◈ FILES</span><span id="fileCount" style="color:var(--dim)">0 files</span></div>
  <div style="overflow-x:auto;max-height:220px;overflow-y:auto">
    <table class="files-table">
      <thead><tr><th>Name</th><th>Size</th><th>Ratio</th><th>Manifest ID</th><th></th></tr></thead>
      <tbody id="filesTbody"><tr><td colspan="5" style="text-align:center;color:var(--dim);padding:20px;font-family:var(--mono);font-size:11px">No files yet</td></tr></tbody>
    </table>
  </div>
</div>
```

  </div>

  <div class="log" id="logEl"></div>
</div>

<script>
const API = '';
let vaultId = '—';

function ts(){return new Date().toTimeString().slice(0,8)}
function log(msg,type='info'){
  const el=document.getElementById('logEl');
  const d=document.createElement('div');
  d.className='log-line';
  d.innerHTML=`<span class="ts">[${ts()}]</span><span class="${type}">${msg}</span>`;
  el.appendChild(d);el.scrollTop=el.scrollHeight;
}
function fmtBytes(b){const u=['B','KB','MB','GB','TB'];let i=0;while(b>=1024&&i<4){b/=1024;i++}return b.toFixed(1)+u[i]}

async function loadStats(){
  const r=await fetch('/api/stats');const s=await r.json();
  document.getElementById('vaultId').textContent=s.vault_id;
  document.getElementById('sFiles').textContent=s.total_files;
  document.getElementById('sOriginal').textContent=fmtBytes(s.total_original_bytes||0);
  document.getElementById('sStored').textContent=fmtBytes(s.total_stored_bytes||0);
  document.getElementById('sRatio').textContent=s.compression_ratio?(s.compression_ratio+'x'):'—';
  document.getElementById('sDedup').textContent=s.dedup_chunks||0;
}

async function loadFiles(){
  const r=await fetch('/api/files');const files=await r.json();
  document.getElementById('fileCount').textContent=files.length+' file'+(files.length!==1?'s':'');
  const tb=document.getElementById('filesTbody');
  if(!files.length){tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:var(--dim);padding:20px;font-family:var(--mono);font-size:11px">No files yet</td></tr>';return;}
  tb.innerHTML=files.map(f=>`
    <tr>
      <td title="${f.name}">${f.name.length>24?f.name.slice(0,24)+'…':f.name}</td>
      <td>${fmtBytes(f.size)}</td>
      <td>—</td>
      <td class="mid-cell" title="${f.manifest_id}">${f.manifest_id.slice(0,20)}…</td>
      <td>
        <button onclick="downloadFile('${f.manifest_id}','${f.name}')" style="font-size:9px;padding:3px 8px">GET</button>
        <button class="warn" onclick="deleteFile('${f.manifest_id}')" style="font-size:9px;padding:3px 8px;margin-left:4px">DEL</button>
      </td>
    </tr>`).join('');
}

async function downloadFile(mid, name){
  log(`Retrieving ${name}...`,'info');
  window.location.href=`/api/retrieve/${mid}`;
}

async function deleteFile(mid){
  if(!confirm('Delete this file from vault?'))return;
  await fetch(`/api/files/${mid}`,{method:'DELETE'});
  log(`Deleted ${mid}`,'ok');
  await loadStats();await loadFiles();
}

async function pollJob(jobId){
  const wrap=document.getElementById('progWrap');
  const bar=document.getElementById('progBar');
  const txt=document.getElementById('progText');
  const det=document.getElementById('progDetail');
  wrap.style.display='block';

  while(true){
    await new Promise(r=>setTimeout(r,800));
    const r=await fetch(`/api/ingest/progress/${jobId}`);
    const j=await r.json();
    bar.style.width=j.progress_pct+'%';
    txt.textContent=`Ingesting... ${j.progress_pct}%`;
    if(j.rate_mbps) det.textContent=`${j.rate_mbps} MB/s  ETA ${j.eta_seconds||0}s`;
    if(j.status==='done'){
      document.getElementById('ingestResult').textContent=`✅ ${j.manifest_id}`;
      log(`Ingested → ${j.manifest_id}`,'ok');
      wrap.style.display='none';
      await loadStats();await loadFiles();
      break;
    }
    if(j.status==='error'){
      document.getElementById('ingestResult').textContent=`❌ ${j.error}`;
      log(`Error: ${j.error}`,'err');
      wrap.style.display='none';
      break;
    }
  }
}

document.getElementById('fileInput').addEventListener('change',async(e)=>{
  for(const file of e.target.files){
    log(`Uploading ${file.name} (${fmtBytes(file.size)})`,'info');
    const fd=new FormData();
    fd.append('file',file);fd.append('name',file.name);
    const r=await fetch('/api/ingest',{method:'POST',body:fd});
    const j=await r.json();
    if(j.job_id) await pollJob(j.job_id);
  }
  e.target.value='';
});

const dz=document.getElementById('dropZone');
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag')});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag'));
dz.addEventListener('drop',async(e)=>{
  e.preventDefault();dz.classList.remove('drag');
  for(const file of e.dataTransfer.files){
    const fd=new FormData();fd.append('file',file);fd.append('name',file.name);
    log(`Uploading ${file.name}`,'info');
    const r=await fetch('/api/ingest',{method:'POST',body:fd});
    const j=await r.json();
    if(j.job_id) await pollJob(j.job_id);
  }
});

log('Vault 33 production dashboard connected','info');
loadStats();loadFiles();
setInterval(()=>{loadStats();loadFiles();},15000);
</script>

</body>
</html>
"""

@app.route(”/”)
def dashboard():
return Response(DASHBOARD_HTML, mimetype=“text/html”)

# ── Entry point ───────────────────────────────────────────────────────────────

if **name** == “**main**”:
print(f”\n🚀 Vault 33 API starting on port {PORT}”)
print(f”   Dashboard: http://localhost:{PORT}”)
print(f”   Vault dir: {VAULT_DIR}”)
print(f”   Chunk size: {CHUNK_MB}MB  Workers: {WORKERS}”)
print()
app.run(host=“0.0.0.0”, port=PORT, threaded=True, debug=False)