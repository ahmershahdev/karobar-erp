import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Field } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { can } from '../../lib/api/types';
import { today } from '../../lib/dates';
import { ActionError } from '../purchasing/pages';
import { useTenantAction, useWorkspace } from '../workspace/hooks';
import { TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';

export function useTaxRates() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'tax-rates'],
    queryFn: () => unwrap(api.GET('/api/accounting/tax-rates/')),
  });
}

/** The rates to pick from on a sale, for people who sell but don't manage accounting. */
export function useSaleTaxRates() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'tax-rates', 'sale'],
    queryFn: () => unwrap(api.GET('/api/sales/tax-rates/')),
  });
}

export function TaxRatesPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const rates = useTaxRates();
  const save = useTenantAction(['tax-rates']);
  const empty = { name: '', rate: '', from: today(), to: '', source: '' };
  const [form, setForm] = useState(empty);
  const set = (patch: Partial<typeof empty>) => setForm({ ...form, ...patch });
  return (
    <>
      <PageTitle title={t('tax.title')} subtitle={t('tax.body')} />
      {can(membership, 'accounting', 'create') && (
        <Panel title={t('tax.new')}>
          <form
            className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"
            onSubmit={(event) => {
              event.preventDefault();
              const body = {
                name: form.name,
                rate: form.rate,
                valid_from: form.from,
                valid_to: form.to || null,
                source: form.source,
              } as never;
              save.mutate(() => unwrap(api.POST('/api/accounting/tax-rates/', { body })), {
                onSuccess: () => setForm(empty),
              });
            }}
          >
            <Field
              label={t('pur.name')}
              required
              maxLength={80}
              value={form.name}
              onChange={(e) => set({ name: e.target.value })}
            />
            <Field
              label={t('tax.percent')}
              required
              inputMode="decimal"
              value={form.rate}
              onChange={(e) => set({ rate: e.target.value })}
            />
            <Field
              label={t('tax.from')}
              type="date"
              required
              value={form.from}
              onChange={(e) => set({ from: e.target.value })}
            />
            <Field
              label={t('tax.to')}
              type="date"
              value={form.to}
              onChange={(e) => set({ to: e.target.value })}
            />
            <div className="md:col-span-2 xl:col-span-4">
              <Field
                label={t('tax.source')}
                hint={t('tax.sourceHint')}
                required
                maxLength={255}
                value={form.source}
                onChange={(e) => set({ source: e.target.value })}
              />
            </div>
            <div className="md:col-span-2 xl:col-span-4">
              <Button type="submit" disabled={save.isPending}>
                {t('tax.add')}
              </Button>
            </div>
          </form>
          <div className="mt-4">
            <ActionError error={save.error} />
          </div>
        </Panel>
      )}
      <Panel title={t('tax.title')}>
        {rates.data?.length === 0 ? (
          <p className="text-muted">{t('tax.none')}</p>
        ) : (
          <div className="overflow-x-auto" data-lenis-prevent>
            <table className={`${TABLE} min-w-[36rem]`}>
              <thead>
                <tr>
                  <th className={TH}>{t('pur.name')}</th>
                  <th className={TH}>{t('tax.percent')}</th>
                  <th className={TH}>{t('tax.from')}</th>
                  <th className={TH}>{t('tax.to')}</th>
                  <th className={TH}>{t('tax.source')}</th>
                </tr>
              </thead>
              <tbody>
                {rates.data?.map((rate) => (
                  <tr key={rate.id} className="border-t border-line">
                    <td className={TD}>{rate.name}</td>
                    <td className={TD}>{Number(rate.rate)}%</td>
                    <td className={TD}>{rate.valid_from}</td>
                    <td className={TD}>{rate.valid_to ?? t('tax.noEnd')}</td>
                    <td className={`${TD} text-muted`}>{rate.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
