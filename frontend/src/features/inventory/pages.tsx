import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Button, Field, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { can, type Product, type StockEntry } from '../../lib/api/types';
import { formatMoney } from '../../lib/money';
import { ensureCsrf } from '../auth/session';
import { errorText, useWorkspace } from '../workspace/hooks';
import { PageTitle, Panel } from '../workspace/ui';

const TABLE = 'w-full text-sm';
const TH = 'label py-3 pe-4 text-start font-normal';
const TD = 'py-3 pe-4 align-top';
const NUM = 'py-3 pe-4 text-end font-mono tabular-nums';
const CELL_INPUT = 'w-full rounded-lg border border-line bg-black/50 px-2 py-2';
type Kind = 'receipt' | 'issue' | 'transfer' | 'adjustment';

function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function formatQuantity(value: string, locale: string | undefined): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(Number(value));
}

function useList<T>(key: string, load: () => Promise<T>) {
  const { membership } = useWorkspace();
  return useQuery({ queryKey: [membership.tenant_id, key], queryFn: load });
}

function useUnits() {
  return useList('units', () => unwrap(api.GET('/api/inventory/units/')));
}

function useWarehouses() {
  return useList('warehouses', () => unwrap(api.GET('/api/inventory/warehouses/')));
}

// Searches as you type and resolves scanned barcodes, so it works the same for 20 products or
// 20,000. A barcode also picks the pack it belongs to (scan a carton, get the carton unit).
function ProductPicker({
  value,
  onPick,
}: {
  value: Product | undefined;
  onPick: (product: Product, unit: number) => void;
}) {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const query = term.trim();
  const barcode = /^\d{6,}$/.test(query);
  const results = useQuery({
    queryKey: [membership.tenant_id, 'product-search', query],
    enabled: open && query.length > 0,
    queryFn: () =>
      unwrap(
        api.GET('/api/inventory/products/', {
          params: {
            query: { ...(barcode ? { barcode: query } : { q: query }), page_size: 8 } as never,
          },
        }),
      ),
  });
  const pick = (product: Product) => {
    const pack = barcode ? product.packs?.find((item) => item.barcode === query) : undefined;
    onPick(product, pack?.unit ?? product.unit);
    setTerm('');
    setOpen(false);
  };
  return (
    <div className="relative">
      <input
        aria-label={t('inv.product')}
        placeholder={value ? `${value.sku} ${value.name}` : t('inv.search')}
        className={`${CELL_INPUT} ${value ? 'placeholder:text-ink' : ''}`}
        value={term}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          setTerm(e.target.value.slice(0, 80));
          setOpen(true);
        }}
        onKeyDown={(e) => {
          const first = results.data?.results[0];
          if (e.key === 'Enter' && first) {
            e.preventDefault();
            pick(first);
          }
        }}
      />
      {open && query && (
        <ul
          className="absolute inset-x-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-xl border border-line bg-raised shadow-xl"
          data-lenis-prevent
        >
          {results.data?.results.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted">{t('workspace.none')}</li>
          )}
          {results.data?.results.map((product) => (
            <li key={product.id}>
              <button
                type="button"
                className="w-full px-3 py-2 text-start text-sm hover:bg-white/5"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(product)}
              >
                <span className="font-mono text-xs text-gold">{product.sku}</span> {product.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function useInventoryAction(keys: string[]) {
  const client = useQueryClient();
  const { membership } = useWorkspace();
  return useMutation({
    mutationFn: async (call: () => Promise<unknown>) => {
      await ensureCsrf();
      return call();
    },
    onSuccess: () =>
      Promise.all(
        keys.map((key) => client.invalidateQueries({ queryKey: [membership.tenant_id, key] })),
      ),
  });
}

export function ProductsPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const units = useUnits();
  const [search, setSearch] = useState('');
  const products = useQuery({
    queryKey: [membership.tenant_id, 'products', search],
    queryFn: () =>
      unwrap(
        api.GET('/api/inventory/products/', {
          params: { query: /^\d{6,}$/.test(search) ? { barcode: search } : { q: search } },
        }),
      ),
  });
  const save = useInventoryAction(['products', 'products-all']);
  const [form, setForm] = useState({ sku: '', name: '', unit: '', reorder: '', batches: false });
  const [pack, setPack] = useState({ unit: '', factor: '', barcode: '' });

  const submit = () => {
    const packs =
      pack.unit && pack.factor
        ? [{ unit: Number(pack.unit), factor: pack.factor, barcode: pack.barcode || null }]
        : [];
    save.mutate(
      () =>
        unwrap(
          api.POST('/api/inventory/products/', {
            body: {
              sku: form.sku,
              name: form.name,
              unit: Number(form.unit),
              reorder_level: form.reorder || '0',
              track_batches: form.batches,
              packs,
            } as never,
          }),
        ),
      {
        onSuccess: () => {
          setForm({ sku: '', name: '', unit: form.unit, reorder: '', batches: false });
          setPack({ unit: '', factor: '', barcode: '' });
        },
      },
    );
  };

  return (
    <>
      <PageTitle title={t('inv.products')} subtitle={t('inv.productsBody')} />
      {can(membership, 'inventory', 'create') && (
        <Panel title={t('inv.newProduct')}>
          {units.data?.length === 0 && <Alert tone="error">{t('inv.needUnits')}</Alert>}
          <form
            className="grid gap-4 md:grid-cols-[9rem_1fr_9rem_9rem]"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <Field
              label={t('inv.sku')}
              required
              maxLength={40}
              value={form.sku}
              onChange={(e) => setForm({ ...form, sku: e.target.value })}
            />
            <Field
              label={t('acc.name')}
              required
              maxLength={150}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <Select
              label={t('inv.baseUnit')}
              required
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
            >
              <option value="">-</option>
              {units.data?.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.code}
                </option>
              ))}
            </Select>
            <Field
              label={t('inv.reorderLevel')}
              inputMode="decimal"
              value={form.reorder}
              onChange={(e) => setForm({ ...form, reorder: e.target.value })}
            />
            <Select
              label={t('inv.packUnit')}
              value={pack.unit}
              onChange={(e) => setPack({ ...pack, unit: e.target.value })}
            >
              <option value="">-</option>
              {units.data?.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.code}
                </option>
              ))}
            </Select>
            <Field
              label={t('inv.packSize')}
              inputMode="decimal"
              value={pack.factor}
              onChange={(e) => setPack({ ...pack, factor: e.target.value })}
            />
            <Field
              label={t('inv.barcode')}
              maxLength={64}
              value={pack.barcode}
              onChange={(e) => setPack({ ...pack, barcode: e.target.value })}
            />
            <label className="flex items-center gap-3 self-end pb-3 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-[var(--color-gold)]"
                checked={form.batches}
                onChange={(e) => setForm({ ...form, batches: e.target.checked })}
              />
              {t('inv.trackBatches')}
            </label>
            <div className="md:col-span-4">
              <Button type="submit" disabled={save.isPending}>
                {t('workspace.save')}
              </Button>
            </div>
          </form>
          {save.isError && (
            <div className="mt-4">
              <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
            </div>
          )}
        </Panel>
      )}
      <Panel
        title={t('inv.products')}
        action={
          <input
            aria-label={t('inv.search')}
            placeholder={t('inv.search')}
            className="rounded-full border border-line bg-black/50 px-4 py-2 text-sm"
            value={search}
            onChange={(e) => setSearch(e.target.value.slice(0, 80))}
          />
        }
      >
        <div className="overflow-x-auto" data-lenis-prevent>
          <table className={TABLE}>
            <thead>
              <tr>
                <th className={TH}>{t('inv.sku')}</th>
                <th className={TH}>{t('acc.name')}</th>
                <th className={TH}>{t('inv.packs')}</th>
                <th className={`${TH} text-end`}>{t('inv.onHand')}</th>
              </tr>
            </thead>
            <tbody>
              {products.data?.results.map((product: Product) => (
                <tr key={product.id} className="border-t border-line">
                  <td className={`${TD} font-mono text-gold`}>{product.sku}</td>
                  <td className={TD}>
                    {product.name}
                    {product.track_batches && (
                      <span className="label ms-2">{t('inv.batched')}</span>
                    )}
                  </td>
                  <td className={`${TD} text-muted`}>
                    {product.unit_code}
                    {product.packs?.map(
                      (item) =>
                        ` · ${item.unit_code} ×${formatQuantity(item.factor, i18n.resolvedLanguage)}`,
                    )}
                  </td>
                  <td className={NUM}>
                    {formatQuantity(product.on_hand, i18n.resolvedLanguage)} {product.unit_code}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

interface DraftLine {
  key: number;
  product: string;
  unit: string;
  quantity: string;
  cost: string;
  batch: string;
  expiry: string;
}

function blank(key: number): DraftLine {
  return { key, product: '', unit: '', quantity: '', cost: '', batch: '', expiry: '' };
}

function StockEditor({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const warehouses = useWarehouses();
  const [picked, setPicked] = useState<Map<string, Product>>(new Map());
  const save = useInventoryAction(['stock-entries']);
  const [kind, setKind] = useState<Kind>('receipt');
  const [date, setDate] = useState(today());
  const [memo, setMemo] = useState('');
  const [warehouse, setWarehouse] = useState('');
  const [destination, setDestination] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([blank(0)]);
  const byId = picked;
  const costed = kind === 'receipt' || kind === 'adjustment';
  const update = (key: number, patch: Partial<DraftLine>) => {
    setLines(lines.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  };

  const submit = () => {
    const body = {
      kind,
      date,
      memo,
      warehouse: Number(warehouse),
      to_warehouse: kind === 'transfer' && destination ? Number(destination) : null,
      lines: lines
        .filter((line) => line.product && line.quantity)
        .map((line) => ({
          product: Number(line.product),
          unit: Number(line.unit || byId.get(line.product)?.unit),
          quantity: line.quantity,
          unit_cost: costed && line.cost ? line.cost : null,
          batch_number: line.batch,
          expiry_date: line.expiry || null,
        })),
    } as never;
    save.mutate(() => unwrap(api.POST('/api/inventory/stock-entries/', { body })), {
      onSuccess: onDone,
    });
  };

  return (
    <Panel title={t('inv.newEntry')}>
      <div className="grid gap-4 md:grid-cols-4">
        <Select
          label={t('acc.type')}
          value={kind}
          onChange={(e) => setKind(e.target.value as Kind)}
        >
          {(['receipt', 'issue', 'transfer', 'adjustment'] as const).map((value) => (
            <option key={value} value={value}>
              {t(`inv.kinds.${value}`)}
            </option>
          ))}
        </Select>
        <Field
          label={t('acc.date')}
          type="date"
          required
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <Select
          label={kind === 'transfer' ? t('inv.from') : t('inv.warehouse')}
          required
          value={warehouse}
          onChange={(e) => setWarehouse(e.target.value)}
        >
          <option value="">-</option>
          {warehouses.data?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.code} {item.name}
            </option>
          ))}
        </Select>
        {kind === 'transfer' ? (
          <Select
            label={t('inv.to')}
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
          >
            <option value="">-</option>
            {warehouses.data
              ?.filter((item) => String(item.id) !== warehouse)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.code} {item.name}
                </option>
              ))}
          </Select>
        ) : (
          <Field
            label={t('acc.memo')}
            maxLength={255}
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
          />
        )}
      </div>
      <p className="mt-4 text-xs text-muted">{t(`inv.kindHelp.${kind}`)}</p>
      <div className="mt-4 overflow-x-auto" data-lenis-prevent>
        <table className={`${TABLE} min-w-[44rem]`}>
          <thead>
            <tr>
              <th className={TH}>{t('inv.product')}</th>
              <th className={TH}>{t('inv.unit')}</th>
              <th className={TH}>{kind === 'adjustment' ? t('inv.counted') : t('inv.quantity')}</th>
              {costed && <th className={TH}>{t('inv.unitCost')}</th>}
              <th className={TH}>{t('inv.batch')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const product = byId.get(line.product);
              return (
                <tr key={line.key} className="border-t border-line">
                  <td className="py-2 pe-2">
                    <ProductPicker
                      value={product}
                      onPick={(chosen, unit) => {
                        setPicked(new Map(picked).set(String(chosen.id), chosen));
                        update(line.key, { product: String(chosen.id), unit: String(unit) });
                      }}
                    />
                  </td>
                  <td className="w-28 py-2 pe-2">
                    <select
                      aria-label={t('inv.unit')}
                      className={CELL_INPUT}
                      value={line.unit || String(product?.unit ?? '')}
                      onChange={(e) => update(line.key, { unit: e.target.value })}
                    >
                      {product && <option value={product.unit}>{product.unit_code}</option>}
                      {product?.packs?.map((item) => (
                        <option key={item.unit} value={item.unit}>
                          {item.unit_code}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="w-28 py-2 pe-2">
                    <input
                      aria-label={t('inv.quantity')}
                      inputMode="decimal"
                      className={`${CELL_INPUT} text-end font-mono`}
                      value={line.quantity}
                      onChange={(e) => update(line.key, { quantity: e.target.value })}
                    />
                  </td>
                  {costed && (
                    <td className="w-32 py-2 pe-2">
                      <input
                        aria-label={t('inv.unitCost')}
                        inputMode="decimal"
                        className={`${CELL_INPUT} text-end font-mono`}
                        value={line.cost}
                        onChange={(e) => update(line.key, { cost: e.target.value })}
                      />
                    </td>
                  )}
                  <td className="py-2 pe-2">
                    {product?.track_batches ? (
                      <div className="flex gap-2">
                        <input
                          aria-label={t('inv.batch')}
                          maxLength={40}
                          className={CELL_INPUT}
                          value={line.batch}
                          onChange={(e) => update(line.key, { batch: e.target.value })}
                        />
                        {(kind === 'receipt' || kind === 'adjustment') && (
                          <input
                            aria-label={t('inv.expiry')}
                            type="date"
                            className={CELL_INPUT}
                            value={line.expiry}
                            onChange={(e) => update(line.key, { expiry: e.target.value })}
                          />
                        )}
                      </div>
                    ) : (
                      <span className="text-muted">-</span>
                    )}
                  </td>
                  <td className="py-2">
                    <button
                      type="button"
                      aria-label={t('workspace.remove')}
                      className="px-2 text-muted hover:text-coral disabled:opacity-30"
                      disabled={lines.length <= 1}
                      onClick={() => setLines(lines.filter((item) => item.key !== line.key))}
                    >
                      &times;
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          variant="ghost"
          onClick={() => setLines([...lines, blank(Math.max(...lines.map((l) => l.key)) + 1)])}
        >
          {t('acc.addLine')}
        </Button>
        <Button disabled={save.isPending || !warehouse} onClick={submit}>
          {t('acc.saveDraft')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('workspace.cancel')}
        </Button>
      </div>
      {save.isError && (
        <div className="mt-4">
          <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
        </div>
      )}
    </Panel>
  );
}

function EntryRow({ entry }: { entry: StockEntry }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const [open, setOpen] = useState(false);
  const action = useInventoryAction(['stock-entries', 'levels', 'products', 'alerts']);
  const posted = entry.status === 'posted';
  return (
    <li className="border-t border-line">
      <button
        type="button"
        className="grid w-full grid-cols-[1fr_auto] gap-3 py-4 text-start sm:grid-cols-[9rem_8rem_7rem_1fr]"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="font-mono text-sm">{entry.number ?? t('acc.draft')}</span>
        <span className="label self-center">{t(`inv.kinds.${entry.kind}`)}</span>
        <span className="hidden text-sm text-muted sm:block">{entry.date}</span>
        <span className="hidden truncate sm:block">
          {entry.memo || `${entry.lines.length} ${t('inv.lines')}`}
        </span>
      </button>
      {open && (
        <div className="space-y-4 pb-6">
          <div className="overflow-x-auto" data-lenis-prevent>
            <table className={TABLE}>
              <tbody>
                {entry.lines.map((line) => (
                  <tr key={line.id} className="border-t border-line">
                    <td className={TD}>
                      <span className="font-mono text-xs text-gold">{line.sku}</span>{' '}
                      {line.product_name}
                      {line.batch_number && <span className="label ms-2">{line.batch_number}</span>}
                    </td>
                    <td className={NUM}>
                      {formatQuantity(line.quantity, i18n.resolvedLanguage)} {line.unit_code}
                    </td>
                    <td className={NUM}>
                      {line.unit_cost
                        ? new Intl.NumberFormat(i18n.resolvedLanguage, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 4,
                          }).format(Number(line.unit_cost))
                        : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {entry.journal_number && (
            <p className="label">{t('inv.postedAs', { number: entry.journal_number })}</p>
          )}
          {action.isError && (
            <Alert tone="error">{errorText(action.error, t('signIn.unavailable'))}</Alert>
          )}
          {!posted && (
            <div className="flex flex-wrap gap-3">
              {can(membership, 'inventory', 'post') && (
                <Button
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate(() =>
                      unwrap(
                        api.POST('/api/inventory/stock-entries/{id}/post/', {
                          params: { path: { id: entry.id } },
                        }),
                      ),
                    )
                  }
                >
                  {t('acc.post')}
                </Button>
              )}
              {can(membership, 'inventory', 'delete') && (
                <Button
                  variant="danger"
                  onClick={() =>
                    action.mutate(() =>
                      unwrap(
                        api.DELETE('/api/inventory/stock-entries/{id}/', {
                          params: { path: { id: entry.id } },
                        }),
                      ),
                    )
                  }
                >
                  {t('workspace.remove')}
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function StockEntriesPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const [creating, setCreating] = useState(false);
  const entries = useList('stock-entries', () => unwrap(api.GET('/api/inventory/stock-entries/')));
  return (
    <>
      <PageTitle title={t('inv.entries')} subtitle={t('inv.entriesBody')} />
      {creating ? (
        <StockEditor onDone={() => setCreating(false)} />
      ) : (
        can(membership, 'inventory', 'create') && (
          <Button onClick={() => setCreating(true)}>{t('inv.newEntry')}</Button>
        )
      )}
      <Panel title={t('acc.entries')}>
        <ul>
          {entries.data?.results.length === 0 && (
            <li className="py-4 text-sm text-muted">{t('workspace.none')}</li>
          )}
          {entries.data?.results.map((entry) => (
            <EntryRow key={entry.id} entry={entry} />
          ))}
        </ul>
      </Panel>
    </>
  );
}

export function StockOnHandPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const warehouses = useWarehouses();
  const [warehouse, setWarehouse] = useState('');
  const filter = warehouse ? { warehouse: Number(warehouse) } : {};
  const levels = useInfiniteQuery({
    queryKey: [membership.tenant_id, 'levels', warehouse],
    initialPageParam: '',
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/inventory/stock-levels/', {
          params: { query: { ...filter, ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
    getNextPageParam: (page) =>
      page.next ? (new URL(page.next).searchParams.get('cursor') ?? undefined) : undefined,
  });
  // The total comes from the server so it covers every row, not just the pages loaded so far.
  const value = useQuery({
    queryKey: [membership.tenant_id, 'levels', 'value', warehouse],
    queryFn: () => unwrap(api.GET('/api/inventory/stock-value/', { params: { query: filter } })),
  });
  const rows = levels.data?.pages.flatMap((page) => page.results) ?? [];
  return (
    <>
      <PageTitle title={t('inv.onHandTitle')} subtitle={t('inv.onHandBody')} />
      <Panel
        title={t('inv.levels')}
        action={
          <select
            aria-label={t('inv.warehouse')}
            className="rounded-full border border-line bg-black/50 px-4 py-2 text-sm"
            value={warehouse}
            onChange={(e) => setWarehouse(e.target.value)}
          >
            <option value="">{t('inv.allWarehouses')}</option>
            {warehouses.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.code}
              </option>
            ))}
          </select>
        }
      >
        <div className="overflow-x-auto" data-lenis-prevent>
          <table className={TABLE}>
            <thead>
              <tr>
                <th className={TH}>{t('inv.sku')}</th>
                <th className={TH}>{t('inv.product')}</th>
                <th className={TH}>{t('inv.warehouse')}</th>
                <th className={`${TH} text-end`}>{t('inv.quantity')}</th>
                <th className={`${TH} text-end`}>{t('inv.value')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className={`${TD} font-mono text-gold`}>{row.sku}</td>
                  <td className={TD}>{row.product_name}</td>
                  <td className={TD}>{row.warehouse_code}</td>
                  <td className={NUM}>
                    {formatQuantity(row.quantity, i18n.resolvedLanguage)} {row.unit_code}
                  </td>
                  <td className={NUM}>{formatMoney(row.value, i18n.resolvedLanguage)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-gold/40 text-gold">
                <td className={TD} colSpan={4}>
                  {t('inv.totalValue')}
                </td>
                <td className={NUM}>
                  {formatMoney(value.data?.total_value ?? '0', i18n.resolvedLanguage)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        {levels.hasNextPage && (
          <div className="mt-4">
            <Button
              variant="ghost"
              disabled={levels.isFetchingNextPage}
              onClick={() => void levels.fetchNextPage()}
            >
              {t('inv.loadMore', { shown: rows.length, total: value.data?.lines ?? rows.length })}
            </Button>
          </div>
        )}
      </Panel>
    </>
  );
}

interface LowRow {
  product: number;
  sku: string;
  name: string;
  on_hand: string;
  reorder_level: string;
}

interface ExpiringRow {
  batch: number;
  product: string;
  number: string;
  warehouse: string;
  quantity: string;
  expiry_date: string;
}

export function AlertsPage() {
  const { t, i18n } = useTranslation();
  const alerts = useList('alerts', () => unwrap(api.GET('/api/inventory/alerts/')));
  const low = (alerts.data?.low_stock ?? []) as unknown as LowRow[];
  const expiring = (alerts.data?.expiring ?? []) as unknown as ExpiringRow[];
  return (
    <>
      <PageTitle title={t('inv.alerts')} subtitle={t('inv.alertsBody')} />
      <Panel title={t('inv.lowStock')}>
        <ul>
          {low.length === 0 && <li className="py-3 text-sm text-muted">{t('workspace.none')}</li>}
          {low.map((row) => (
            <li key={row.product} className="flex justify-between gap-4 border-t border-line py-3">
              <span>
                <span className="font-mono text-xs text-gold">{row.sku}</span> {row.name}
              </span>
              <span className="font-mono text-sm text-coral">
                {formatQuantity(row.on_hand, i18n.resolvedLanguage)} /{' '}
                {formatQuantity(row.reorder_level, i18n.resolvedLanguage)}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title={t('inv.expiring')}>
        <ul>
          {expiring.length === 0 && (
            <li className="py-3 text-sm text-muted">{t('workspace.none')}</li>
          )}
          {expiring.map((row) => (
            <li
              key={`${row.batch}-${row.warehouse}`}
              className="flex flex-wrap justify-between gap-4 border-t border-line py-3"
            >
              <span>
                {row.product} <span className="label ms-2">{row.number}</span>{' '}
                <span className="label ms-2">{row.warehouse}</span>
              </span>
              <span className="font-mono text-sm text-yellow">
                {formatQuantity(row.quantity, i18n.resolvedLanguage)} · {row.expiry_date}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}

export function InventorySetupPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const units = useUnits();
  const warehouses = useWarehouses();
  const save = useInventoryAction(['units', 'warehouses']);
  const [unit, setUnit] = useState({ code: '', name: '' });
  const [store, setStore] = useState({ code: '', name: '' });
  const allowed = can(membership, 'inventory', 'create');
  return (
    <>
      <PageTitle title={t('inv.setup')} subtitle={t('inv.setupBody')} />
      {save.isError && <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={t('inv.units')}>
          <ul className="mb-5">
            {units.data?.map((item) => (
              <li key={item.id} className="flex gap-4 border-t border-line py-2.5">
                <span className="w-16 font-mono text-gold">{item.code}</span> {item.name}
              </li>
            ))}
          </ul>
          {allowed && (
            <form
              className="grid grid-cols-[6rem_1fr_auto] items-end gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                save.mutate(
                  () => unwrap(api.POST('/api/inventory/units/', { body: unit as never })),
                  { onSuccess: () => setUnit({ code: '', name: '' }) },
                );
              }}
            >
              <Field
                label={t('acc.code')}
                required
                maxLength={10}
                value={unit.code}
                onChange={(e) => setUnit({ ...unit, code: e.target.value })}
              />
              <Field
                label={t('acc.name')}
                required
                maxLength={50}
                value={unit.name}
                onChange={(e) => setUnit({ ...unit, name: e.target.value })}
              />
              <Button type="submit">{t('workspace.save')}</Button>
            </form>
          )}
        </Panel>
        <Panel title={t('inv.warehouses')}>
          <ul className="mb-5">
            {warehouses.data?.map((item) => (
              <li key={item.id} className="flex gap-4 border-t border-line py-2.5">
                <span className="w-16 font-mono text-gold">{item.code}</span> {item.name}
              </li>
            ))}
          </ul>
          {allowed && (
            <form
              className="grid grid-cols-[6rem_1fr_auto] items-end gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                save.mutate(
                  () => unwrap(api.POST('/api/inventory/warehouses/', { body: store as never })),
                  { onSuccess: () => setStore({ code: '', name: '' }) },
                );
              }}
            >
              <Field
                label={t('acc.code')}
                required
                maxLength={20}
                value={store.code}
                onChange={(e) => setStore({ ...store, code: e.target.value })}
              />
              <Field
                label={t('acc.name')}
                required
                maxLength={100}
                value={store.name}
                onChange={(e) => setStore({ ...store, name: e.target.value })}
              />
              <Button type="submit">{t('workspace.save')}</Button>
            </form>
          )}
        </Panel>
      </div>
    </>
  );
}
