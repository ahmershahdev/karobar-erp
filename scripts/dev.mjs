// Starts the whole stack for local development with one command: `npm run dev`.
// MySQL and Redis run in Docker; Django, the Celery worker and Vite run on the host so code
// reloads instantly. Ctrl+C stops everything this script started (the containers keep running).

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { join } from 'node:path';

const root = join(import.meta.dirname, '..');
const backend = join(root, 'backend');
const frontend = join(root, 'frontend');
const windows = process.platform === 'win32';
const venvBin = join(backend, '.venv', windows ? 'Scripts' : 'bin');
const python = join(venvBin, windows ? 'python.exe' : 'python');

const COLORS = { db: 90, api: 36, worker: 35, beat: 34, web: 33 };

function step(label, command, args, options = {}) {
  console.log(`\x1b[1m> ${label}\x1b[0m`);
  const result = spawnSync(command, args, { stdio: 'inherit', shell: windows, ...options });
  if (result.status !== 0) {
    console.error(`\n${label} failed. Fix the error above and run npm run dev again.`);
    process.exit(result.status ?? 1);
  }
}

function writeIfMissing(file, contents) {
  // The 'wx' flag creates the file only if it doesn't exist, in one step, so an existing .env is
  // never overwritten even if something creates it between a check and the write.
  try {
    writeFileSync(file, contents, { flag: 'wx' });
    return true;
  } catch (error) {
    if (error.code === 'EEXIST') return false;
    throw error;
  }
}

function ensureBackendEnv() {
  // A fresh random key for this machine only; .env is git-ignored.
  const key = randomBytes(48).toString('base64url');
  const example = readFileSync(join(backend, '.env.example'), 'utf8');
  const contents = example.replace(/^DJANGO_SECRET_KEY=.*$/m, `DJANGO_SECRET_KEY=${key}`);
  if (writeIfMissing(join(backend, '.env'), contents)) {
    console.log('Created backend/.env from .env.example');
  }
}

function ensurePythonEnv() {
  if (existsSync(python)) return;
  const launcher = windows ? 'py' : 'python3';
  const version = windows ? ['-3.12'] : [];
  step('Creating backend/.venv', launcher, [...version, '-m', 'venv', '.venv'], { cwd: backend });
  step('Installing Python packages', python, ['-m', 'pip', 'install', '-r', 'requirements/dev.txt'], {
    cwd: backend,
  });
}

function ensureNodeModules() {
  if (existsSync(join(frontend, 'node_modules'))) return;
  step('Installing frontend packages', 'npm', ['ci'], { cwd: frontend });
}

function ensureFrontendEnv() {
  writeIfMissing(join(frontend, '.env.local'), readFileSync(join(frontend, '.env.example'), 'utf8'));
}

const children = [];

function run(name, command, args, cwd) {
  const child = spawn(command, args, { cwd, shell: windows, env: process.env });
  const prefix = `\x1b[${COLORS[name]}m${name.padEnd(6)}|\x1b[0m `;
  const pipe = (stream, out) => {
    let buffer = '';
    stream.on('data', (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? '';
      for (const line of lines) out.write(prefix + line + '\n');
    });
  };
  pipe(child.stdout, process.stdout);
  pipe(child.stderr, process.stderr);
  child.on('exit', (code) => {
    console.log(`${prefix}exited with code ${code}`);
    shutdown(code ?? 0);
  });
  children.push(child);
}

let stopping = false;
function shutdown(code) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode !== null) continue;
    if (windows) spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' });
    else child.kill('SIGINT');
  }
  process.exit(code);
}
process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

ensureBackendEnv();
ensurePythonEnv();
ensureNodeModules();
ensureFrontendEnv();
step('Starting MySQL and Redis', 'docker', ['compose', 'up', '-d', '--wait', 'mysql', 'redis'], {
  cwd: root,
});
step('Applying migrations', python, ['manage.py', 'migrate', '--noinput'], { cwd: backend });

run('api', python, ['manage.py', 'runserver', '127.0.0.1:8000'], backend);
run(
  'worker',
  python,
  ['-m', 'celery', '-A', 'config', 'worker', '--loglevel=info', ...(windows ? ['--pool=solo'] : [])],
  backend,
);
// Beat sends scheduled jobs (the morning stock-alert email) to the worker.
run('beat', python, ['-m', 'celery', '-A', 'config', 'beat', '--loglevel=info', '--schedule', join(backend, '.celerybeat-schedule')], backend);
run('web', 'npm', ['run', 'dev'], frontend);

console.log('\n  Karobar ERP is starting: http://localhost:5173  (API on :8000)');
console.log('  Emails (sign-up links, invitations) are printed in the worker log.\n');
