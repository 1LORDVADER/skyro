from src.runtime import PortRuntime
from pathlib import Path

VAULT_PATH = Path("../vault33-digital").resolve()

print(f"🚀 Vault 33 connected → {VAULT_PATH}")
print(f"Markdown notes detected: {len(list(VAULT_PATH.glob('**/*.md')))}\n")

runtime = PortRuntime()

print("Starting Vault 33 Guardian Agent (full mirrored runtime)...\n")

results = runtime.run_turn_loop(
prompt="""
You are now the eternal guardian of Vault 33 (Lord Vader's Obsidian second brain).
Workspace root = vault33-digital folder.
1. Scan the entire vault for notes tagged #needs-ai, #trading, or #fallout
2. Auto-improve formatting, add bidirectional links, create MOCs where missing
3. Write a new daily summary note in the Journal folder (or create the folder if missing)
4. Commit changes with a Sith-themed git message
""",
max_turns=5
)

for idx, result in enumerate(results, start=1):
print(f"\n## Turn {idx} — Result")
print(result.output)
print(f"stop_reason = {result.stop_reason}")
