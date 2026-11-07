import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Button, Field, Hint, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import type { components } from '../../lib/api/schema';
import { can } from '../../lib/api/types';
import { ensureCsrf } from '../auth/session';
import { errorText, useWorkspace } from './hooks';
import { PageTitle, Panel } from './ui';

type Settings = components['schemas']['BillSettings'];
type Form = Omit<Settings, 'logo' | 'signature'>;
type Template = NonNullable<Form['template']>;
type ImageKind = 'logo' | 'signature';

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
  | 'invoice_prefix'
  | 'signature_text';

const TEMPLATES: Template[] = ['classic', 'modern', 'minimal', 'bold', 'compact', 'elegant'];
// The same limits as the server, checked here first only so a wrong file gets a quick answer.
const MAX_BYTES = 1024 * 1024;
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp'];

// Pictures are uploaded on their own, so they never go back with the other settings.
function withoutPictures(settings: Settings): Form {
  return Object.fromEntries(
    Object.entries(settings).filter(([key]) => key !== 'logo' && key !== 'signature'),
  );
}

function Area({
  label,
  value,
  maxLength,
  placeholder,
  hint,
  onChange,
}: {
  label: string;
  value: string;
  maxLength: number;
  placeholder: string;
  hint: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block space-y-2">
      <span className="label">{label}</span>
      <textarea
        rows={3}
        maxLength={maxLength}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-line bg-canvas px-4 py-3 outline-none placeholder:text-muted/70 focus:border-ink"
      />
      <Hint>{hint}</Hint>
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

/** A thumbnail drawn with boxes, so each template can be told apart at a glance. */
function TemplateThumb({ template, accent }: { template: Template; accent: string }) {
  const bar = 'h-1 rounded-full bg-[#c8cdd8]';
  const head: Record<Template, ReactNode> = {
    classic: (
      <div className="flex justify-between border-b pb-1" style={{ borderColor: accent }}>
        <div className="h-1.5 w-8 rounded-full" style={{ background: accent }} />
        <div className="h-1.5 w-5 rounded-full" style={{ background: accent }} />
      </div>
    ),
    modern: (
      <div className="flex justify-between rounded p-1.5" style={{ background: accent }}>
        <div className="h-1.5 w-8 rounded-full bg-white" />
        <div className="h-1.5 w-5 rounded-full bg-white" />
      </div>
    ),
    minimal: (
      <div className="flex justify-between pb-1">
        <div className="h-1 w-8 rounded-full bg-[#0b1a3c]" />
        <div className="h-1 w-6 rounded-full bg-[#c8cdd8]" />
      </div>
    ),
    bold: (
      <div className="space-y-1 border-t-4 pt-1" style={{ borderColor: accent }}>
        <div className="h-2.5 w-12 rounded-sm" style={{ background: accent }} />
      </div>
    ),
    compact: (
      <div className="flex justify-between border-b pb-0.5" style={{ borderColor: accent }}>
        <div className="h-1 w-6 rounded-full" style={{ background: accent }} />
        <div className="h-1 w-4 rounded-full" style={{ background: accent }} />
      </div>
    ),
    elegant: (
      <div
        className="flex flex-col items-center gap-0.5 border-b-4 border-double pb-1"
        style={{ borderColor: accent }}
      >
        <div className="h-1.5 w-10 rounded-full" style={{ background: accent }} />
        <div className="h-1 w-6 rounded-full bg-[#c8cdd8]" />
      </div>
    ),
  };
  const rows = template === 'compact' ? 5 : 3;
  return (
    <div className="space-y-1.5 rounded-lg border border-line bg-white p-2" aria-hidden="true">
      {head[template]}
      {template === 'bold' && <div className="h-1.5 rounded-sm" style={{ background: accent }} />}
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className={bar} />
      ))}
      <div
        className={`ms-auto h-1.5 w-8 rounded-full ${template === 'modern' ? '' : 'bg-[#0b1a3c]'}`}
        style={template === 'modern' ? { background: accent } : undefined}
      />
    </div>
  );
}

/** A rough picture of the top and bottom of the bill, so changes can be seen before printing. */
function Preview({
  form,
  logo,
  signature,
  business,
}: {
  form: Form;
  logo: string | null;
  signature: string | null;
  business: string;
}) {
  const { t } = useTranslation();
  const accent = form.accent ?? '#0b1a3c';
  const template = form.template ?? 'classic';
  const banded = template === 'modern';
  const centred = template === 'elegant';
  const footer = [form.thanks, form.payment_terms, form.bank_details, form.return_policy].filter(
    Boolean,
  );
  const muted = banded ? 'text-white/85' : 'text-[#566076]';
  return (
    <div
      className={`space-y-4 rounded-xl border border-line bg-white p-5 text-[#0b1a3c] ${
        template === 'compact' ? 'text-xs' : 'text-sm'
      } ${centred ? 'font-serif' : ''}`}
      style={template === 'bold' ? { borderTop: `6px solid ${accent}` } : undefined}
    >
      <div
        className={`gap-4 pb-3 ${centred ? 'flex flex-col items-center text-center' : 'flex justify-between'} ${
          banded ? 'rounded-lg p-4 text-white' : template === 'minimal' ? '' : 'border-b'
        } ${centred ? 'border-b-4 border-double' : ''}`}
        style={banded ? { background: accent } : { borderColor: accent }}
      >
        <div className="min-w-0 space-y-0.5">
          {logo && <img src={logo} alt="" className="mb-2 max-h-14 max-w-40" />}
          <p
            className="text-base font-semibold"
            style={banded || template === 'minimal' ? undefined : { color: accent }}
          >
            {business}
          </p>
          {form.address && <p className={`text-xs ${muted}`}>{form.address}</p>}
          {(form.phone || form.email) && (
            <p className={`text-xs ${muted}`}>
              {[form.phone, form.email].filter(Boolean).join(' · ')}
            </p>
          )}
          {form.tax_number && (
            <p className={`text-xs ${muted}`}>
              {form.tax_label || t('bill.taxNumber')}: {form.tax_number}
            </p>
          )}
        </div>
        <div className={centred ? '' : 'text-end'}>
          <p
            className={`${template === 'bold' ? 'text-2xl font-bold uppercase' : 'text-lg'} ${
              template === 'minimal' || centred ? 'tracking-widest uppercase' : ''
            }`}
            style={banded || template === 'minimal' ? undefined : { color: accent }}
          >
            {form.title || t('bill.defaultTitle')}
          </p>
          <p className={`text-xs ${muted}`}>{form.invoice_prefix || 'INV-'}000123</p>
        </div>
      </div>
      <p className="text-xs text-[#566076]">{t('bill.previewLines')}</p>
      {(signature || form.signature_text) && (
        <div className="ms-auto w-44 text-center">
          {signature ? (
            <img src={signature} alt="" className="mx-auto max-h-12" />
          ) : (
            <p className="font-serif text-xl italic" style={{ color: accent }}>
              {form.signature_text}
            </p>
          )}
          {signature && form.signature_text && <p className="text-xs">{form.signature_text}</p>}
          <p className="mt-1 border-t border-[#0b1a3c] pt-1 text-xs text-[#566076]">
            {t('bill.signatureLine')}
          </p>
        </div>
      )}
      {footer.length > 0 && (
        <div
          className={`space-y-1 border-t border-[#c8cdd8] pt-3 text-xs whitespace-pre-line text-[#566076] ${
            centred ? 'text-center' : ''
          }`}
        >
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

/** Choose, show and remove one picture: the logo or the signature. */
function PictureField({
  kind,
  current,
  onSaved,
}: {
  kind: ImageKind;
  current: string | null | undefined;
  onSaved: (data: Settings | undefined) => void;
}) {
  const { t } = useTranslation();
  const [problem, setProblem] = useState('');
  const path =
    kind === 'logo' ? '/api/sales/bill-settings/logo/' : '/api/sales/bill-settings/signature/';
  const change = useMutation({
    mutationFn: async (file: File | null) => {
      await ensureCsrf();
      if (file === null) return unwrap(api.DELETE(path));
      const body = new FormData();
      body.append('image', file);
      return unwrap(
        api.PUT(path, {
          body: body as never,
          // The browser sets the multipart boundary itself.
          bodySerializer: (value) => value as unknown as FormData,
        }),
      );
    },
    onSuccess: onSaved,
  });
  const choose = (file: File) => {
    setProblem('');
    if (!IMAGE_TYPES.includes(file.type) || file.size > MAX_BYTES) {
      setProblem(t('bill.pictureRules'));
      return;
    }
    change.mutate(file);
  };
  const label = kind === 'logo' ? t('bill.logo') : t('bill.signaturePicture');
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        {current ? (
          <img
            src={current}
            alt={label}
            className="max-h-20 max-w-48 rounded-lg border border-line p-2"
          />
        ) : (
          <p className="text-sm text-muted">
            {kind === 'logo' ? t('bill.noLogo') : t('bill.noSignaturePicture')}
          </p>
        )}
        <label className="btn btn-primary cursor-pointer !py-2.5 !text-sm">
          {kind === 'logo' ? t('bill.chooseLogo') : t('bill.chooseSignature')}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) choose(file);
              e.target.value = '';
            }}
          />
        </label>
        {current && (
          <Button variant="ghost" onClick={() => change.mutate(null)}>
            {t('bill.removePicture')}
          </Button>
        )}
      </div>
      <Hint>{t('bill.pictureRules')}</Hint>
      {problem && <Alert tone="error">{problem}</Alert>}
      {change.isError && (
        <Alert tone="error">{errorText(change.error, t('signIn.unavailable'))}</Alert>
      )}
    </div>
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
  const [form, setForm] = useState<Form>(() => withoutPictures(settings));
  const saved = (data: Settings | undefined) =>
    data && client.setQueryData([membership.tenant_id, 'bill-settings'], data);
  const save = useMutation({
    mutationFn: async (body: Form) => {
      await ensureCsrf();
      return unwrap(api.PATCH('/api/sales/bill-settings/', { body }));
    },
    onSuccess: saved,
  });
  const editable = can(membership, 'members', 'update');
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  const text = (field: TextField) => form[field] ?? '';
  const accent = form.accent ?? '#0b1a3c';
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
            <Panel title={t('bill.template')}>
              <p className="mb-4 text-sm text-muted">{t('bill.templateHint')}</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {TEMPLATES.map((template) => (
                  <label
                    key={template}
                    className={`cursor-pointer space-y-2 rounded-xl border p-3 ${
                      form.template === template ? 'border-ink' : 'border-line'
                    }`}
                  >
                    <input
                      type="radio"
                      name="template"
                      className="sr-only"
                      checked={form.template === template}
                      onChange={() => set({ template })}
                    />
                    <TemplateThumb template={template} accent={accent} />
                    <span className="block font-medium">{t(`bill.templates.${template}`)}</span>
                    <span className="block text-xs text-muted">
                      {t(`bill.templates.${template}Body`)}
                    </span>
                  </label>
                ))}
              </div>
            </Panel>
            <Panel title={t('bill.logo')}>
              <PictureField kind="logo" current={settings.logo} onSaved={saved} />
            </Panel>
            <Section title={t('bill.details')}>
              <Field
                label={t('bill.address')}
                placeholder={t('bill.placeholders.address')}
                hint={t('bill.hints.address')}
                maxLength={300}
                value={text('address')}
                onChange={(e) => set({ address: e.target.value })}
              />
              <Field
                label={t('bill.phone')}
                placeholder="0300 1234567"
                hint={t('bill.hints.phone')}
                inputMode="tel"
                maxLength={40}
                value={text('phone')}
                onChange={(e) => set({ phone: e.target.value })}
              />
              <Field
                label={t('bill.email')}
                type="email"
                placeholder="shop@example.com"
                hint={t('bill.hints.email')}
                value={text('email')}
                onChange={(e) => set({ email: e.target.value })}
              />
              <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3">
                <Field
                  label={t('bill.taxLabel')}
                  placeholder="NTN"
                  hint={t('bill.hints.taxLabel')}
                  maxLength={20}
                  value={text('tax_label')}
                  onChange={(e) => set({ tax_label: e.target.value })}
                />
                <Field
                  label={t('bill.taxNumber')}
                  placeholder="1234567-8"
                  hint={t('bill.hints.taxNumber')}
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
                placeholder="INV-"
                maxLength={10}
                value={text('invoice_prefix')}
                onChange={(e) => set({ invoice_prefix: e.target.value.toUpperCase() })}
                hint={t('bill.prefixHint')}
              />
            </Section>
            <Panel title={t('bill.signature')}>
              <div className="space-y-5">
                <p className="text-sm text-muted">{t('bill.signatureHint')}</p>
                <Field
                  label={t('bill.signatureText')}
                  placeholder={t('bill.placeholders.signatureText')}
                  hint={t('bill.hints.signatureText')}
                  maxLength={60}
                  value={text('signature_text')}
                  onChange={(e) => set({ signature_text: e.target.value })}
                />
                <PictureField kind="signature" current={settings.signature} onSaved={saved} />
              </div>
            </Panel>
            <Section title={t('bill.footer')}>
              <Field
                label={t('bill.thanks')}
                placeholder={t('bill.placeholders.thanks')}
                hint={t('bill.hints.thanks')}
                maxLength={200}
                value={text('thanks')}
                onChange={(e) => set({ thanks: e.target.value })}
              />
              <Area
                label={t('bill.paymentTerms')}
                placeholder={t('bill.placeholders.paymentTerms')}
                hint={t('bill.hints.paymentTerms')}
                maxLength={300}
                value={text('payment_terms')}
                onChange={(payment_terms) => set({ payment_terms })}
              />
              <Area
                label={t('bill.bankDetails')}
                placeholder={t('bill.placeholders.bankDetails')}
                hint={t('bill.hints.bankDetails')}
                maxLength={500}
                value={text('bank_details')}
                onChange={(bank_details) => set({ bank_details })}
              />
              <Area
                label={t('bill.returnPolicy')}
                placeholder={t('bill.placeholders.returnPolicy')}
                hint={t('bill.hints.returnPolicy')}
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
                  value={accent}
                  onChange={(e) => set({ accent: e.target.value })}
                  className="h-12 w-24 cursor-pointer rounded-xl border border-line bg-canvas"
                />
                <Hint>{t('bill.accentHint')}</Hint>
              </label>
              <div className="space-y-2">
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
                <Hint>{t('bill.hints.counterPaper')}</Hint>
              </div>
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
          <Preview
            form={form}
            logo={settings.logo ?? null}
            signature={settings.signature ?? null}
            business={membership.tenant_name}
          />
        </aside>
      </div>
    </>
  );
}
