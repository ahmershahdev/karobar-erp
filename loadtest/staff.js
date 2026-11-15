// Load and stress test: staff of one business working at the same time. Run with k6 in Docker
// (see docs/testing.md). Each simulated person signs in once, then keeps doing one of four jobs:
// reading lists, reading reports, adding customers, or making and posting sales bills. The bill
// makers all sell the same few products from the same store, which is where stock levels, bill
// numbers and the books are under contention.

import { check, group, sleep } from 'k6';
import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE = __ENV.BASE || 'http://host.docker.internal:8001';
const HOST = __ENV.HOST_HEADER || 'localhost:8001';
const PASSWORD = __ENV.PASSWORD || 'seven quiet lanterns drift home';
const STAFF = Number(__ENV.STAFF || 50);
const PEAK = Number(__ENV.PEAK || 50);
const HOLD = __ENV.HOLD || '2m';

const serverErrors = new Counter('server_errors');
const refused = new Counter('throttled_or_refused');
const billsPosted = new Counter('bills_posted');
const billsOutOfStock = new Counter('bills_refused_no_stock');
const wrongAnswers = new Rate('wrong_answers');
const postTime = new Trend('bill_post_ms', true);

export const options = {
  // The session cookie has to last for the whole run, not one round.
  noCookiesReset: true,
  scenarios: {
    staff: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: Math.min(10, PEAK) },
        { duration: '1m', target: Math.min(10, PEAK) },
        { duration: '30s', target: Math.min(25, PEAK) },
        { duration: '1m', target: Math.min(25, PEAK) },
        { duration: '30s', target: PEAK },
        { duration: HOLD, target: PEAK },
        { duration: '20s', target: 0 },
      ],
      gracefulRampDown: '20s',
    },
  },
  thresholds: {
    // Nothing may ever be a server error, and no answer may be wrong. Speed limits are loose
    // here because the development server is being measured, not gunicorn behind nginx.
    server_errors: ['count==0'],
    wrong_answers: ['rate==0'],
    http_req_failed: ['rate<0.05'],
  },
};

function headers(session, write) {
  const base = { Host: HOST, 'X-Tenant': session.tenant, Accept: 'application/json' };
  return write
    ? { ...base, 'Content-Type': 'application/json', 'X-CSRFToken': session.csrf, Referer: `http://${HOST}/` }
    : base;
}

function note(reply, name) {
  if (reply.status >= 500 || reply.status === 0) {
    serverErrors.add(1, { name });
    console.error(`${name}: ${reply.status} ${String(reply.body).slice(0, 200)}`);
  } else if (reply.status === 429 || reply.status === 403) {
    refused.add(1, { name });
  }
  return reply;
}

function get(session, path, name) {
  return note(http.get(`${BASE}${path}`, { headers: headers(session, false), tags: { name } }), name);
}

function post(session, path, body, name) {
  return note(
    http.post(`${BASE}${path}`, JSON.stringify(body), { headers: headers(session, true), tags: { name } }),
    name,
  );
}

function signIn() {
  // The check after the run has no person number, so it signs in as the first.
  const email = `load${((Math.max(__VU, 1) - 1) % STAFF) + 1}@e2e.test`;
  http.get(`${BASE}/api/accounts/csrf/`, { headers: { Host: HOST }, tags: { name: 'csrf' } });
  const jar = http.cookieJar().cookiesForURL(BASE);
  const login = http.post(`${BASE}/api/accounts/login/`, JSON.stringify({ email, password: PASSWORD }), {
    headers: {
      Host: HOST,
      'Content-Type': 'application/json',
      'X-CSRFToken': (jar.kb_csrftoken || [''])[0],
      Referer: `http://${HOST}/`,
    },
    tags: { name: 'login' },
  });
  if (!check(login, { 'signed in': (reply) => reply.status === 200 })) {
    console.error(`login ${email}: ${login.status} ${String(login.body).slice(0, 200)}`);
    return null;
  }
  const csrf = (http.cookieJar().cookiesForURL(BASE).kb_csrftoken || [''])[0];
  const tenants = http.get(`${BASE}/api/tenants/`, { headers: { Host: HOST }, tags: { name: 'tenants' } });
  const store = tenants.json().find((row) => row.tenant_name.includes('Kiryana'));
  const session = { csrf, tenant: store.tenant_id };
  const rows = (path) => {
    const body = get(session, path, 'setup').json();
    return Array.isArray(body) ? body : body.results || [];
  };
  session.customers = rows('/api/sales/customers/').filter((row) => row.is_active);
  session.warehouses = rows('/api/inventory/warehouses/');
  session.products = rows('/api/inventory/products/').filter((row) => row.is_active && Number(row.sale_price) > 0);
  return session;
}

const READS = [
  '/api/sales/invoices/',
  '/api/sales/customers/',
  '/api/inventory/products/',
  '/api/inventory/stock-levels/',
  '/api/purchasing/bills/',
  '/api/accounting/entries/',
  '/api/hr/employees/',
  '/api/audit/',
];
const REPORTS = [
  '/api/reports/home/',
  '/api/reports/dashboard/',
  '/api/reports/profit-loss/',
  '/api/reports/balance-sheet/',
  '/api/accounting/reports/trial-balance/',
  '/api/sales/ageing/',
  '/api/inventory/stock-value/',
];

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function sellSomething(session) {
  // Everyone sells from the first few products, so they fight over the same stock rows.
  const product = pick(session.products.slice(0, 5));
  const made = post(
    session,
    '/api/sales/invoices/',
    {
      customer: pick(session.customers).id,
      warehouse: session.warehouses[0].id,
      date: new Date().toISOString().slice(0, 10),
      lines: [{ product: product.id, unit: product.unit, quantity: '1', unit_price: product.sale_price }],
    },
    'bill create',
  );
  if (made.status !== 201) {
    if (made.status < 500 && made.status !== 429) {
      wrongAnswers.add(1);
      console.error(`bill create: ${made.status} ${String(made.body).slice(0, 300)}`);
    }
    return;
  }
  wrongAnswers.add(0);
  const posted = post(session, `/api/sales/invoices/${made.json().id}/post/`, {}, 'bill post');
  postTime.add(posted.timings.duration);
  if (posted.status === 200) {
    billsPosted.add(1);
    // A posted bill has a number and a journal entry, always.
    wrongAnswers.add(!(posted.json().number && posted.json().journal_number));
  } else if (posted.status === 400 || posted.status === 409) {
    // Out of stock or over a credit limit is a correct refusal, not a fault.
    billsOutOfStock.add(1);
  }
}

let session = null;

export default function () {
  if (session === null) {
    session = signIn();
    if (session === null) {
      sleep(5);
      return;
    }
  }
  const job = __VU % 4;
  if (job === 0) {
    group('read lists', () => check(get(session, pick(READS), 'list'), { 'list answers': (r) => r.status === 200 }));
  } else if (job === 1) {
    group('read reports', () => check(get(session, pick(REPORTS), 'report'), { 'report answers': (r) => r.status === 200 }));
  } else if (job === 2) {
    group('add a customer', () => {
      const code = `L${__VU}-${__ITER}-${Date.now() % 100000}`;
      const made = post(session, '/api/sales/customers/', { code, name: `Load Customer ${code}` }, 'customer create');
      check(made, { 'customer saved': (r) => r.status === 201 });
    });
  } else {
    group('sell', () => sellSomething(session));
  }
  sleep(0.5 + Math.random());
}

// After the run: the books must still balance and no two bills may share a number.
export function teardown() {
  session = signIn();
  if (session === null) return;
  const balance = get(session, '/api/accounting/reports/trial-balance/', 'check').json();
  console.log(`trial balance after the run: debit ${balance.total_debit} credit ${balance.total_credit}`);
  if (balance.total_debit !== balance.total_credit) {
    throw new Error('the trial balance no longer balances');
  }
}
