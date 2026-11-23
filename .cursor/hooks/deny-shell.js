#!/usr/bin/env node
/**
 * beforeShellExecution: block must-never shell patterns.
 * Adapted from agent-sdlc/sample-harness-project.
 * Exit 0 allows; exit 2 is a hard block when the host honors it.
 */
const fs = require("fs");

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
  payload = { command: raw };
}

const cmd = String(
  payload.command || payload.cmd || payload.shellCommand || raw || ""
).toLowerCase();

const denied = [
  { re: /git\s+push\s+(-f|--force)/, why: "force-push is denied by harness" },
  { re: /\b(kubectl|helm)\b.*\b(apply|delete)\b.*\bprod(uction)?\b/, why: "prod cluster mutate denied" },
  { re: /\brm\s+-rf\s+\/\b/, why: "destructive root delete denied" },
];

for (const { re, why } of denied) {
  if (re.test(cmd)) {
    const msg = `DENIED: ${why}. Command: ${cmd.slice(0, 200)}`;
    console.error(msg);
    process.exit(2);
  }
}

process.exit(0);
