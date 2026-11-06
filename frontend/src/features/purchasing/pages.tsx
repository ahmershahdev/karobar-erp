import { useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Button, Field, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import {
  can,
  type Account,
  type Bill,
  type GoodsReceipt,
  type Product,
  type PurchaseOrder,
  type Supplier,
  type SupplierPayment,
} from '../../lib/api/types';
import { today } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { ProductPicker } from '../inventory/ProductPicker';
import { formatQuantity, useWarehouses } from '../inventory/shared';
import { errorText, useTenantAction, useWorkspace } from '../workspace/hooks';
import { CELL_INPUT, NUM, TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';

// Query keys a purchase can change. Posting a receipt moves stock, and bills and payments
// change supplier balances, so every action refreshes all of them.
const KEYS = ['suppliers', 'orders', 'receipts', 'bills', 'payments', 'levels', 'products'];

function useSuppliers() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'suppliers'],
    queryFn: () => unwrap(api.GET('/api/purchasing/suppliers/', { params: { query: {} } })),
  });
}

function useAccounts() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'accounts'],
    queryFn: () => unwrap(api.GET('/api/accounting/accounts/')),
  });
}

function postable(accounts: Account[] | undefined, type: string): Account[] {
  return (accounts ?? []).filter(
    (account) => account.type === type && !account.is_group && account.is_active !== false,
  );
}

function SupplierSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const { t } = useTranslation();
  const suppliers = useSuppliers();
  return (
    <Select
      label={t('pur.supplier')}
      required
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">-</option>
      {suppliers.data?.results
        .filter((item) => item.is_active !== false)
        .map((item) => (
          <option key={item.id} value={item.id}>
            {item.code} {item.name}
          </option>
        ))}
    </Select>
  );
}

function ActionError({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  return <Alert tone="error">{errorText(error, t('signIn.unavailable'))}</Alert>;
}

function RemoveLine({ disabled, onClick }: { disabled?: boolean; onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      aria-label={t('workspace.remove')}
      className="px-2 text-muted hover:text-coral disabled:opacity-30"
      disabled={disabled}
      onClick={onClick}
    >
      &times;
    </button>
  );
}

function NumberCell({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <input
      aria-label={label}
      inputMode="decimal"
      className={`${CELL_INPUT} text-end font-mono`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// A row in a document list: summary line, then the detail and actions when opened.
function DocumentRow({
  number,
  date,
  party,
  amount,
  status,
  children,
}: {
  number: string | null | undefined;
  date: string;
  party: string;
  amount?: string;
  status: string;
  children: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <li className="border-t border-line">
      <button
        type="button"
        className="grid w-full grid-cols-[1fr_auto] gap-3 py-4 text-start sm:grid-cols-[9rem_7rem_1fr_8rem_7rem]"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="font-mono text-sm">{number ?? t('acc.draft')}</span>
        <span className="label self-center sm:order-last">{t(`pur.status.${status}`)}</span>
        <span className="hidden text-sm text-muted sm:block">{date}</span>
        <span className="hidden truncate sm:block">{party}</span>
        <span className="hidden text-end font-mono tabular-nums sm:block">
          {amount ? formatMoney(amount, i18n.resolvedLanguage) : ''}
        </span>
      </button>
      {open && <div className="space-y-4 pb-6">{children}</div>}
    </li>
  );
}

function DocumentList<T extends { id: number }>({
  title,
  rows,
  render,
}: {
  title: string;
  rows: T[] | undefined;
  render: (row: T) => ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <Panel title={title}>
      <ul>
        {rows?.length === 0 && <li className="py-4 text-sm text-muted">{t('workspace.none')}</li>}
        {rows?.map(render)}
      </ul>
    </Panel>
  );
}

// Suppliers

export function SuppliersPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const suppliers = useSuppliers();
  const save = useTenantAction(KEYS);
  const empty = { code: '', name: '', phone: '', email: '', tax_number: '', terms: '0' };
  const [form, setForm] = useState(empty);
  const set = (patch: Partial<typeof empty>) => setForm({ ...form, ...patch });

  return (
    <>
      <PageTitle title={t('pur.suppliers')} subtitle={t('pur.suppliersBody')} />
      {can(membership, 'purchasing', 'create') && (
        <Panel title={t('pur.newSupplier')}>
          <form
            className="grid gap-4 md:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              const body = {
                code: form.code,
                name: form.name,
                phone: form.phone,
                email: form.email,
                tax_number: form.tax_number,
                payment_terms_days: Number(form.terms) || 0,
              } as never;
              save.mutate(() => unwrap(api.POST('/api/purchasing/suppliers/', { body })), {
                onSuccess: () => setForm(empty),
              });
            }}
          >
            <Field
              label={t('pur.code')}
              required
              maxLength={20}
              value={form.code}
              onChange={(e) => set({ code: e.target.value })}
            />
            <Field
              label={t('pur.name')}
              required
              maxLength={150}
              value={form.name}
              onChange={(e) => set({ name: e.target.value })}
            />
            <Field
              label={t('pur.phone')}
              maxLength={30}
              value={form.phone}
              onChange={(e) => set({ phone: e.target.value })}
            />
            <Field
              label={t('pur.email')}
              type="email"
              value={form.email}
              onChange={(e) => set({ email: e.target.value })}
            />
            <Field
              label={t('pur.taxNumber')}
              maxLength={40}
              value={form.tax_number}
              onChange={(e) => set({ tax_number: e.target.value })}
            />
            <Field
              label={t('pur.terms')}
              type="number"
              min={0}
              max={365}
              value={form.terms}
              onChange={(e) => set({ terms: e.target.value })}
            />
            <div className="md:col-span-3">
              <Button type="submit" disabled={save.isPending}>
                {t('pur.addSupplier')}
              </Button>
            </div>
          </form>
          <div className="mt-4">
            <ActionError error={save.error} />
          </div>
        </Panel>
      )}
      <Panel title={t('pur.suppliers')}>
        <div className="overflow-x-auto" data-lenis-prevent>
          <table className={TABLE}>
            <thead>
              <tr>
                <th className={TH}>{t('pur.code')}</th>
                <th className={TH}>{t('pur.name')}</th>
                <th className={TH}>{t('pur.phone')}</th>
                <th className={`${TH} text-end`}>{t('pur.terms')}</th>
                <th className={`${TH} text-end`}>{t('pur.balance')}</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.data?.results.map((item: Supplier) => (
                <tr key={item.id} className="border-t border-line">
                  <td className={`${TD} font-mono text-xs text-gold`}>{item.code}</td>
                  <td className={TD}>{item.name}</td>
                  <td className={`${TD} text-muted`}>{item.phone}</td>
                  <td className={NUM}>{item.payment_terms_days}</td>
                  <td className={NUM}>{formatMoney(item.balance ?? '0', i18n.resolvedLanguage)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

// Purchase orders and receipts without an order share one line editor.

interface ItemLine {
  key: number;
  product: string;
  unit: string;
  quantity: string;
  price: string;
}

function itemLine(key: number): ItemLine {
  return { key, product: '', unit: '', quantity: '', price: '' };
}

function ItemsEditor({
  lines,
  onChange,
  priceLabel,
}: {
  lines: ItemLine[];
  onChange: (lines: ItemLine[]) => void;
  priceLabel: string;
}) {
  const { t } = useTranslation();
  const [picked, setPicked] = useState<Map<string, Product>>(new Map());
  const update = (key: number, patch: Partial<ItemLine>) =>
    onChange(lines.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  return (
    <>
      <div className="overflow-x-auto" data-lenis-prevent>
        <table className={`${TABLE} min-w-[40rem]`}>
          <thead>
            <tr>
              <th className={TH}>{t('inv.product')}</th>
              <th className={TH}>{t('inv.unit')}</th>
              <th className={TH}>{t('inv.quantity')}</th>
              <th className={TH}>{priceLabel}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const product = picked.get(line.product);
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
                      value={line.unit}
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
                    <NumberCell
                      label={t('inv.quantity')}
                      value={line.quantity}
                      onChange={(quantity) => update(line.key, { quantity })}
                    />
                  </td>
                  <td className="w-32 py-2 pe-2">
                    <NumberCell
                      label={priceLabel}
                      value={line.price}
                      onChange={(price) => update(line.key, { price })}
                    />
                  </td>
                  <td className="py-2">
                    <RemoveLine
                      disabled={lines.length <= 1}
                      onClick={() => onChange(lines.filter((item) => item.key !== line.key))}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Button
        variant="ghost"
        onClick={() => onChange([...lines, itemLine(Math.max(...lines.map((l) => l.key)) + 1)])}
      >
        {t('acc.addLine')}
      </Button>
    </>
  );
}

function filled(lines: ItemLine[]) {
  return lines.filter((line) => line.product && line.quantity);
}

function ItemsDocumentEditor({
  title,
  priceLabel,
  showExpected,
  onSave,
  onDone,
  pending,
  error,
}: {
  title: string;
  priceLabel: string;
  showExpected?: boolean;
  onSave: (header: Record<string, unknown>, lines: ItemLine[]) => void;
  onDone: () => void;
  pending: boolean;
  error: unknown;
}) {
  const { t } = useTranslation();
  const warehouses = useWarehouses();
  const [supplier, setSupplier] = useState('');
  const [date, setDate] = useState(today());
  const [expected, setExpected] = useState('');
  const [warehouse, setWarehouse] = useState('');
  const [memo, setMemo] = useState('');
  const [lines, setLines] = useState<ItemLine[]>([itemLine(0)]);
  return (
    <Panel title={title}>
      <div className="grid gap-4 md:grid-cols-4">
        <SupplierSelect value={supplier} onChange={setSupplier} />
        <Field
          label={t('acc.date')}
          type="date"
          required
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <Select
          label={t('inv.warehouse')}
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
        {showExpected ? (
          <Field
            label={t('pur.expected')}
            type="date"
            value={expected}
            onChange={(e) => setExpected(e.target.value)}
          />
        ) : (
          <Field
            label={t('acc.memo')}
            maxLength={255}
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
          />
        )}
      </div>
      <div className="mt-4 space-y-4">
        <ItemsEditor lines={lines} onChange={setLines} priceLabel={priceLabel} />
        <div className="flex flex-wrap gap-3">
          <Button
            disabled={pending || !supplier || !warehouse || filled(lines).length === 0}
            onClick={() =>
              onSave(
                {
                  supplier: Number(supplier),
                  date,
                  warehouse: Number(warehouse),
                  memo,
                  ...(showExpected ? { expected_date: expected || null } : {}),
                },
                filled(lines),
              )
            }
          >
            {t('acc.saveDraft')}
          </Button>
          <Button variant="ghost" onClick={onDone}>
            {t('workspace.cancel')}
          </Button>
        </div>
        <ActionError error={error} />
      </div>
    </Panel>
  );
}

function LinesTable({ rows }: { rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto" data-lenis-prevent>
      <table className={TABLE}>
        <tbody>
          {rows.map((cells, index) => (
            <tr key={index} className="border-t border-line">
              {cells.map((cell, column) => (
                <td key={column} className={column === 0 ? TD : NUM}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Actions({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap gap-3">{children}</div>;
}

function OrderRow({ order }: { order: PurchaseOrder }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  const [receiptStarted, setReceiptStarted] = useState(false);
  const id = { params: { path: { id: order.id } } };
  const qty = (value: string) => formatQuantity(value, i18n.resolvedLanguage);
  return (
    <DocumentRow
      number={order.number}
      date={order.date}
      party={order.supplier_name}
      amount={order.total}
      status={order.status}
    >
      <LinesTable
        rows={order.lines.map((line) => [
          <>
            <span className="font-mono text-xs text-gold">{line.sku}</span> {line.product_name}
          </>,
          `${qty(line.quantity)} ${line.unit_code}`,
          t('pur.receivedOf', { received: qty(line.received_quantity) }),
          formatMoney(line.unit_price, i18n.resolvedLanguage),
        ])}
      />
      <ActionError error={action.error} />
      <Actions>
        {order.status === 'draft' && can(membership, 'purchasing', 'post') && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.POST('/api/purchasing/orders/{id}/confirm/', id)))
            }
          >
            {t('pur.confirm')}
          </Button>
        )}
        {order.status === 'confirmed' && can(membership, 'purchasing', 'create') && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(async () => {
                const receipt = await unwrap(
                  api.POST('/api/purchasing/orders/{id}/receive/', {
                    ...id,
                    body: { date: today() } as never,
                  }),
                );
                setReceiptStarted(true);
                return receipt;
              })
            }
          >
            {t('pur.receive')}
          </Button>
        )}
        {order.status === 'confirmed' && can(membership, 'purchasing', 'update') && (
          <Button
            variant="ghost"
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.POST('/api/purchasing/orders/{id}/close/', id)))
            }
          >
            {t('pur.close')}
          </Button>
        )}
        {order.status === 'draft' && can(membership, 'purchasing', 'delete') && (
          <Button
            variant="danger"
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.DELETE('/api/purchasing/orders/{id}/', id)))
            }
          >
            {t('workspace.remove')}
          </Button>
        )}
      </Actions>
      {receiptStarted && order.status === 'confirmed' && (
        <p className="text-sm text-muted">{t('pur.receiptStarted')}</p>
      )}
    </DocumentRow>
  );
}

function useDocuments<T>(key: string, load: () => Promise<T>) {
  const { membership } = useWorkspace();
  return useQuery({ queryKey: [membership.tenant_id, key], queryFn: load });
}

function NewButton({ label, onClick }: { label: string; onClick: () => void }) {
  const { membership } = useWorkspace();
  if (!can(membership, 'purchasing', 'create')) return null;
  return <Button onClick={onClick}>{label}</Button>;
}

export function OrdersPage() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const save = useTenantAction(KEYS);
  const orders = useDocuments('orders', () => unwrap(api.GET('/api/purchasing/orders/')));
  return (
    <>
      <PageTitle title={t('pur.orders')} subtitle={t('pur.ordersBody')} />
      {creating ? (
        <ItemsDocumentEditor
          title={t('pur.newOrder')}
          priceLabel={t('pur.unitPrice')}
          showExpected
          pending={save.isPending}
          error={save.error}
          onDone={() => setCreating(false)}
          onSave={(header, lines) => {
            const body = {
              ...header,
              lines: lines.map((line) => ({
                product: Number(line.product),
                unit: Number(line.unit),
                quantity: line.quantity,
                unit_price: line.price || '0',
              })),
            } as never;
            save.mutate(() => unwrap(api.POST('/api/purchasing/orders/', { body })), {
              onSuccess: () => setCreating(false),
            });
          }}
        />
      ) : (
        <NewButton label={t('pur.newOrder')} onClick={() => setCreating(true)} />
      )}
      <DocumentList
        title={t('pur.orders')}
        rows={orders.data?.results}
        render={(order: PurchaseOrder) => <OrderRow key={order.id} order={order} />}
      />
    </>
  );
}

// Goods receipts

interface ReceiptDraftLine {
  quantity: string;
  batch: string;
  expiry: string;
}

function ReceiptRow({ receipt }: { receipt: GoodsReceipt }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  const id = { params: { path: { id: receipt.id } } };
  const draft = receipt.status === 'draft';
  // Saving a draft replaces its lines, so their ids change. Whatever has no edit under its current
  // id shows what the server holds, or a retry after a failed post would send empty lines.
  const [edits, setEdits] = useState<Record<number, ReceiptDraftLine>>({});
  const current = (line: GoodsReceipt['lines'][number]): ReceiptDraftLine =>
    edits[line.id] ?? {
      quantity: line.quantity,
      batch: line.batch_number ?? '',
      expiry: line.expiry_date ?? '',
    };
  const edit = (line: GoodsReceipt['lines'][number], patch: Partial<ReceiptDraftLine>) =>
    setEdits({ ...edits, [line.id]: { ...current(line), ...patch } });
  const saveAndPost = () =>
    action.mutate(async () => {
      const body = {
        supplier: receipt.supplier,
        purchase_order: receipt.purchase_order ?? null,
        date: receipt.date,
        warehouse: receipt.warehouse,
        memo: receipt.memo,
        lines: receipt.lines
          .filter((line) => Number(current(line).quantity) > 0)
          .map((line) => ({
            order_line: line.order_line ?? null,
            product: line.product,
            unit: line.unit,
            quantity: current(line).quantity,
            unit_cost: line.unit_cost,
            batch_number: current(line).batch,
            expiry_date: current(line).expiry || null,
          })),
      } as never;
      await unwrap(api.PUT('/api/purchasing/receipts/{id}/', { ...id, body }));
      return unwrap(api.POST('/api/purchasing/receipts/{id}/post/', id));
    });
  const unbilled = receipt.lines.some(
    (line) => Number(line.billed_quantity) < Number(line.quantity),
  );
  return (
    <DocumentRow
      number={receipt.number}
      date={receipt.date}
      party={receipt.supplier_name}
      status={receipt.status}
    >
      {receipt.order_number && (
        <p className="label">{t('pur.againstOrder', { number: receipt.order_number })}</p>
      )}
      <LinesTable
        rows={receipt.lines.map((line) => [
          <>
            <span className="font-mono text-xs text-gold">{line.sku}</span> {line.product_name}
          </>,
          draft ? (
            <div className="flex justify-end gap-2">
              <div className="w-24">
                <NumberCell
                  label={t('inv.quantity')}
                  value={current(line).quantity}
                  onChange={(quantity) => edit(line, { quantity })}
                />
              </div>
              <input
                aria-label={t('inv.batch')}
                placeholder={t('inv.batch')}
                maxLength={40}
                className={`${CELL_INPUT} w-28`}
                value={current(line).batch}
                onChange={(e) => edit(line, { batch: e.target.value })}
              />
              <input
                aria-label={t('inv.expiry')}
                type="date"
                className={`${CELL_INPUT} w-36`}
                value={current(line).expiry}
                onChange={(e) => edit(line, { expiry: e.target.value })}
              />
            </div>
          ) : (
            `${formatQuantity(line.quantity, i18n.resolvedLanguage)} ${line.unit_code}`
          ),
          line.unit_code,
          formatMoney(line.unit_cost, i18n.resolvedLanguage),
        ])}
      />
      {draft && <p className="text-xs text-muted">{t('pur.receiveHint')}</p>}
      <ActionError error={action.error} />
      <Actions>
        {draft && can(membership, 'purchasing', 'post') && (
          <Button disabled={action.isPending} onClick={saveAndPost}>
            {t('pur.postReceipt')}
          </Button>
        )}
        {!draft && unbilled && can(membership, 'purchasing', 'create') && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() =>
                unwrap(
                  api.POST('/api/purchasing/receipts/{id}/bill/', {
                    ...id,
                    body: { date: today() } as never,
                  }),
                ),
              )
            }
          >
            {t('pur.createBill')}
          </Button>
        )}
        {draft && can(membership, 'purchasing', 'delete') && (
          <Button
            variant="danger"
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.DELETE('/api/purchasing/receipts/{id}/', id)))
            }
          >
            {t('workspace.remove')}
          </Button>
        )}
      </Actions>
    </DocumentRow>
  );
}

export function ReceiptsPage() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const save = useTenantAction(KEYS);
  const receipts = useDocuments('receipts', () => unwrap(api.GET('/api/purchasing/receipts/')));
  return (
    <>
      <PageTitle title={t('pur.receipts')} subtitle={t('pur.receiptsBody')} />
      {creating ? (
        <ItemsDocumentEditor
          title={t('pur.newReceipt')}
          priceLabel={t('inv.unitCost')}
          pending={save.isPending}
          error={save.error}
          onDone={() => setCreating(false)}
          onSave={(header, lines) => {
            const body = {
              ...header,
              lines: lines.map((line) => ({
                product: Number(line.product),
                unit: Number(line.unit),
                quantity: line.quantity,
                unit_cost: line.price || '0',
              })),
            } as never;
            save.mutate(() => unwrap(api.POST('/api/purchasing/receipts/', { body })), {
              onSuccess: () => setCreating(false),
            });
          }}
        />
      ) : (
        <NewButton label={t('pur.newReceipt')} onClick={() => setCreating(true)} />
      )}
      <DocumentList
        title={t('pur.receipts')}
        rows={receipts.data?.results}
        render={(receipt: GoodsReceipt) => <ReceiptRow key={receipt.id} receipt={receipt} />}
      />
    </>
  );
}

// Bills

interface BillDraftLine {
  key: number;
  account: string;
  description: string;
  amount: string;
  tax: string;
}

function BillEditor({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const accounts = useAccounts();
  const save = useTenantAction(KEYS);
  const [supplier, setSupplier] = useState('');
  const [date, setDate] = useState(today());
  const [reference, setReference] = useState('');
  const blankLine = (key: number): BillDraftLine => ({
    key,
    account: '',
    description: '',
    amount: '',
    tax: '',
  });
  const [lines, setLines] = useState<BillDraftLine[]>([blankLine(0)]);
  const update = (key: number, patch: Partial<BillDraftLine>) =>
    setLines(lines.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  const ready = lines.filter((line) => line.account && line.amount);
  const choices = [...postable(accounts.data, 'expense'), ...postable(accounts.data, 'asset')];

  return (
    <Panel title={t('pur.newExpenseBill')}>
      <div className="grid gap-4 md:grid-cols-3">
        <SupplierSelect value={supplier} onChange={setSupplier} />
        <Field
          label={t('acc.date')}
          type="date"
          required
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <Field
          label={t('pur.reference')}
          maxLength={40}
          value={reference}
          onChange={(e) => setReference(e.target.value)}
        />
      </div>
      <div className="mt-4 overflow-x-auto" data-lenis-prevent>
        <table className={`${TABLE} min-w-[40rem]`}>
          <thead>
            <tr>
              <th className={TH}>{t('pur.account')}</th>
              <th className={TH}>{t('pur.description')}</th>
              <th className={TH}>{t('pur.amount')}</th>
              <th className={TH}>{t('pur.tax')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.key} className="border-t border-line">
                <td className="py-2 pe-2">
                  <select
                    aria-label={t('pur.account')}
                    className={CELL_INPUT}
                    value={line.account}
                    onChange={(e) => update(line.key, { account: e.target.value })}
                  >
                    <option value="">-</option>
                    {choices.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.code} {account.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pe-2">
                  <input
                    aria-label={t('pur.description')}
                    maxLength={255}
                    className={CELL_INPUT}
                    value={line.description}
                    onChange={(e) => update(line.key, { description: e.target.value })}
                  />
                </td>
                <td className="w-32 py-2 pe-2">
                  <NumberCell
                    label={t('pur.amount')}
                    value={line.amount}
                    onChange={(amount) => update(line.key, { amount })}
                  />
                </td>
                <td className="w-28 py-2 pe-2">
                  <NumberCell
                    label={t('pur.tax')}
                    value={line.tax}
                    onChange={(tax) => update(line.key, { tax })}
                  />
                </td>
                <td className="py-2">
                  <RemoveLine
                    disabled={lines.length <= 1}
                    onClick={() => setLines(lines.filter((item) => item.key !== line.key))}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          variant="ghost"
          onClick={() => setLines([...lines, blankLine(Math.max(...lines.map((l) => l.key)) + 1)])}
        >
          {t('acc.addLine')}
        </Button>
        <Button
          disabled={save.isPending || !supplier || ready.length === 0}
          onClick={() => {
            const body = {
              supplier: Number(supplier),
              date,
              supplier_reference: reference,
              lines: ready.map((line) => ({
                account: Number(line.account),
                description: line.description,
                quantity: '1',
                unit_price: line.amount,
                tax_amount: line.tax || '0',
              })),
            } as never;
            save.mutate(() => unwrap(api.POST('/api/purchasing/bills/', { body })), {
              onSuccess: onDone,
            });
          }}
        >
          {t('acc.saveDraft')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('workspace.cancel')}
        </Button>
      </div>
      <div className="mt-4">
        <ActionError error={save.error} />
      </div>
    </Panel>
  );
}

function BillRow({ bill }: { bill: Bill }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  const id = { params: { path: { id: bill.id } } };
  const draft = bill.status === 'draft';
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const [reference, setReference] = useState(bill.supplier_reference ?? '');
  // Keyed like the receipt edits above, and for the same reason.
  const [prices, setPrices] = useState<Record<number, { price: string; tax: string }>>({});
  const priced = (line: Bill['lines'][number]) =>
    prices[line.id] ?? { price: line.unit_price, tax: line.tax_amount ?? '0' };
  const setPrice = (line: Bill['lines'][number], patch: Partial<{ price: string; tax: string }>) =>
    setPrices({ ...prices, [line.id]: { ...priced(line), ...patch } });
  const saveAndPost = () =>
    action.mutate(async () => {
      const body = {
        supplier: bill.supplier,
        date: bill.date,
        due_date: bill.due_date ?? null,
        supplier_reference: reference,
        memo: bill.memo,
        lines: bill.lines.map((line) => ({
          receipt_line: line.receipt_line ?? null,
          account: line.account ?? null,
          description: line.description,
          quantity: line.quantity,
          unit_price: priced(line).price,
          tax_amount: priced(line).tax || '0',
        })),
      } as never;
      await unwrap(api.PUT('/api/purchasing/bills/{id}/', { ...id, body }));
      return unwrap(api.POST('/api/purchasing/bills/{id}/post/', id));
    });
  const status = draft ? 'draft' : Number(bill.amount_paid) >= Number(bill.total) ? 'paid' : 'open';
  return (
    <DocumentRow
      number={bill.number}
      date={bill.date}
      party={bill.supplier_name}
      amount={bill.total}
      status={status}
    >
      <div className="grid gap-4 text-sm sm:grid-cols-3">
        {draft ? (
          <Field
            label={t('pur.reference')}
            maxLength={40}
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
        ) : (
          <p>
            <span className="label block">{t('pur.reference')}</span>
            {bill.supplier_reference || '-'}
          </p>
        )}
        <p>
          <span className="label block">{t('pur.due')}</span>
          {bill.due_date}
        </p>
        <p>
          <span className="label block">{t('pur.paid')}</span>
          <span className="font-mono">{money(bill.amount_paid)}</span>
        </p>
      </div>
      <LinesTable
        rows={bill.lines.map((line) => [
          line.description || line.account_name,
          formatQuantity(line.quantity, i18n.resolvedLanguage),
          draft ? (
            <div className="ms-auto w-28">
              <NumberCell
                label={t('pur.unitPrice')}
                value={priced(line).price}
                onChange={(price) => setPrice(line, { price })}
              />
            </div>
          ) : (
            money(line.unit_price)
          ),
          draft ? (
            <div className="ms-auto w-24">
              <NumberCell
                label={t('pur.tax')}
                value={priced(line).tax}
                onChange={(tax) => setPrice(line, { tax })}
              />
            </div>
          ) : (
            money(line.tax_amount ?? '0')
          ),
        ])}
      />
      {bill.journal_number && (
        <p className="label">{t('inv.postedAs', { number: bill.journal_number })}</p>
      )}
      {draft && <p className="text-xs text-muted">{t('pur.billHint')}</p>}
      <ActionError error={action.error} />
      {draft && (
        <Actions>
          {can(membership, 'purchasing', 'post') && (
            <Button disabled={action.isPending} onClick={saveAndPost}>
              {t('pur.postBill')}
            </Button>
          )}
          {can(membership, 'purchasing', 'delete') && (
            <Button
              variant="danger"
              disabled={action.isPending}
              onClick={() =>
                action.mutate(() => unwrap(api.DELETE('/api/purchasing/bills/{id}/', id)))
              }
            >
              {t('workspace.remove')}
            </Button>
          )}
        </Actions>
      )}
    </DocumentRow>
  );
}

export function BillsPage() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const bills = useDocuments('bills', () => unwrap(api.GET('/api/purchasing/bills/')));
  return (
    <>
      <PageTitle title={t('pur.bills')} subtitle={t('pur.billsBody')} />
      {creating ? (
        <BillEditor onDone={() => setCreating(false)} />
      ) : (
        <NewButton label={t('pur.newExpenseBill')} onClick={() => setCreating(true)} />
      )}
      <DocumentList
        title={t('pur.bills')}
        rows={bills.data?.results}
        render={(bill: Bill) => <BillRow key={bill.id} bill={bill} />}
      />
    </>
  );
}

// Payments

function PaymentEditor({ onDone }: { onDone: () => void }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const accounts = useAccounts();
  const save = useTenantAction(KEYS);
  const [supplier, setSupplier] = useState('');
  const [date, setDate] = useState(today());
  const [paidFrom, setPaidFrom] = useState('');
  const [reference, setReference] = useState('');
  const [amount, setAmount] = useState('');
  const [allocations, setAllocations] = useState<Record<number, string>>({});
  const open = useQuery({
    queryKey: [membership.tenant_id, 'bills', 'open', supplier],
    enabled: Boolean(supplier),
    queryFn: () =>
      unwrap(
        api.GET('/api/purchasing/bills/', {
          params: { query: { status: 'posted', supplier: Number(supplier) } as never },
        }),
      ),
  });
  const owing = (open.data?.results ?? []).filter(
    (bill) => Number(bill.amount_paid) < Number(bill.total),
  );
  const allocated = Object.values(allocations).reduce(
    (sum, value) => sum + (Number(value) || 0),
    0,
  );
  const money = (value: string | number) => formatMoney(value, i18n.resolvedLanguage);

  return (
    <Panel title={t('pur.newPayment')}>
      <div className="grid gap-4 md:grid-cols-3">
        <SupplierSelect
          value={supplier}
          onChange={(value) => {
            setSupplier(value);
            setAllocations({});
          }}
        />
        <Field
          label={t('acc.date')}
          type="date"
          required
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <Select
          label={t('pur.paidFrom')}
          required
          value={paidFrom}
          onChange={(e) => setPaidFrom(e.target.value)}
        >
          <option value="">-</option>
          {postable(accounts.data, 'asset').map((account) => (
            <option key={account.id} value={account.id}>
              {account.code} {account.name}
            </option>
          ))}
        </Select>
        <Field
          label={t('pur.amount')}
          inputMode="decimal"
          required
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <Field
          label={t('pur.reference')}
          maxLength={60}
          value={reference}
          onChange={(e) => setReference(e.target.value)}
        />
      </div>
      {supplier && (
        <div className="mt-4 overflow-x-auto" data-lenis-prevent>
          <table className={TABLE}>
            <thead>
              <tr>
                <th className={TH}>{t('pur.bill')}</th>
                <th className={TH}>{t('pur.due')}</th>
                <th className={`${TH} text-end`}>{t('pur.owing')}</th>
                <th className={`${TH} text-end`}>{t('pur.allocate')}</th>
              </tr>
            </thead>
            <tbody>
              {owing.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-4 text-sm text-muted">
                    {t('pur.nothingOwing')}
                  </td>
                </tr>
              )}
              {owing.map((bill) => {
                const due = Number(bill.total) - Number(bill.amount_paid);
                return (
                  <tr key={bill.id} className="border-t border-line">
                    <td className={`${TD} font-mono text-sm`}>{bill.number}</td>
                    <td className={`${TD} text-muted`}>{bill.due_date}</td>
                    <td className={NUM}>{money(due)}</td>
                    <td className="w-32 py-2">
                      <NumberCell
                        label={t('pur.allocate')}
                        value={allocations[bill.id] ?? ''}
                        onChange={(value) => setAllocations({ ...allocations, [bill.id]: value })}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">
            {t('pur.allocated', {
              allocated: money(allocated),
              amount: money(Number(amount) || 0),
            })}
          </p>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          disabled={save.isPending || !supplier || !paidFrom || !(Number(amount) > 0)}
          onClick={() => {
            const body = {
              supplier: Number(supplier),
              date,
              amount,
              paid_from: Number(paidFrom),
              reference,
              allocations: Object.entries(allocations)
                .filter(([, value]) => Number(value) > 0)
                .map(([bill, value]) => ({ bill: Number(bill), amount: value })),
            } as never;
            save.mutate(() => unwrap(api.POST('/api/purchasing/payments/', { body })), {
              onSuccess: onDone,
            });
          }}
        >
          {t('acc.saveDraft')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('workspace.cancel')}
        </Button>
      </div>
      <div className="mt-4">
        <ActionError error={save.error} />
      </div>
    </Panel>
  );
}

function PaymentRow({ payment }: { payment: SupplierPayment }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  const id = { params: { path: { id: payment.id } } };
  return (
    <DocumentRow
      number={payment.number}
      date={payment.date}
      party={payment.supplier_name}
      amount={payment.amount}
      status={payment.status}
    >
      <LinesTable
        rows={(payment.allocations ?? []).map((allocation) => [
          allocation.bill_number,
          formatMoney(allocation.amount, i18n.resolvedLanguage),
        ])}
      />
      {payment.reference && <p className="text-sm text-muted">{payment.reference}</p>}
      {payment.journal_number && (
        <p className="label">{t('inv.postedAs', { number: payment.journal_number })}</p>
      )}
      <ActionError error={action.error} />
      {payment.status === 'draft' && (
        <Actions>
          {can(membership, 'purchasing', 'post') && (
            <Button
              disabled={action.isPending}
              onClick={() =>
                action.mutate(() => unwrap(api.POST('/api/purchasing/payments/{id}/post/', id)))
              }
            >
              {t('acc.post')}
            </Button>
          )}
          {can(membership, 'purchasing', 'delete') && (
            <Button
              variant="danger"
              disabled={action.isPending}
              onClick={() =>
                action.mutate(() => unwrap(api.DELETE('/api/purchasing/payments/{id}/', id)))
              }
            >
              {t('workspace.remove')}
            </Button>
          )}
        </Actions>
      )}
    </DocumentRow>
  );
}

export function PaymentsPage() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const payments = useDocuments('payments', () => unwrap(api.GET('/api/purchasing/payments/')));
  return (
    <>
      <PageTitle title={t('pur.payments')} subtitle={t('pur.paymentsBody')} />
      {creating ? (
        <PaymentEditor onDone={() => setCreating(false)} />
      ) : (
        <NewButton label={t('pur.newPayment')} onClick={() => setCreating(true)} />
      )}
      <DocumentList
        title={t('pur.payments')}
        rows={payments.data?.results}
        render={(payment: SupplierPayment) => <PaymentRow key={payment.id} payment={payment} />}
      />
    </>
  );
}
