import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Button, Field, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { allPages } from '../../lib/api/pages';
import {
  can,
  type CreditNote,
  type Customer,
  type CustomerReceipt,
  type Invoice,
  type SalesOrder,
} from '../../lib/api/types';
import { today } from '../../lib/dates';
import { formatMoney, toMinor } from '../../lib/money';
import { useSaleTaxRates } from '../accounting/TaxRates';
import { formatQuantity, useWarehouses } from '../inventory/shared';
import {
  ActionError,
  Actions,
  DocumentList,
  DocumentRow,
  filled,
  itemLine,
  ItemsEditor,
  LinesTable,
  postable,
  useAccounts,
  useDocuments,
  type ItemLine,
} from '../purchasing/pages';
import { useTenantAction, useWorkspace } from '../workspace/hooks';
import { PrintButton, StatementPanel } from './ledgers';
import { NUM, TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';

// A sale moves stock and money, so every action refreshes all of these.
const SALES_ORDERS = 'sales-orders';
const SALES_RECEIPTS = 'sales-receipts';
const KEYS = [
  'customers',
  SALES_ORDERS,
  'invoices',
  SALES_RECEIPTS,
  'credits',
  'levels',
  'products',
];

function useCustomers() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'customers'],
    queryFn: async () => ({
      results: await allPages((cursor) =>
        unwrap(
          api.GET('/api/sales/customers/', {
            params: { query: { page_size: 200, cursor } as never },
          }),
        ),
      ),
    }),
  });
}

function CustomerSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const { t } = useTranslation();
  const customers = useCustomers();
  return (
    <Select
      label={t('sal.customer')}
      required
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">-</option>
      {customers.data?.results
        .filter((customer) => customer.is_active !== false)
        .map((customer) => (
          <option key={customer.id} value={customer.id}>
            {customer.name}
          </option>
        ))}
    </Select>
  );
}

// In paisa, like every sum the UI does: formatMoney reads a number as paisa, not rupees.
function stillToPay(invoice: Invoice): number {
  return toMinor(invoice.total) - toMinor(invoice.amount_paid) - toMinor(invoice.amount_credited);
}

function NewButton({ label, onClick }: { label: string; onClick: () => void }) {
  const { membership } = useWorkspace();
  if (!can(membership, 'sales', 'create')) return null;
  return <Button onClick={onClick}>{label}</Button>;
}

// Customers

export function CustomersPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const customers = useCustomers();
  const save = useTenantAction(KEYS);
  const empty = { code: '', name: '', phone: '', limit: '', terms: '0' };
  const [form, setForm] = useState(empty);
  const [viewing, setViewing] = useState<Customer | null>(null);
  const set = (patch: Partial<typeof empty>) => setForm({ ...form, ...patch });
  return (
    <>
      <PageTitle title={t('sal.customers')} subtitle={t('sal.customersBody')} />
      {viewing && (
        <StatementPanel
          key={viewing.id}
          title={viewing.name}
          queryKey={`statement-${viewing.id}`}
          onClose={() => setViewing(null)}
          load={(query) =>
            unwrap(
              api.GET('/api/sales/customers/{id}/statement/', {
                params: { path: { id: viewing.id }, query },
              }),
            )
          }
        />
      )}
      {can(membership, 'sales', 'create') && (
        <Panel title={t('sal.newCustomer')}>
          <form
            className="grid gap-4 md:grid-cols-5"
            onSubmit={(event) => {
              event.preventDefault();
              const body = {
                code: form.code,
                name: form.name,
                phone: form.phone,
                payment_terms_days: Number(form.terms) || 0,
                credit_limit: form.limit === '' ? null : form.limit,
              } as never;
              save.mutate(() => unwrap(api.POST('/api/sales/customers/', { body })), {
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
              label={t('pur.terms')}
              inputMode="numeric"
              value={form.terms}
              onChange={(e) => set({ terms: e.target.value })}
            />
            <Field
              label={t('sal.creditLimit')}
              hint={t('sal.creditLimitHint')}
              inputMode="decimal"
              value={form.limit}
              onChange={(e) => set({ limit: e.target.value })}
            />
            <div className="md:col-span-5">
              <Button type="submit" disabled={save.isPending}>
                {t('sal.addCustomer')}
              </Button>
            </div>
          </form>
          <div className="mt-4">
            <ActionError error={save.error} />
          </div>
        </Panel>
      )}
      <Panel title={t('sal.customers')}>
        <div className="overflow-x-auto" data-lenis-prevent>
          <table className={`${TABLE} min-w-[34rem]`}>
            <thead>
              <tr>
                <th className={TH}>{t('pur.name')}</th>
                <th className={TH}>{t('pur.phone')}</th>
                <th className={`${TH} text-end`}>{t('sal.creditLimit')}</th>
                <th className={`${TH} text-end`}>{t('sal.balance')}</th>
              </tr>
            </thead>
            <tbody>
              {customers.data?.results.map((customer: Customer) => (
                <tr key={customer.id} className="border-t border-line">
                  <td className={TD}>
                    <button
                      type="button"
                      className="text-start underline underline-offset-4"
                      onClick={() => setViewing(customer)}
                    >
                      {customer.name}
                    </button>
                  </td>
                  <td className={TD}>{customer.phone}</td>
                  <td className={NUM}>
                    {customer.credit_limit == null
                      ? t('sal.noLimit')
                      : formatMoney(customer.credit_limit, i18n.resolvedLanguage)}
                  </td>
                  <td className={NUM}>
                    {formatMoney(customer.balance ?? '0', i18n.resolvedLanguage)}
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

// Quotes and orders, and invoices: the same editor, because both are a customer and some goods.

function saleLines(lines: ItemLine[], taxRate: unknown) {
  return lines.map((line) => ({
    product: Number(line.product),
    unit: Number(line.unit),
    quantity: line.quantity,
    unit_price: line.price || '0',
    tax_amount: line.tax || '0',
    tax_rate: taxRate ?? null,
  }));
}

function SaleEditor({
  title,
  onSave,
  onDone,
  pending,
  error,
}: {
  title: string;
  onSave: (header: Record<string, unknown>, lines: ItemLine[]) => void;
  onDone: () => void;
  pending: boolean;
  error: unknown;
}) {
  const { t } = useTranslation();
  const warehouses = useWarehouses();
  const [customer, setCustomer] = useState('');
  const [date, setDate] = useState(today());
  const [warehouse, setWarehouse] = useState('');
  const [lines, setLines] = useState<ItemLine[]>([itemLine(0)]);
  const rates = useSaleTaxRates();
  const [picked, setPicked] = useState('');
  // Only rates that apply on this date. The server checks again, so this is a convenience.
  const usable = rates.data?.filter(
    (item) => item.valid_from <= date && (!item.valid_to || date <= item.valid_to),
  );
  // Changing the date can rule the picked rate out; then it stops counting, here and on save.
  const rate = usable?.some((item) => String(item.id) === picked) ? picked : '';
  return (
    <Panel title={title}>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <CustomerSelect value={customer} onChange={setCustomer} />
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
        <Select label={t('pur.tax')} value={rate} onChange={(e) => setPicked(e.target.value)}>
          <option value="">{t('tax.typeIt')}</option>
          {usable?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} {Number(item.rate)}%
            </option>
          ))}
        </Select>
      </div>
      <div className="mt-4 space-y-4">
        <ItemsEditor
          lines={lines}
          onChange={setLines}
          priceLabel={t('sal.price')}
          {...(rate ? {} : { taxLabel: t('pur.tax') })}
        />
        <Actions>
          <Button
            disabled={pending || !customer || !warehouse || filled(lines).length === 0}
            onClick={() =>
              onSave(
                {
                  customer: Number(customer),
                  date,
                  warehouse: Number(warehouse),
                  taxRate: rate ? Number(rate) : null,
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
        </Actions>
        <ActionError error={error} />
      </div>
    </Panel>
  );
}

function OrderRow({ order }: { order: SalesOrder }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  const id = { params: { path: { id: order.id } } };
  const [invoiced, setInvoiced] = useState(false);
  const open = order.status === 'draft' || order.status === 'quoted';
  return (
    <DocumentRow
      number={order.number ?? order.quote_number}
      date={order.date}
      party={order.customer_name}
      amount={order.total}
      status={order.status}
    >
      <LinesTable
        rows={order.lines.map((line) => [
          line.product_name,
          `${formatQuantity(line.quantity, i18n.resolvedLanguage)} ${line.unit_code}`,
          formatMoney(line.unit_price, i18n.resolvedLanguage),
        ])}
      />
      <Actions>
        {order.status === 'draft' && can(membership, 'sales', 'update') && (
          <Button
            variant="ghost"
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.POST('/api/sales/orders/{id}/quote/', id)))
            }
          >
            {t('sal.quote')}
          </Button>
        )}
        {open && can(membership, 'sales', 'post') && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.POST('/api/sales/orders/{id}/confirm/', id)))
            }
          >
            {t('pur.confirm')}
          </Button>
        )}
        {order.status === 'confirmed' && can(membership, 'sales', 'create') && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(async () => {
                const invoice = await unwrap(
                  api.POST('/api/sales/orders/{id}/invoice/', {
                    ...id,
                    body: { date: today() } as never,
                  }),
                );
                setInvoiced(true);
                return invoice;
              })
            }
          >
            {t('sal.makeInvoice')}
          </Button>
        )}
        {(order.status === 'quoted' || order.status === 'confirmed') &&
          can(membership, 'sales', 'update') && (
            <Button
              variant="ghost"
              disabled={action.isPending}
              onClick={() =>
                action.mutate(() => unwrap(api.POST('/api/sales/orders/{id}/close/', id)))
              }
            >
              {t('pur.close')}
            </Button>
          )}
        {order.status === 'draft' && can(membership, 'sales', 'delete') && (
          <Button
            variant="danger"
            disabled={action.isPending}
            onClick={() => action.mutate(() => unwrap(api.DELETE('/api/sales/orders/{id}/', id)))}
          >
            {t('workspace.remove')}
          </Button>
        )}
      </Actions>
      {invoiced && <p className="text-sm text-muted">{t('sal.invoiceStarted')}</p>}
      <ActionError error={action.error} />
    </DocumentRow>
  );
}

export function OrdersPage() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const save = useTenantAction(KEYS);
  const orders = useDocuments(SALES_ORDERS, () => unwrap(api.GET('/api/sales/orders/')));
  return (
    <>
      <PageTitle title={t('sal.orders')} subtitle={t('sal.ordersBody')} />
      {creating ? (
        <SaleEditor
          title={t('sal.newOrder')}
          pending={save.isPending}
          error={save.error}
          onDone={() => setCreating(false)}
          onSave={(header, lines) => {
            const { taxRate, ...fields } = header;
            const body = { ...fields, lines: saleLines(lines, taxRate) } as never;
            save.mutate(() => unwrap(api.POST('/api/sales/orders/', { body })), {
              onSuccess: () => setCreating(false),
            });
          }}
        />
      ) : (
        <NewButton label={t('sal.newOrder')} onClick={() => setCreating(true)} />
      )}
      <DocumentList
        title={t('sal.orders')}
        rows={orders.data?.results}
        render={(order: SalesOrder) => <OrderRow key={order.id} order={order} />}
      />
    </>
  );
}

function InvoiceRow({ invoice }: { invoice: Invoice }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  const id = { params: { path: { id: invoice.id } } };
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  const draft = invoice.status === 'draft';
  const left = stillToPay(invoice);
  const returnable = invoice.lines.some(
    (line) => Number(line.returned_quantity) < Number(line.quantity),
  );
  return (
    <DocumentRow
      number={invoice.number}
      date={invoice.date}
      party={invoice.customer_name}
      amount={invoice.total}
      status={draft ? 'draft' : left <= 0 ? 'paid' : 'open'}
    >
      <LinesTable
        rows={invoice.lines.map((line) => [
          line.product_name,
          `${formatQuantity(line.quantity, i18n.resolvedLanguage)} ${line.unit_code}`,
          money(line.amount),
        ])}
      />
      {!draft && (
        <p className="text-sm text-muted">
          {t('sal.leftToPay')}: {formatMoney(left, i18n.resolvedLanguage)}
        </p>
      )}
      <Actions>
        {draft && can(membership, 'sales', 'post') && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.POST('/api/sales/invoices/{id}/post/', id)))
            }
          >
            {t('sal.postInvoice')}
          </Button>
        )}
        {draft && can(membership, 'sales', 'delete') && (
          <Button
            variant="danger"
            disabled={action.isPending}
            onClick={() => action.mutate(() => unwrap(api.DELETE('/api/sales/invoices/{id}/', id)))}
          >
            {t('workspace.remove')}
          </Button>
        )}
        {!draft && <PrintButton path={`/api/sales/invoices/${invoice.id}/pdf/`} />}
        {!draft && returnable && can(membership, 'sales', 'create') && (
          <Button
            variant="ghost"
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() =>
                unwrap(
                  api.POST('/api/sales/invoices/{id}/credit/', {
                    ...id,
                    body: { date: today() } as never,
                  }),
                ),
              )
            }
          >
            {t('sal.startReturn')}
          </Button>
        )}
      </Actions>
      <ActionError error={action.error} />
    </DocumentRow>
  );
}

export function InvoicesPage() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const save = useTenantAction(KEYS);
  const invoices = useDocuments('invoices', () => unwrap(api.GET('/api/sales/invoices/')));
  return (
    <>
      <PageTitle title={t('sal.invoices')} subtitle={t('sal.invoicesBody')} />
      {creating ? (
        <SaleEditor
          title={t('sal.newInvoice')}
          pending={save.isPending}
          error={save.error}
          onDone={() => setCreating(false)}
          onSave={(header, lines) => {
            const { taxRate, ...fields } = header;
            const body = { ...fields, lines: saleLines(lines, taxRate) } as never;
            save.mutate(() => unwrap(api.POST('/api/sales/invoices/', { body })), {
              onSuccess: () => setCreating(false),
            });
          }}
        />
      ) : (
        <NewButton label={t('sal.newInvoice')} onClick={() => setCreating(true)} />
      )}
      <DocumentList
        title={t('sal.invoices')}
        rows={invoices.data?.results}
        render={(invoice: Invoice) => <InvoiceRow key={invoice.id} invoice={invoice} />}
      />
    </>
  );
}

// Money received

function ReceiptEditor({ onDone }: { onDone: () => void }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const accounts = useAccounts();
  const save = useTenantAction(KEYS);
  const [customer, setCustomer] = useState('');
  const [date, setDate] = useState(today());
  const [into, setInto] = useState('');
  const [amount, setAmount] = useState('');
  const [allocations, setAllocations] = useState<Record<number, string>>({});
  const open = useQuery({
    queryKey: [membership.tenant_id, 'invoices', 'open', customer],
    enabled: Boolean(customer),
    queryFn: () =>
      allPages((cursor) =>
        unwrap(
          api.GET('/api/sales/invoices/', {
            params: {
              query: {
                status: 'posted',
                customer: Number(customer),
                page_size: 200,
                cursor,
              } as never,
            },
          }),
        ),
      ),
  });
  const owing = (open.data ?? []).filter((invoice) => stillToPay(invoice) > 0);
  const allocated = Object.values(allocations).reduce((sum, value) => sum + toMinor(value), 0);
  const money = (value: string | number) => formatMoney(value, i18n.resolvedLanguage);
  return (
    <Panel title={t('sal.newReceipt')}>
      <div className="grid gap-4 md:grid-cols-4">
        <CustomerSelect
          value={customer}
          onChange={(value) => {
            setCustomer(value);
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
          label={t('sal.receivedInto')}
          required
          value={into}
          onChange={(e) => setInto(e.target.value)}
        >
          <option value="">-</option>
          {postable(accounts.data, 'asset').map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
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
      </div>
      {owing.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="font-medium">{t('sal.whichInvoices')}</p>
          {owing.map((invoice) => (
            <label key={invoice.id} className="flex items-center justify-between gap-4 text-sm">
              <span>
                {invoice.number} &middot; {money(stillToPay(invoice))}
              </span>
              <input
                inputMode="decimal"
                aria-label={invoice.number ?? ''}
                className="w-32 rounded-lg border border-line bg-canvas px-2 py-2 text-end font-mono"
                value={allocations[invoice.id] ?? ''}
                onChange={(e) => setAllocations({ ...allocations, [invoice.id]: e.target.value })}
              />
            </label>
          ))}
          {allocated < toMinor(amount) && (
            <p className="text-sm text-muted">
              {t('sal.advance', { amount: money(toMinor(amount) - allocated) })}
            </p>
          )}
        </div>
      )}
      <div className="mt-4">
        <Actions>
          <Button
            disabled={save.isPending || !customer || !into || Number(amount) <= 0}
            onClick={() => {
              const body = {
                customer: Number(customer),
                date,
                amount,
                received_into: Number(into),
                allocations: Object.entries(allocations)
                  .filter(([, value]) => Number(value) > 0)
                  .map(([invoice, value]) => ({ invoice: Number(invoice), amount: value })),
              } as never;
              save.mutate(() => unwrap(api.POST('/api/sales/receipts/', { body })), {
                onSuccess: onDone,
              });
            }}
          >
            {t('acc.saveDraft')}
          </Button>
          <Button variant="ghost" onClick={onDone}>
            {t('workspace.cancel')}
          </Button>
        </Actions>
      </div>
      <div className="mt-4">
        <ActionError error={save.error} />
      </div>
    </Panel>
  );
}

function ReceiptRow({ receipt }: { receipt: CustomerReceipt }) {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  const id = { params: { path: { id: receipt.id } } };
  const draft = receipt.status === 'draft';
  return (
    <DocumentRow
      number={receipt.number}
      date={receipt.date}
      party={receipt.customer_name}
      amount={receipt.amount}
      status={receipt.status}
    >
      <Actions>
        {draft && can(membership, 'sales', 'post') && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.POST('/api/sales/receipts/{id}/post/', id)))
            }
          >
            {t('sal.postReceipt')}
          </Button>
        )}
        {!draft && <PrintButton path={`/api/sales/receipts/${receipt.id}/pdf/`} />}
        {draft && can(membership, 'sales', 'delete') && (
          <Button
            variant="danger"
            disabled={action.isPending}
            onClick={() => action.mutate(() => unwrap(api.DELETE('/api/sales/receipts/{id}/', id)))}
          >
            {t('workspace.remove')}
          </Button>
        )}
      </Actions>
      <ActionError error={action.error} />
    </DocumentRow>
  );
}

export function ReceiptsPage() {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const receipts = useDocuments(SALES_RECEIPTS, () => unwrap(api.GET('/api/sales/receipts/')));
  return (
    <>
      <PageTitle title={t('sal.receipts')} subtitle={t('sal.receiptsBody')} />
      {creating ? (
        <ReceiptEditor onDone={() => setCreating(false)} />
      ) : (
        <NewButton label={t('sal.newReceipt')} onClick={() => setCreating(true)} />
      )}
      <DocumentList
        title={t('sal.receipts')}
        rows={receipts.data?.results}
        render={(receipt: CustomerReceipt) => <ReceiptRow key={receipt.id} receipt={receipt} />}
      />
    </>
  );
}

// Returns

function ReturnRow({ note }: { note: CreditNote }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const action = useTenantAction(KEYS);
  const id = { params: { path: { id: note.id } } };
  const draft = note.status === 'draft';
  return (
    <DocumentRow
      number={note.number}
      date={note.date}
      party={note.customer_name}
      amount={note.total}
      status={note.status}
    >
      <LinesTable
        rows={note.lines.map((line) => [
          line.product_name,
          formatQuantity(line.quantity, i18n.resolvedLanguage),
        ])}
      />
      <Actions>
        {draft && can(membership, 'sales', 'post') && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.POST('/api/sales/credit-notes/{id}/post/', id)))
            }
          >
            {t('sal.postReturn')}
          </Button>
        )}
        {draft && can(membership, 'sales', 'delete') && (
          <Button
            variant="danger"
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() => unwrap(api.DELETE('/api/sales/credit-notes/{id}/', id)))
            }
          >
            {t('workspace.remove')}
          </Button>
        )}
      </Actions>
      <ActionError error={action.error} />
    </DocumentRow>
  );
}

export function ReturnsPage() {
  const { t } = useTranslation();
  const notes = useDocuments('credits', () => unwrap(api.GET('/api/sales/credit-notes/')));
  return (
    <>
      <PageTitle title={t('sal.returns')} subtitle={t('sal.returnsBody')} />
      <Alert tone="success">{t('sal.returnsHint')}</Alert>
      <DocumentList
        title={t('sal.returns')}
        rows={notes.data?.results}
        render={(note: CreditNote) => <ReturnRow key={note.id} note={note} />}
      />
    </>
  );
}
