import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const script = new URL('./audit-global-install.mjs', import.meta.url);
function fixture(run) {
 const root = mkdtempSync(join(tmpdir(), 'skill-audit-'));
 const canonical = join(root, '.agents/skills/record-real-dev-e2e');
 mkdirSync(canonical, { recursive: true });
 try { run(root, canonical); } finally { rmSync(root, { recursive: true, force: true }); }
}
const audit = root => spawnSync(process.execPath, [fileURLToPath(script), root], { encoding: 'utf8' });
test('ignores backups, worktrees and archived source while finding global links', () => fixture((root, canonical) => {
 for (const suffix of ['.agents/cleanup-backups/run/skills/record-real-dev-e2e', '.codex/worktrees/review/skills/record-real-dev-e2e', '.claude/archive/source/skills/record-real-dev-e2e']) mkdirSync(join(root, suffix), { recursive: true });
 mkdirSync(join(root, '.claude/skills'), { recursive: true });
 symlinkSync(canonical, join(root, '.claude/skills/record-real-dev-e2e'), 'junction');
 const result = audit(root); assert.equal(result.status, 0, result.stderr);
 assert.match(result.stdout, /explicit_links=1/);
}));
test('detects divergent install in a real harness root', () => fixture(root => {
 mkdirSync(join(root, '.cursor/skills/record-real-dev-e2e'), { recursive: true });
 const result = audit(root); assert.equal(result.status, 1); assert.match(result.stderr, /divergent package.*\.cursor/);
}));
test('follows symlinked skills roots and finds config and Antigravity installs', () => fixture((root, canonical) => {
 mkdirSync(join(root, '.claude'), { recursive: true });
 symlinkSync(join(root, '.agents/skills'), join(root, '.claude/skills'), 'junction');
 for (const suffix of ['.config/opencode/skills', '.gemini/antigravity/skills']) {
  mkdirSync(join(root, suffix), { recursive: true });
  symlinkSync(canonical, join(root, suffix, 'record-real-dev-e2e'), 'junction');
 }
 assert.equal(audit(root).status, 0);
 rmSync(join(root, '.claude/skills'));
 mkdirSync(join(root, 'external/record-real-dev-e2e'), { recursive: true });
 symlinkSync(join(root, 'external'), join(root, '.claude/skills'), 'junction');
 assert.equal(audit(root).status, 1);
}));

test('detects divergent Antigravity config catalog', () => fixture(root => {
 mkdirSync(join(root, '.gemini/config/skills/record-real-dev-e2e'), { recursive: true });
 assert.equal(audit(root).status, 1);
}));
