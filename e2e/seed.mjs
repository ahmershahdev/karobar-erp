// Empties the end-to-end database and fills it again: migrations, the two demo businesses and
// the people in seed.py. Takes a few minutes, because every demo document is really posted.

import { spawnSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { backend, mailDir, python, serverEnv } from './stack.mjs';

const days = process.env.E2E_DEMO_DAYS ?? '14';

function manage(...args) {
  console.log(`> manage.py ${args.join(' ')}`);
  const result = spawnSync(python, ['manage.py', ...args], {
    cwd: backend,
    env: serverEnv,
    stdio: 'inherit',
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

if (!/\/(test_|e2e_)\w+$/.test(new URL(serverEnv.DATABASE_URL).pathname)) {
  // flush removes every row, so it only ever runs on a database named for tests.
  console.error('The end-to-end database name must start with test_ or e2e_.');
  process.exit(1);
}

// `node seed.mjs --people` only adds the people in seed.py to a database that is already filled.
if (!process.argv.includes('--people')) {
  rmSync(mailDir, { recursive: true, force: true });
  mkdirSync(mailDir, { recursive: true });
  manage('migrate', '--noinput');
  manage('flush', '--noinput');
  manage('seed_demo', '--days', days);
}
const script = join(import.meta.dirname, 'seed.py').replaceAll('\\', '/');
manage('shell', '-c', `exec(open('${script}', encoding='utf-8').read())`);
