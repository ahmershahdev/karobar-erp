// Where the end-to-end stack lives and how its two servers are started. The tests use their own
// ports, database and Redis database, so a developer's running app is never touched.

import { existsSync } from 'node:fs';
import { join } from 'node:path';

const root = join(import.meta.dirname, '..');
const windows = process.platform === 'win32';
const venvPython = join(
  root,
  'backend',
  '.venv',
  windows ? 'Scripts' : 'bin',
  windows ? 'python.exe' : 'python',
);

export const backend = join(root, 'backend');
export const frontend = join(root, 'frontend');
// A worktree has no virtual environment of its own; E2E_PYTHON names the one to use.
export const python = process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : 'python');
export const mailDir = join(import.meta.dirname, '.mail');

export const API_PORT = Number(process.env.E2E_API_PORT ?? 8001);
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5174);
export const baseURL = `http://localhost:${WEB_PORT}`;

// Invented accounts, made by seed.py. The password is only ever used against this stack.
export const PASSWORD = process.env.E2E_PASSWORD ?? 'seven quiet lanterns drift home';
export const DEMO_EMAIL = 'demo@example.com';

export const serverEnv = {
  ...process.env,
  DJANGO_SETTINGS_MODULE: 'config.settings.e2e',
  DATABASE_URL:
    process.env.E2E_DATABASE_URL ?? 'mysql://karobar:karobar@127.0.0.1:3306/test_karobar',
  REDIS_URL: process.env.E2E_REDIS_URL ?? 'redis://127.0.0.1:6379/1',
  SITE_URL: baseURL,
  E2E_MAIL_DIR: mailDir,
  E2E_PASSWORD: PASSWORD,
  DEMO_MODE: 'true',
  DEMO_EMAIL,
  DEMO_PASSWORD: PASSWORD,
  PYTHONUNBUFFERED: '1',
};
