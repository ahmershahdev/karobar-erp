import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Button, Field, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import type { components } from '../../lib/api/schema';
import { can } from '../../lib/api/types';
import { ensureCsrf } from '../auth/session';
import { errorText, useWorkspace } from './hooks';
import { PageTitle, Panel } from './ui';

type Settings = components['schemas']['BillSettings'];
type Form = Omit<Settings, 'logo'>;

type TextField =
  | 'address'
  | 'phone'
  | 'email'
  | 'tax_label'
  | 'tax_number'
  | 'title'
  | 'thanks'
  | 'payment_terms'
  | 'bank_details'
  | 'return_policy'
  | 'invoice_prefix';

// The logo is uploaded on its own, so it never goes back with the other settings.
function withoutLogo(settings: Settings): Form {
  return Object.fromEntries(Object.entries(settings).filter(([key]) => key !== 'logo'));
}

function Area({
  label,
  value,
  maxLength,
  onChange,
}: {
  label: string;
  value: string;
  maxLength: number;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block space-y-2">
      <span className="label">{label}</span>
      <textarea
        rows={3}
        maxLength={maxLength}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-line bg-canvas px-4 py-3 outline-none focus:border-ink"
      />
    </label>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-11 items-center gap-3">
      <input
        type="checkbox"
        className="size-5"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}

/** A rough picture of the top and bottom of the bill, so changes can be seen before printing. */
function Preview({ form, logo, business }: { form: Form; logo: string | null; business: string }) {
  const { t } = useTranslation();
  const accent = form.accent ?? '#0b1a3c';
  const footer = [form.thanks, form.payment_terms, form.bank_details, form.return_policy].filter(
    Boolean,
  );
  return (
    <div className="space-y-4 rounded-xl border border-line bg-white p-5 text-sm text-[#0b1a3c]">
      <div className="flex justify-between gap-4 border-b pb-3" style={{ borderColor: accent }}>
        <div className="min-w-0 space-y-0.5">
          {logo && <img src={logo} alt="" className="mb-2 max-h-14 max-w-40" />}
          <p className="text-base font-semibold" style={{ color: accent }}>
            {business}
          </p>
          {form.address && <p className="text-xs text-[#566076]">{form.address}</p>}
          {(form.phone || form.email) && (
            <p className="text-xs text-[#566076]">
              {[form.phone, form.email].filter(Boolean).join(' · ')}
            </p>
          )}
          {form.tax_number && (
            <p className="text-xs text-[#566076]">
              {form.tax_label || t('bill.taxNumber')}: {form.tax_number}
            </p>
          )}
        </div>
        <div className="text-end">
          <p className="text-lg" style={{ color: accent }}>
            {form.title || t('bill.defaultTitle')}
          </p>
          <p className="text-xs text-[#566076]">{form.invoice_prefix}000123</p>
        </div>
      </div>
      <p className="text-xs text-[#566076]">{t('bill.previewLines')}</p>
      {footer.length > 0 && (
        <div className="space-y-1 border-t border-[#c8cdd8] pt-3 text-xs whitespace-pre-line text-[#566076]">
          {footer.map((text, index) => (
            <p key={index} style={index === 0 && form.thanks ? { color: accent } : undefined}>
              {text}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Panel title={title}>
      <div className="grid gap-4 md:grid-cols-2">{children}</div>
    </Panel>
  );
}

export function BillDesignPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const settings = useQuery({
    queryKey: [membership.tenant_id, 'bill-settings'],
    queryFn: () => unwrap(api.GET('/api/sales/bill-settings/')),
  });
  if (!settings.data) {
    return <PageTitle title={t('bill.title')} subtitle={t('bill.body')} />;
  }
  return <BillEditor settings={settings.data} />;
}

function BillEditor({ settings }: { settings: Settings }) {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const client = useQueryClient();
  const [form, setForm] = useState<Form>(() => withoutLogo(settings));
  const saved = (data: Settings | undefined) =>
    data && client.setQueryData([membership.tenant_id, 'bill-settings'], data);
  const save = useMutation({
    mutationFn: async (body: Form) => {
      await ensureCsrf();
      return unwrap(api.PATCH('/api/sales/bill-settings/', { body }));
    },
    onSuccess: saved,
  });
  const logo = useMutation({
    mutationFn: async (file: File | null) => {
      await ensureCsrf();
      if (file === null) return unwrap(api.DELETE('/api/sales/bill-settings/logo/'));
      const body = new FormData();
      body.append('logo', file);
      return unwrap(
        api.PUT('/api/sales/bill-settings/logo/', {
          body: body as never,
          // The browser sets the multipart boundary itself.
          bodySerializer: (value) => value as unknown as FormData,
        }),
      );
    },
    onSuccess: saved,
  });
  const editable = can(membership, 'members', 'update');
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  const text = (field: TextField) => form[field] ?? '';
  return (
    <>
      <PageTitle title={t('bill.title')} subtitle={t('bill.body')} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <form
          className="space-y-6"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate(form);
          }}
        >
          <fieldset disabled={!editable} className="space-y-6">
            <Panel title={t('bill.logo')}>
              <div className="flex flex-wrap items-center gap-4">
                {settings.logo ? (
                  <img
                    src={settings.logo}
                    alt={t('bill.logo')}
                    className="max-h-20 max-w-48 rounded-lg border border-line p-2"
                  />
                ) : (
                  <p className="text-sm text-muted">{t('bill.noLogo')}</p>
                )}
                <label className="btn btn-primary cursor-pointer !py-2.5 !text-sm">
                  {t('bill.chooseLogo')}
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    className="sr-only"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) logo.mutate(file);
                      e.target.value = '';
                    }}
                  />
                </label>
                {settings.logo && (
                  <Button variant="ghost" onClick={() => logo.mutate(null)}>
                    {t('bill.removeLogo')}
                  </Button>
                )}
              </div>
              <p className="mt-3 text-xs text-muted">{t('bill.logoHint')}</p>
              {logo.isError && (
                <Alert tone="error">{errorText(logo.error, t('signIn.unavailable'))}</Alert>
              )}
            </Panel>
            <Section title={t('bill.details')}>
              <Field
                label={t('bill.address')}
                maxLength={300}
                value={text('address')}
                onChange={(e) => set({ address: e.target.value })}
              />
              <Field
                label={t('bill.phone')}
                maxLength={40}
                value={text('phone')}
                onChange={(e) => set({ phone: e.target.value })}
              />
              <Field
                label={t('bill.email')}
                type="email"
                value={text('email')}
                onChange={(e) => set({ email: e.target.value })}
              />
              <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                <Field
                  label={t('bill.taxLabel')}
                  placeholder="NTN"
                  maxLength={20}
                  value={text('tax_label')}
                  onChange={(e) => set({ tax_label: e.target.value })}
                />
                <Field
                  label={t('bill.taxNumber')}
                  maxLength={40}
                  value={text('tax_number')}
                  onChange={(e) => set({ tax_number: e.target.value })}
                />
              </div>
            </Section>
            <Section title={t('bill.wording')}>
              <Field
                label={t('bill.billTitle')}
                placeholder={t('bill.defaultTitle')}
                maxLength={40}
                value={text('title')}
                onChange={(e) => set({ title: e.target.value })}
                hint={t('bill.billTitleHint')}
              />
              <Field
                label={t('bill.prefix')}
                maxLength={10}
                value={text('invoice_prefix')}
                onChange={(e) => set({ invoice_prefix: e.target.value.toUpperCase() })}
                hint={t('bill.prefixHint')}
              />
            </Section>
            <Section title={t('bill.footer')}>
              <Field
                label={t('bill.thanks')}
                maxLength={200}
                value={text('thanks')}
                onChange={(e) => set({ thanks: e.target.value })}
              />
              <Area
                label={t('bill.paymentTerms')}
                maxLength={300}
                value={text('payment_terms')}
                onChange={(payment_terms) => set({ payment_terms })}
              />
              <Area
                label={t('bill.bankDetails')}
                maxLength={500}
                value={text('bank_details')}
                onChange={(bank_details) => set({ bank_details })}
              />
              <Area
                label={t('bill.returnPolicy')}
                maxLength={500}
                value={text('return_policy')}
                onChange={(return_policy) => set({ return_policy })}
              />
            </Section>
            <Section title={t('bill.look')}>
              <label className="block space-y-2">
                <span className="label">{t('bill.accent')}</span>
                <input
                  type="color"
                  value={form.accent ?? '#0b1a3c'}
                  onChange={(e) => set({ accent: e.target.value })}
                  className="h-12 w-24 cursor-pointer rounded-xl border border-line bg-canvas"
                />
                <span className="block text-xs text-muted">{t('bill.accentHint')}</span>
              </label>
              <Select
                label={t('bill.counterPaper')}
                value={form.counter_paper ?? 'a4'}
                onChange={(e) =>
                  set({ counter_paper: e.target.value === 'receipt' ? 'receipt' : 'a4' })
                }
              >
                <option value="a4">{t('bill.paperA4')}</option>
                <option value="receipt">{t('bill.paperReceipt')}</option>
              </Select>
              <div className="space-y-1 md:col-span-2">
                <Toggle
                  label={t('bill.showTax')}
                  checked={form.show_tax ?? true}
                  onChange={(show_tax) => set({ show_tax })}
                />
                <Toggle
                  label={t('bill.showDiscount')}
                  checked={form.show_discount ?? true}
                  onChange={(show_discount) => set({ show_discount })}
                />
                <Toggle
                  label={t('bill.showSku')}
                  checked={form.show_sku ?? false}
                  onChange={(show_sku) => set({ show_sku })}
                />
              </div>
            </Section>
          </fieldset>
          {save.isError && (
            <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
          )}
          {save.isSuccess && <Alert tone="success">{t('bill.saved')}</Alert>}
          {editable && (
            <Button type="submit" disabled={save.isPending}>
              {t('bill.save')}
            </Button>
          )}
        </form>
        <aside className="space-y-3 xl:sticky xl:top-6 xl:self-start">
          <h2 className="text-lg">{t('bill.preview')}</h2>
          <Preview form={form} logo={settings.logo ?? null} business={membership.tenant_name} />
        </aside>
      </div>
    </>
  );
}
