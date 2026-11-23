#!/usr/bin/env node
/**
 * beforeReadFile: block secret paths.
 * Adapted from agent-sdlc/sample-harness-project.
 */
const fs = require("fs");
const path = require("path");

let raw = "";
try {
  raw = fs.readFileSync(0, "utf8");
} catch {
  raw = "";
}

let payload = {};
try {
  payload = raw ? JSON.parse(raw) : {};
} catch {
  payload = { path: raw };
}

const file = String(
  payload.path || payload.filePath || payload.file || payload.uri || ""
);
const base = path.basename(file);
const norm = file.replace(/\\/g, "/");

const blocked =
  base === ".env" ||
  /^\.env\./.test(base) ||
  norm.includes("/secrets/") ||
  norm.endsWith("/secrets");

if (blocked) {
  console.error(`DENIED: reading secrets is blocked by harness (${file || "unknown path"})`);
  process.exit(2);
}

process.exit(0);
