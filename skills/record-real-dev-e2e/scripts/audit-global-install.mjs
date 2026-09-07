#!/usr/bin/env node
import { existsSync, lstatSync, readdirSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join } from "node:path";

const skillName = "record-real-dev-e2e";
const home = process.argv[2] ?? homedir();
const canonical = join(home, ".agents", "skills", skillName);

if (!existsSync(canonical)) {
  console.error(`FAIL canonical package missing: ${canonical}`);
  process.exit(1);
}

const canonicalReal = realpathSync(canonical);
const skillDirs = [];

function childDirectories(path) {
  try {
    return readdirSync(path, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() || entry.isSymbolicLink())
      .map((entry) => entry.name);
  } catch {
    return [];
  }
}

// Global catalogs live directly under a harness root, not under its backups or projects.
for (const name of childDirectories(home)) {
  if (name.startsWith(".")) skillDirs.push(join(home, name, "skills"));
}
for (const name of childDirectories(join(home, ".config"))) {
  skillDirs.push(join(home, ".config", name, "skills"));
}
for (const name of ["config", "antigravity", "antigravity-cli", "antigravity-ide"]) {
  skillDirs.push(join(home, ".gemini", name, "skills"));
}

const installed = new Set([canonical]);
const failures = [];
for (const dir of skillDirs) {
  const candidate = join(dir, skillName);
  if (!existsSync(candidate)) continue;
  installed.add(candidate);
  const actual = realpathSync(candidate);
  if (actual !== canonicalReal) failures.push(`${candidate} -> ${actual}`);
}

if (failures.length > 0) {
  for (const failure of failures) console.error(`FAIL divergent package: ${failure}`);
  process.exit(1);
}

const explicitLinks = [...installed].filter((path) => path !== canonical && lstatSync(path).isSymbolicLink()).length;
console.log(`Global install audit passed: canonical=1 explicit_links=${explicitLinks} divergent=0`);
console.log(`Canonical package: ${basename(canonicalReal)}`);
