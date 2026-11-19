// Fails if the committed generated client differs from what openapi/openapi.json produces.
// CI runs `npm run api:snapshot` first, so a backend contract change without a
// regenerated client breaks the build (LLD, Portal Build: API client).
import { execSync } from 'node:child_process';
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';

const committed = 'src/app/core/api/generated';
const scratch = mkdtempSync(join(tmpdir(), 'amc-api-'));

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

function snapshot(dir) {
  return new Map(
    walk(dir).map((f) => [relative(dir, f).replaceAll('\\', '/'), readFileSync(f, 'utf8')]),
  );
}

try {
  execSync(`npx ng-openapi-gen --config ng-openapi-gen.json --output "${scratch}"`, {
    stdio: 'inherit',
  });
  const want = snapshot(scratch);
  const have = snapshot(committed);
  const drift = [...new Set([...want.keys(), ...have.keys()])].filter(
    (k) => want.get(k) !== have.get(k),
  );
  if (drift.length) {
    console.error(`API client drift in ${drift.length} file(s); run "npm run api:gen" and commit:`);
    drift.forEach((f) => console.error(`  ${f}`));
    process.exitCode = 1;
  } else {
    console.log('API client matches openapi/openapi.json');
  }
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
