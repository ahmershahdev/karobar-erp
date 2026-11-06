import { useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Field } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { today } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { ReportState } from '../sales/ledgers';
import { useWorkspace } from '../workspace/hooks';
import { NUM, TABLE, TD } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';

interface Section {
  lines: { code: string; name: string; amount: string }[];
  total: string;
}

function firstOfMonth(): string {
  return `${today().slice(0, 8)}01`;
}

function usePeriod(key: string, load: (query: { start: string; end: string }) => Promise<unknown>) {
  const { membership } = useWorkspace();
  const [start, setStart] = useState(firstOfMonth());
  const [end, setEnd] = useState(today());
  const report = useQuery({
    queryKey: [membership.tenant_id, 'report', key, start, end],
    enabled: Boolean(start && end),
    queryFn: () => load({ start, end }),
  });
  return { start, end, setStart, setEnd, report };
}

function Dates({
  start,
  end,
  onStart,
  onEnd,
}: {
  start?: string;
  end: string;
  onStart?: (value: string) => void;
  onEnd: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-4 sm:grid-cols-2 md:max-w-lg">
      {onStart && (
        <Field
          label={t('led.from')}
          type="date"
          value={start}
          onChange={(e) => onStart(e.target.value)}
        />
      )}
      <Field label={t('led.to')} type="date" value={end} onChange={(e) => onEnd(e.target.value)} />
    </div>
  );
}

function Rows({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto" data-lenis-prevent>
      <table className={TABLE}>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function SectionRows({ title, section }: { title: string; section: Section }) {
  const { t, i18n } = useTranslation();
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  return (
    <>
      <tr>
        <td className={`${TD} pt-6 font-medium`} colSpan={2}>
          {title}
        </td>
      </tr>
      {section.lines.map((line) => (
        <tr key={line.code} className="border-t border-line">
          <td className={`${TD} ps-4 text-muted`}>{line.name}</td>
          <td className={NUM}>{money(line.amount)}</td>
        </tr>
      ))}
      <tr className="border-t border-line">
        <td className={TD}>{t('rep.totalOf', { name: title })}</td>
        <td className={NUM}>{money(section.total)}</td>
      </tr>
    </>
  );
}

function Result({ label, value }: { label: string; value: string }) {
  const { i18n } = useTranslation();
  return (
    <tr className="border-t border-line-strong font-medium">
      <td className={`${TD} text-base`}>{label}</td>
      <td className={`${NUM} text-base`}>{formatMoney(value, i18n.resolvedLanguage)}</td>
    </tr>
  );
}

export function ProfitLossPage() {
  const { t } = useTranslation();
  const { start, end, setStart, setEnd, report } = usePeriod('profit-loss', (query) =>
    unwrap(api.GET('/api/reports/profit-loss/', { params: { query } })),
  );
  const data = report.data as
    | {
        income: Section;
        cost_of_sales: Section;
        gross_profit: string;
        expenses: Section;
        net_profit: string;
      }
    | undefined;
  return (
    <>
      <PageTitle title={t('rep.profitLoss')} subtitle={t('rep.profitLossBody')} />
      <Dates start={start} end={end} onStart={setStart} onEnd={setEnd} />
      <Panel title={t('rep.profitLoss')}>
        <ReportState pending={report.isPending} failed={report.isError} />
        {data && (
          <Rows>
            <SectionRows title={t('rep.income')} section={data.income} />
            <SectionRows title={t('rep.costOfSales')} section={data.cost_of_sales} />
            <Result label={t('rep.grossProfit')} value={data.gross_profit} />
            <SectionRows title={t('rep.expenses')} section={data.expenses} />
            <Result label={t('rep.netProfit')} value={data.net_profit} />
          </Rows>
        )}
      </Panel>
    </>
  );
}

export function BalanceSheetPage() {
  const { t } = useTranslation();
  const { end, setEnd, report } = usePeriod('balance-sheet', (query) =>
    unwrap(api.GET('/api/reports/balance-sheet/', { params: { query } })),
  );
  const data = report.data as
    | {
        assets: Section;
        liabilities: Section;
        equity: Section;
        profit_to_date: string;
        total_liabilities_and_equity: string;
        balanced: boolean;
      }
    | undefined;
  return (
    <>
      <PageTitle title={t('rep.balanceSheet')} subtitle={t('rep.balanceSheetBody')} />
      <Dates end={end} onEnd={setEnd} />
      <Panel title={t('rep.balanceSheet')}>
        <ReportState pending={report.isPending} failed={report.isError} />
        {data && (
          <>
            {!data.balanced && <Alert tone="error">{t('rep.notBalanced')}</Alert>}
            <Rows>
              <SectionRows title={t('rep.assets')} section={data.assets} />
              <Result label={t('rep.totalAssets')} value={data.assets.total} />
              <SectionRows title={t('rep.liabilities')} section={data.liabilities} />
              <SectionRows title={t('rep.equity')} section={data.equity} />
              <Result label={t('rep.profitToDate')} value={data.profit_to_date} />
              <Result
                label={t('rep.totalOwedAndOwned')}
                value={data.total_liabilities_and_equity}
              />
            </Rows>
          </>
        )}
      </Panel>
    </>
  );
}

function Amount({ label, value }: { label: string; value: string }) {
  const { i18n } = useTranslation();
  return (
    <tr className="border-t border-line">
      <td className={TD}>{label}</td>
      <td className={NUM}>{formatMoney(value, i18n.resolvedLanguage)}</td>
    </tr>
  );
}

export function CashFlowPage() {
  const { t } = useTranslation();
  const { start, end, setStart, setEnd, report } = usePeriod('cash-flow', (query) =>
    unwrap(api.GET('/api/reports/cash-flow/', { params: { query } })),
  );
  const data = report.data as
    | {
        opening: string;
        from_customers: string;
        to_suppliers: string;
        other: string;
        closing: string;
      }
    | undefined;
  return (
    <>
      <PageTitle title={t('rep.cashFlow')} subtitle={t('rep.cashFlowBody')} />
      <Dates start={start} end={end} onStart={setStart} onEnd={setEnd} />
      <Panel title={t('rep.cashFlow')}>
        <ReportState pending={report.isPending} failed={report.isError} />
        {data && (
          <Rows>
            <Amount label={t('rep.cashAtStart')} value={data.opening} />
            <Amount label={t('rep.fromCustomers')} value={data.from_customers} />
            <Amount label={t('rep.toSuppliers')} value={data.to_suppliers} />
            <Amount label={t('rep.otherMoney')} value={data.other} />
            <Result label={t('rep.cashAtEnd')} value={data.closing} />
          </Rows>
        )}
      </Panel>
    </>
  );
}

export function SalesTaxPage() {
  const { t } = useTranslation();
  const { start, end, setStart, setEnd, report } = usePeriod('sales-tax', (query) =>
    unwrap(api.GET('/api/reports/sales-tax/', { params: { query } })),
  );
  const data = report.data as
    | {
        taxable_sales: string;
        output_tax: string;
        taxable_purchases: string;
        input_tax: string;
        payable: string;
      }
    | undefined;
  return (
    <>
      <PageTitle title={t('rep.salesTax')} subtitle={t('rep.salesTaxBody')} />
      <Dates start={start} end={end} onStart={setStart} onEnd={setEnd} />
      <Panel title={t('rep.salesTax')}>
        <ReportState pending={report.isPending} failed={report.isError} />
        {data && (
          <Rows>
            <Amount label={t('rep.taxableSales')} value={data.taxable_sales} />
            <Amount label={t('rep.outputTax')} value={data.output_tax} />
            <Amount label={t('rep.taxablePurchases')} value={data.taxable_purchases} />
            <Amount label={t('rep.inputTax')} value={data.input_tax} />
            <Result
              label={t(Number(data.payable) < 0 ? 'rep.taxToClaim' : 'rep.taxToPay')}
              value={data.payable}
            />
          </Rows>
        )}
      </Panel>
    </>
  );
}
