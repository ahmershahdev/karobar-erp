import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Field, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { today } from '../../lib/dates';
import { formatMoney, toMinor } from '../../lib/money';
import { ActionError } from '../purchasing/pages';
import { PrintButton } from '../sales/ledgers';
import { useTenantAction, useWorkspace } from '../workspace/hooks';
import { PageTitle, Panel } from '../workspace/ui';

const KEYS = ['pos', 'levels', 'products', 'invoices'];

interface Found {
  id: number;
  sku: string;
  name: string;
  unit: number;
  unit_code: string;
  price: string | null;
  exact: boolean;
}

interface CartLine extends Found {
  quantity: number;
}

interface Till {
  id: number;
  warehouse_name: string;
  opening_float: string;
  sales_count: number;
  cash_sales: string;
  card_sales: string;
  expected_cash: string | null;
  difference: string | null;
}

interface Done {
  id: number;
  number: string;
  amount: string;
  change: string;
}

// What the screen shows before the sale is sent. The server works the real figures out again,
// and those are what the receipt and the books use.
function linePaisa(line: CartLine): number {
  return Math.round(Number(line.price) * line.quantity * 100);
}

function taxPaisa(amount: number, percent: number): number {
  return Math.round((amount * percent) / 100);
}

function OpenTill() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const save = useTenantAction(KEYS);
  const warehouses = useQuery({
    queryKey: [membership.tenant_id, 'pos', 'warehouses'],
    queryFn: () => unwrap(api.GET('/api/pos/warehouses/')),
  });
  const [warehouse, setWarehouse] = useState('');
  const [opening, setOpening] = useState('');
  return (
    <Panel title={t('pos.startDay')}>
      <p className="mb-4 text-muted">{t('pos.startDayBody')}</p>
      <div className="grid gap-4 md:max-w-xl md:grid-cols-2">
        <Select
          label={t('inv.warehouse')}
          required
          value={warehouse}
          onChange={(e) => setWarehouse(e.target.value)}
        >
          <option value="">-</option>
          {warehouses.data?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </Select>
        <Field
          label={t('pos.cashInDrawer')}
          inputMode="decimal"
          value={opening}
          onChange={(e) => setOpening(e.target.value)}
        />
      </div>
      <div className="mt-4">
        <Button
          disabled={save.isPending || !warehouse}
          onClick={() => {
            const body = {
              warehouse: Number(warehouse),
              opening_float: opening || '0',
            } as never;
            save.mutate(() => unwrap(api.POST('/api/pos/sessions/', { body })));
          }}
        >
          {t('pos.openTill')}
        </Button>
      </div>
      <div className="mt-4">
        <ActionError error={save.error} />
      </div>
    </Panel>
  );
}

function CloseTill({ till, onClosed }: { till: Till; onClosed: (closed: Till) => void }) {
  const { t, i18n } = useTranslation();
  const save = useTenantAction(KEYS);
  const [counted, setCounted] = useState('');
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  return (
    <Panel title={t('pos.endDay')}>
      <dl className="mb-4 grid gap-2 text-sm sm:max-w-sm">
        <div className="flex justify-between">
          <dt className="text-muted">{t('pos.salesCount')}</dt>
          <dd>{till.sales_count}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">{t('pos.cashSales')}</dt>
          <dd className="font-mono">{money(till.cash_sales)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">{t('pos.cardSales')}</dt>
          <dd className="font-mono">{money(till.card_sales)}</dd>
        </div>
      </dl>
      <div className="sm:max-w-sm">
        <Field
          label={t('pos.countedCash')}
          hint={t('pos.countedHint')}
          inputMode="decimal"
          required
          value={counted}
          onChange={(e) => setCounted(e.target.value)}
        />
      </div>
      <div className="mt-4">
        <Button
          disabled={save.isPending || counted === ''}
          onClick={() => {
            const body = { counted_cash: counted } as never;
            save.mutate(async () => {
              const closed = await unwrap(
                api.POST('/api/pos/sessions/{id}/close/', {
                  params: { path: { id: till.id } },
                  body,
                }),
              );
              onClosed(closed);
            });
          }}
        >
          {t('pos.closeTill')}
        </Button>
      </div>
      <div className="mt-4">
        <ActionError error={save.error} />
      </div>
    </Panel>
  );
}

function Counter({ till }: { till: Till }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const sale = useTenantAction(KEYS);
  const search = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState('');
  const [cart, setCart] = useState<CartLine[]>([]);
  const [rate, setRate] = useState('');
  const [given, setGiven] = useState('');
  const [done, setDone] = useState<Done | null>(null);
  const [notFound, setNotFound] = useState(false);
  const money = (value: string | number) => formatMoney(value, i18n.resolvedLanguage);

  const rates = useQuery({
    queryKey: [membership.tenant_id, 'pos', 'tax-rates'],
    queryFn: () => unwrap(api.GET('/api/pos/tax-rates/')),
  });
  const now = today();
  const usable = rates.data?.filter(
    (item) => item.valid_from <= now && (!item.valid_to || now <= item.valid_to),
  );
  const chosen = usable?.find((item) => String(item.id) === rate);

  const lookup = (q: string) =>
    unwrap(api.GET('/api/pos/products/', { params: { query: { q } } })) as Promise<Found[]>;
  const results = useQuery({
    queryKey: [membership.tenant_id, 'pos', 'search', term],
    enabled: term.trim().length >= 2,
    queryFn: () => lookup(term.trim()),
  });

  const add = (item: Found) => {
    setCart((lines) => {
      const same = lines.find((line) => line.id === item.id && line.unit === item.unit);
      return same
        ? lines.map((line) => (line === same ? { ...line, quantity: line.quantity + 1 } : line))
        : [...lines, { ...item, quantity: 1 }];
    });
    setTerm('');
    setNotFound(false);
    search.current?.focus();
  };

  // A scanner types the code and presses Enter, so Enter on one exact match adds it at once.
  const scan = async () => {
    const q = term.trim();
    if (!q) return;
    const found = await lookup(q);
    const only = found.length === 1 ? found[0] : undefined;
    if (only) add(only);
    else if (found.length === 0) setNotFound(true);
  };

  const setQuantity = (line: CartLine, quantity: number) =>
    setCart((lines) =>
      quantity <= 0
        ? lines.filter((item) => item !== line)
        : lines.map((item) => (item === line ? { ...item, quantity } : item)),
    );

  const net = cart.reduce((sum, line) => sum + linePaisa(line), 0);
  const tax = chosen
    ? cart.reduce((sum, line) => sum + taxPaisa(linePaisa(line), Number(chosen.rate)), 0)
    : 0;
  const total = net + tax;
  const change = toMinor(given) - total;
  const priceless = cart.some((line) => line.price === null);

  const pay = (method: 'cash' | 'card') => {
    const body = {
      lines: cart.map((line) => ({
        product: line.id,
        unit: line.unit,
        quantity: String(line.quantity),
      })),
      method,
      tendered: method === 'cash' && given ? given : null,
      tax_rate: rate ? Number(rate) : null,
    } as never;
    sale.mutate(async () => {
      const result = await unwrap(
        api.POST('/api/pos/sessions/{id}/sale/', { params: { path: { id: till.id } }, body }),
      );
      setDone(result);
      setCart([]);
      setGiven('');
    });
  };

  const next = () => {
    setDone(null);
    sale.reset();
    window.setTimeout(() => search.current?.focus(), 0);
  };

  if (done) {
    return (
      <Panel title={t('pos.saleDone')}>
        <p className="text-muted">{done.number}</p>
        <p className="mt-2 text-4xl font-medium tabular-nums">{money(done.amount)}</p>
        {Number(done.change) > 0 && (
          <p className="mt-4 text-2xl">
            {t('pos.giveBack')}{' '}
            <span className="font-medium tabular-nums">{money(done.change)}</span>
          </p>
        )}
        <div className="mt-6 flex flex-wrap gap-3">
          <Button onClick={next}>{t('pos.nextCustomer')}</Button>
          <PrintButton path={`/api/pos/sales/${done.id}/receipt/`} />
        </div>
      </Panel>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div className="space-y-4">
        <label className="block space-y-2">
          <span className="label">{t('pos.scan')}</span>
          <input
            ref={search}
            autoFocus
            value={term}
            onChange={(e) => {
              setTerm(e.target.value);
              setNotFound(false);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void scan();
              }
            }}
            className="w-full rounded-xl border border-line bg-canvas px-4 py-4 text-lg outline-none focus:border-ink"
          />
        </label>
        {notFound && <p className="text-red">{t('pos.notFound')}</p>}
        {term.trim().length >= 2 && (results.data?.length ?? 0) > 0 && (
          <ul className="divide-y divide-line rounded-xl border border-line">
            {results.data?.map((item) => (
              <li key={`${item.id}-${item.unit}`}>
                <button
                  type="button"
                  onClick={() => add(item)}
                  className="flex min-h-12 w-full items-center justify-between gap-4 px-4 py-2 text-start hover:bg-surface"
                >
                  <span>
                    {item.name} <span className="text-sm text-muted">{item.unit_code}</span>
                  </span>
                  <span className="font-mono text-sm">
                    {item.price === null ? t('pos.noPrice') : money(item.price)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <Panel title={t('pos.thisSale')}>
          {cart.length === 0 ? (
            <p className="text-muted">{t('pos.empty')}</p>
          ) : (
            <ul className="divide-y divide-line">
              {cart.map((line) => (
                <li key={`${line.id}-${line.unit}`} className="flex items-center gap-3 py-3">
                  <span className="min-w-0 flex-1 truncate">
                    {line.name} <span className="text-sm text-muted">{line.unit_code}</span>
                  </span>
                  <button
                    type="button"
                    aria-label={t('pos.less')}
                    className="size-11 rounded-full border border-line-strong text-lg"
                    onClick={() => setQuantity(line, line.quantity - 1)}
                  >
                    &minus;
                  </button>
                  <span className="w-8 text-center tabular-nums">{line.quantity}</span>
                  <button
                    type="button"
                    aria-label={t('pos.more')}
                    className="size-11 rounded-full border border-line-strong text-lg"
                    onClick={() => setQuantity(line, line.quantity + 1)}
                  >
                    +
                  </button>
                  <span className="w-24 text-end font-mono text-sm tabular-nums">
                    {line.price === null ? t('pos.noPrice') : money(linePaisa(line))}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="space-y-4">
        <Panel title={t('pos.toPay')}>
          <p className="text-4xl font-medium tabular-nums">{money(total)}</p>
          {tax > 0 && (
            <p className="mt-1 text-sm text-muted">
              {t('pur.tax')}: {money(tax)}
            </p>
          )}
          <div className="mt-4 space-y-4">
            {(usable?.length ?? 0) > 0 && (
              <Select label={t('pur.tax')} value={rate} onChange={(e) => setRate(e.target.value)}>
                <option value="">{t('pos.noTax')}</option>
                {usable?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} {Number(item.rate)}%
                  </option>
                ))}
              </Select>
            )}
            <Field
              label={t('pos.cashGiven')}
              inputMode="decimal"
              value={given}
              onChange={(e) => setGiven(e.target.value)}
            />
            {given !== '' && change >= 0 && (
              <p>
                {t('pos.giveBack')}{' '}
                <span className="font-medium tabular-nums">{money(change)}</span>
              </p>
            )}
            {given !== '' && change < 0 && <p className="text-red">{t('pos.notEnough')}</p>}
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                disabled={
                  sale.isPending || cart.length === 0 || priceless || (given !== '' && change < 0)
                }
                onClick={() => pay('cash')}
                className="btn btn-primary !min-h-16 !text-lg disabled:opacity-40"
              >
                {t('pos.cash')}
              </button>
              <button
                type="button"
                disabled={sale.isPending || cart.length === 0 || priceless}
                onClick={() => pay('card')}
                className="btn btn-ghost !min-h-16 !text-lg disabled:opacity-40"
              >
                {t('pos.card')}
              </button>
            </div>
            {priceless && <p className="text-sm text-red">{t('pos.needsPrice')}</p>}
            <ActionError error={sale.error} />
          </div>
        </Panel>
      </div>
    </div>
  );
}

export function PosPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const [closing, setClosing] = useState(false);
  const [closed, setClosed] = useState<Till | null>(null);
  const client = useQueryClient();
  const tills = useQuery({
    queryKey: [membership.tenant_id, 'pos', 'open-tills'],
    queryFn: () => unwrap(api.GET('/api/pos/sessions/', { params: { query: { status: 'open' } } })),
  });
  const till = (tills.data as Till[] | undefined)?.[0];
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);

  return (
    <>
      <PageTitle title={t('pos.title')} subtitle={till?.warehouse_name ?? t('pos.body')} />
      {closed && (
        <Panel title={t('pos.dayClosed')}>
          <p>
            {Number(closed.difference) === 0
              ? t('pos.exact')
              : t(Number(closed.difference) < 0 ? 'pos.short' : 'pos.over', {
                  amount: money(String(Math.abs(Number(closed.difference)))),
                })}
          </p>
        </Panel>
      )}
      {tills.isPending ? null : !till ? (
        <OpenTill />
      ) : closing ? (
        <>
          <CloseTill
            till={till}
            onClosed={(result) => {
              setClosed(result);
              setClosing(false);
              void client.invalidateQueries({ queryKey: [membership.tenant_id, 'pos'] });
            }}
          />
          <Button variant="ghost" onClick={() => setClosing(false)}>
            {t('workspace.cancel')}
          </Button>
        </>
      ) : (
        <>
          <Counter till={till} />
          <Button variant="ghost" onClick={() => setClosing(true)}>
            {t('pos.endDay')}
          </Button>
        </>
      )}
    </>
  );
}
