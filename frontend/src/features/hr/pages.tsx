import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmButton } from '../../components/ConfirmButton';
import { Alert, Button, Field, Hint, Select } from '../../components/form';
import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { allPages } from '../../lib/api/pages';
import type { components } from '../../lib/api/schema';
import { can } from '../../lib/api/types';
import { today } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { errorText, useTenantAction, useWorkspace } from '../workspace/hooks';
import { NUM, NUM_TH, TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';

type Employee = components['schemas']['Employee'];
type Structure = components['schemas']['SalaryStructure'];
type Contract = components['schemas']['Contract'];
type Pay = components['schemas']['Pay'];

// Every HR change can show on another HR screen, so each one refreshes all of them.
const KEYS = ['hr-employees', 'hr-departments', 'hr-structures', 'hr-contracts'];

function useDepartments() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'hr-departments'],
    queryFn: () => unwrap(api.GET('/api/hr/departments/')),
  });
}

function useStructures() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'hr-structures'],
    queryFn: () => unwrap(api.GET('/api/hr/salary-structures/')),
  });
}

function PayTable({ pay }: { pay: Pay }) {
  const { t, i18n } = useTranslation();
  const money = (value: string) => formatMoney(value, i18n.resolvedLanguage);
  return (
    <div className="overflow-x-auto" data-lenis-prevent>
      <table className={TABLE}>
        <tbody>
          {pay.lines.map((line, index) => (
            <tr key={index} className="border-t border-line">
              <td className={TD}>
                {line.name === 'Basic' ? t('hr.basic') : line.name}
                {!line.taxable && (
                  <span className="ms-2 text-xs text-muted">{t('hr.notTaxable')}</span>
                )}
              </td>
              <td className={NUM}>
                {line.kind === 'deduction' ? '- ' : ''}
                {money(line.amount)}
              </td>
            </tr>
          ))}
          <tr className="border-t border-line-strong">
            <td className={TD}>{t('hr.gross')}</td>
            <td className={NUM}>{money(pay.gross)}</td>
          </tr>
          <tr className="border-t border-line">
            <td className={TD}>{t('hr.deductions')}</td>
            <td className={NUM}>- {money(pay.deductions)}</td>
          </tr>
          <tr className="border-t border-line font-medium">
            <td className={TD}>{t('hr.net')}</td>
            <td className={NUM}>{money(pay.net)}</td>
          </tr>
        </tbody>
      </table>
      <Hint>{t('hr.beforeTax')}</Hint>
    </div>
  );
}

// Departments

export function DepartmentsPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const departments = useDepartments();
  const save = useTenantAction(KEYS);
  const remove = useTenantAction(KEYS);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  return (
    <>
      <PageTitle title={t('hr.departments')} subtitle={t('hr.departmentsBody')} />
      {can(membership, 'hr', 'create') && (
        <Panel title={t('hr.newDepartment')}>
          <form
            className="grid gap-4 md:grid-cols-[10rem_minmax(0,1fr)_auto] md:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate(
                () => unwrap(api.POST('/api/hr/departments/', { body: { code, name } as never })),
                {
                  onSuccess: () => {
                    setCode('');
                    setName('');
                  },
                },
              );
            }}
          >
            <Field
              label={t('hr.code')}
              placeholder="SALES"
              hint={t('hr.codeHint')}
              required
              maxLength={20}
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
            />
            <Field
              label={t('hr.departmentName')}
              placeholder={t('hr.departmentPlaceholder')}
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Button type="submit" disabled={save.isPending}>
              {t('hr.add')}
            </Button>
          </form>
          {save.isError && (
            <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
          )}
        </Panel>
      )}
      <Panel title={t('hr.departments')}>
        {departments.data?.length === 0 && <p className="text-muted">{t('hr.noDepartments')}</p>}
        {remove.isError && (
          <Alert tone="error">{errorText(remove.error, t('signIn.unavailable'))}</Alert>
        )}
        <ul className="divide-y divide-line">
          {departments.data?.map((department) => (
            <li key={department.id} className="flex items-center justify-between gap-3 py-3">
              <span>
                <span className="font-mono text-sm text-muted">{department.code}</span>{' '}
                {department.name}
              </span>
              {can(membership, 'hr', 'delete') && (
                <ConfirmButton
                  onConfirm={() =>
                    remove.mutate(() =>
                      unwrap(
                        api.DELETE('/api/hr/departments/{id}/', {
                          params: { path: { id: department.id } },
                        }),
                      ),
                    )
                  }
                >
                  {t('workspace.remove')}
                </ConfirmButton>
              )}
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}

// Salary structures

interface PartRow {
  key: number;
  name: string;
  kind: 'earning' | 'deduction';
  how: 'percent' | 'amount';
  value: string;
  taxable: boolean;
}

function toRows(structure: Structure | null): PartRow[] {
  return (structure?.components ?? []).map((part, index) => ({
    key: index,
    name: part.name,
    kind: part.kind,
    how: part.percent != null ? 'percent' : 'amount',
    value: part.percent ?? part.amount ?? '',
    taxable: part.taxable ?? true,
  }));
}

function StructureEditor({
  structure,
  onDone,
}: {
  structure: Structure | null;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const save = useTenantAction(KEYS);
  const [name, setName] = useState(structure?.name ?? '');
  const [rows, setRows] = useState<PartRow[]>(() => toRows(structure));
  const [basic, setBasic] = useState('50000');
  const update = (key: number, patch: Partial<PartRow>) =>
    setRows(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  const body = {
    name,
    components: rows.map((row) => ({
      name: row.name,
      kind: row.kind,
      amount: row.how === 'amount' ? row.value : null,
      percent: row.how === 'percent' ? row.value : null,
      taxable: row.taxable,
    })),
  } as never;
  const preview = useQuery({
    queryKey: ['hr-preview', structure?.id, basic],
    queryFn: () =>
      unwrap(
        api.GET('/api/hr/salary-structures/{id}/preview/', {
          params: { path: { id: structure?.id ?? 0 }, query: { basic } },
        }),
      ),
    enabled: structure !== null && /^\d+(\.\d{1,2})?$/.test(basic),
  });
  return (
    <Panel title={structure ? t('hr.editStructure') : t('hr.newStructure')}>
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(
            () =>
              structure
                ? unwrap(
                    api.PUT('/api/hr/salary-structures/{id}/', {
                      params: { path: { id: structure.id } },
                      body,
                    }),
                  )
                : unwrap(api.POST('/api/hr/salary-structures/', { body })),
            { onSuccess: onDone },
          );
        }}
      >
        <Field
          label={t('hr.structureName')}
          placeholder={t('hr.structurePlaceholder')}
          hint={t('hr.structureHint')}
          required
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <div className="space-y-3">
          <p className="label">{t('hr.parts')}</p>
          <Hint>{t('hr.partsHint')}</Hint>
          {rows.map((row) => (
            <div
              key={row.key}
              className="grid gap-2 rounded-xl border border-line p-3 md:grid-cols-[minmax(0,1fr)_8rem_9rem_7rem_auto_auto] md:items-center"
            >
              <input
                aria-label={t('hr.partName')}
                placeholder={t('hr.partPlaceholder')}
                maxLength={80}
                value={row.name}
                onChange={(e) => update(row.key, { name: e.target.value })}
                className="min-h-11 rounded-xl border border-line bg-canvas px-3"
              />
              <select
                aria-label={t('hr.partKind')}
                value={row.kind}
                onChange={(e) =>
                  update(row.key, {
                    kind: e.target.value === 'deduction' ? 'deduction' : 'earning',
                  })
                }
                className="min-h-11 rounded-xl border border-line bg-canvas px-2"
              >
                <option value="earning">{t('hr.earning')}</option>
                <option value="deduction">{t('hr.deduction')}</option>
              </select>
              <select
                aria-label={t('hr.partHow')}
                value={row.how}
                onChange={(e) =>
                  update(row.key, { how: e.target.value === 'amount' ? 'amount' : 'percent' })
                }
                className="min-h-11 rounded-xl border border-line bg-canvas px-2"
              >
                <option value="percent">{t('hr.percentOfBasic')}</option>
                <option value="amount">{t('hr.fixedAmount')}</option>
              </select>
              <input
                aria-label={t('hr.partValue')}
                type="number"
                required
                min="0"
                max={row.how === 'percent' ? '100' : undefined}
                step="0.01"
                inputMode="decimal"
                placeholder={row.how === 'percent' ? '45' : '3000'}
                value={row.value}
                onChange={(e) => update(row.key, { value: e.target.value })}
                className="min-h-11 rounded-xl border border-line bg-canvas px-3"
              />
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-5"
                  checked={row.taxable}
                  onChange={(e) => update(row.key, { taxable: e.target.checked })}
                />
                {t('hr.taxable')}
              </label>
              <Button
                variant="ghost"
                onClick={() => setRows(rows.filter((item) => item.key !== row.key))}
              >
                {t('workspace.remove')}
              </Button>
            </div>
          ))}
          <Button
            variant="ghost"
            onClick={() =>
              setRows([
                ...rows,
                {
                  key: Math.max(0, ...rows.map((row) => row.key)) + 1,
                  name: '',
                  kind: 'earning',
                  how: 'percent',
                  value: '',
                  taxable: true,
                },
              ])
            }
          >
            {t('hr.addPart')}
          </Button>
        </div>
        {structure && (
          <div className="space-y-3 rounded-xl bg-surface p-4">
            <Field
              label={t('hr.previewBasic')}
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={basic}
              onChange={(e) => setBasic(e.target.value)}
              hint={t('hr.previewHint')}
            />
            {preview.data && <PayTable pay={preview.data} />}
          </div>
        )}
        {save.isError && (
          <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
        )}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" disabled={save.isPending}>
            {t('hr.save')}
          </Button>
          <Button variant="ghost" onClick={onDone}>
            {t('workspace.cancel')}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

export function SalaryStructuresPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const structures = useStructures();
  const remove = useTenantAction(KEYS);
  const [editing, setEditing] = useState<Structure | 'new' | null>(null);
  return (
    <>
      <PageTitle title={t('hr.structures')} subtitle={t('hr.structuresBody')} />
      {editing ? (
        <StructureEditor
          key={editing === 'new' ? 'new' : editing.id}
          structure={editing === 'new' ? null : editing}
          onDone={() => setEditing(null)}
        />
      ) : (
        can(membership, 'hr', 'create') && (
          <Button onClick={() => setEditing('new')}>{t('hr.newStructure')}</Button>
        )
      )}
      <Panel title={t('hr.structures')}>
        {structures.data?.length === 0 && <p className="text-muted">{t('hr.noStructures')}</p>}
        <ul className="divide-y divide-line">
          {structures.data?.map((structure) => (
            <li
              key={structure.id}
              className="flex flex-wrap items-center justify-between gap-3 py-3"
            >
              <div>
                <div className="font-medium">{structure.name}</div>
                <div className="text-sm text-muted">
                  {structure.components
                    .map(
                      (part) =>
                        `${part.name} ${part.percent != null ? `${Number(part.percent)}%` : part.amount}`,
                    )
                    .join(' · ') || t('hr.basicOnly')}
                </div>
              </div>
              <div className="flex gap-2">
                {can(membership, 'hr', 'update') && (
                  <Button variant="ghost" onClick={() => setEditing(structure)}>
                    {t('workspace.edit')}
                  </Button>
                )}
                {can(membership, 'hr', 'delete') && (
                  <ConfirmButton
                    onConfirm={() =>
                      remove.mutate(() =>
                        unwrap(
                          api.DELETE('/api/hr/salary-structures/{id}/', {
                            params: { path: { id: structure.id } },
                          }),
                        ),
                      )
                    }
                  >
                    {t('workspace.remove')}
                  </ConfirmButton>
                )}
              </div>
            </li>
          ))}
        </ul>
        {remove.isError && (
          <Alert tone="error">{errorText(remove.error, t('signIn.unavailable'))}</Alert>
        )}
      </Panel>
    </>
  );
}

// Employees

const EMPTY = {
  code: '',
  full_name: '',
  job_title: '',
  department: '',
  phone: '',
  email: '',
  national_id: '',
  bank_account: '',
  joined_on: today(),
  left_on: '',
};
type EmployeeForm = typeof EMPTY;

function fromEmployee(employee: Employee): EmployeeForm {
  return {
    code: employee.code,
    full_name: employee.full_name,
    job_title: employee.job_title ?? '',
    department: employee.department ? String(employee.department) : '',
    phone: employee.phone ?? '',
    email: employee.email ?? '',
    national_id: employee.national_id ?? '',
    bank_account: employee.bank_account ?? '',
    joined_on: employee.joined_on,
    left_on: employee.left_on ?? '',
  };
}

function EmployeeEditor({ employee, onDone }: { employee: Employee | null; onDone: () => void }) {
  const { t } = useTranslation();
  const departments = useDepartments();
  const save = useTenantAction(KEYS);
  const [form, setForm] = useState<EmployeeForm>(() => (employee ? fromEmployee(employee) : EMPTY));
  const set = (patch: Partial<EmployeeForm>) => setForm({ ...form, ...patch });
  const body = {
    ...form,
    department: form.department ? Number(form.department) : null,
    left_on: form.left_on || null,
  } as never;
  const field = (key: keyof EmployeeForm, extra: Record<string, unknown> = {}) => ({
    value: form[key],
    onChange: (e: { target: { value: string } }) => set({ [key]: e.target.value }),
    ...extra,
  });
  return (
    <Panel title={employee ? t('hr.editEmployee') : t('hr.newEmployee')}>
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(
            () =>
              employee
                ? unwrap(
                    api.PATCH('/api/hr/employees/{id}/', {
                      params: { path: { id: employee.id } },
                      body,
                    }),
                  )
                : unwrap(api.POST('/api/hr/employees/', { body })),
            { onSuccess: onDone },
          );
        }}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Field
            label={t('hr.code')}
            placeholder="E-001"
            hint={t('hr.employeeCodeHint')}
            required
            maxLength={20}
            {...field('code')}
          />
          <Field
            label={t('hr.fullName')}
            placeholder={t('hr.fullNamePlaceholder')}
            required
            maxLength={150}
            {...field('full_name')}
          />
          <Field
            label={t('hr.jobTitle')}
            placeholder={t('hr.jobTitlePlaceholder')}
            maxLength={100}
            {...field('job_title')}
          />
          <Select label={t('hr.department')} {...field('department')}>
            <option value="">-</option>
            {departments.data
              ?.filter((department) => department.is_active !== false)
              .map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name}
                </option>
              ))}
          </Select>
          <Field
            label={t('hr.phone')}
            placeholder="0300 1234567"
            inputMode="tel"
            maxLength={40}
            {...field('phone')}
          />
          <Field
            label={t('hr.email')}
            type="email"
            placeholder="name@example.com"
            {...field('email')}
          />
          <Field
            label={t('hr.nationalId')}
            placeholder="35202-1234567-1"
            hint={t('hr.nationalIdHint')}
            maxLength={30}
            {...field('national_id')}
          />
          <Field
            label={t('hr.bankAccount')}
            placeholder="PK00 BANK 0000 0000 0000 0000"
            hint={t('hr.bankAccountHint')}
            maxLength={50}
            {...field('bank_account')}
          />
          <Field label={t('hr.joinedOn')} type="date" required {...field('joined_on')} />
          <Field
            label={t('hr.leftOn')}
            type="date"
            hint={t('hr.leftOnHint')}
            {...field('left_on')}
          />
        </div>
        {save.isError && (
          <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
        )}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" disabled={save.isPending}>
            {t('hr.save')}
          </Button>
          <Button variant="ghost" onClick={onDone}>
            {t('workspace.cancel')}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function ContractsPanel({ employee }: { employee: Employee }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const structures = useStructures();
  const save = useTenantAction(KEYS);
  const remove = useTenantAction(KEYS);
  const contracts = useQuery({
    queryKey: [membership.tenant_id, 'hr-contracts', employee.id],
    queryFn: () =>
      unwrap(api.GET('/api/hr/contracts/', { params: { query: { employee: employee.id } } })),
  });
  const empty = {
    kind: 'permanent',
    starts_on: today(),
    ends_on: '',
    structure: '',
    basic_salary: '',
  };
  const [form, setForm] = useState(empty);
  const set = (patch: Partial<typeof empty>) => setForm({ ...form, ...patch });
  const kinds = ['permanent', 'fixed_term', 'probation'] as const;
  return (
    <Panel title={t('hr.contractsFor', { name: employee.full_name })}>
      <div className="space-y-4">
        {contracts.data?.results.length === 0 && (
          <p className="text-muted">{t('hr.noContracts')}</p>
        )}
        {contracts.data?.results.map((contract: Contract) => (
          <div key={contract.id} className="space-y-2 rounded-xl border border-line p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">
                {t(`hr.kinds.${contract.kind ?? 'permanent'}`)} · {contract.structure_name}
              </span>
              <span className="text-sm text-muted tabular-nums">
                {contract.starts_on} – {contract.ends_on ?? t('hr.noEnd')}
              </span>
            </div>
            <p className="text-sm">
              {t('hr.basic')}: {formatMoney(contract.basic_salary, i18n.resolvedLanguage)}
            </p>
            {contract.pay ? (
              <PayTable pay={contract.pay} />
            ) : (
              <Alert tone="error">{t('hr.payBroken')}</Alert>
            )}
            {can(membership, 'hr', 'delete') && (
              <ConfirmButton
                onConfirm={() =>
                  remove.mutate(() =>
                    unwrap(
                      api.DELETE('/api/hr/contracts/{id}/', {
                        params: { path: { id: contract.id } },
                      }),
                    ),
                  )
                }
              >
                {t('workspace.remove')}
              </ConfirmButton>
            )}
          </div>
        ))}
        {remove.isError && (
          <Alert tone="error">{errorText(remove.error, t('signIn.unavailable'))}</Alert>
        )}
        {can(membership, 'hr', 'create') && (
          <form
            className="space-y-4 rounded-xl bg-surface p-4"
            onSubmit={(event) => {
              event.preventDefault();
              const body = {
                employee: employee.id,
                kind: form.kind,
                starts_on: form.starts_on,
                ends_on: form.ends_on || null,
                structure: Number(form.structure),
                basic_salary: form.basic_salary,
              } as never;
              save.mutate(() => unwrap(api.POST('/api/hr/contracts/', { body })), {
                onSuccess: () => setForm(empty),
              });
            }}
          >
            <p className="font-medium">{t('hr.newContract')}</p>
            <Hint>{t('hr.contractHint')}</Hint>
            <div className="grid gap-4 md:grid-cols-2">
              <Select
                label={t('hr.contractKind')}
                value={form.kind}
                onChange={(e) => set({ kind: e.target.value })}
              >
                {kinds.map((kind) => (
                  <option key={kind} value={kind}>
                    {t(`hr.kinds.${kind}`)}
                  </option>
                ))}
              </Select>
              <Select
                label={t('hr.structure')}
                required
                value={form.structure}
                onChange={(e) => set({ structure: e.target.value })}
              >
                <option value="">-</option>
                {structures.data
                  ?.filter((structure) => structure.is_active !== false)
                  .map((structure) => (
                    <option key={structure.id} value={structure.id}>
                      {structure.name}
                    </option>
                  ))}
              </Select>
              <Field
                label={t('hr.startsOn')}
                type="date"
                required
                value={form.starts_on}
                onChange={(e) => set({ starts_on: e.target.value })}
              />
              <Field
                label={t('hr.endsOn')}
                type="date"
                hint={t('hr.endsOnHint')}
                value={form.ends_on}
                onChange={(e) => set({ ends_on: e.target.value })}
              />
              <Field
                label={t('hr.basicSalary')}
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                placeholder="50000"
                hint={t('hr.basicSalaryHint')}
                required
                value={form.basic_salary}
                onChange={(e) => set({ basic_salary: e.target.value })}
              />
            </div>
            {save.isError && (
              <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
            )}
            <Button type="submit" disabled={save.isPending}>
              {t('hr.addContract')}
            </Button>
          </form>
        )}
      </div>
    </Panel>
  );
}

export function EmployeesPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const [term, setTerm] = useState('');
  const [status, setStatus] = useState<'active' | 'left' | ''>('active');
  const [editing, setEditing] = useState<Employee | 'new' | null>(null);
  const [viewing, setViewing] = useState<Employee | null>(null);
  const employees = useQuery({
    queryKey: [membership.tenant_id, 'hr-employees', term, status],
    // Every page, as the customer list does, so a filter never stops at the first 50.
    queryFn: async () => ({
      results: await allPages((cursor) =>
        unwrap(
          api.GET('/api/hr/employees/', {
            params: {
              query: {
                ...(term ? { q: term } : {}),
                ...(status ? { status } : {}),
                page_size: 200,
                cursor,
              } as never,
            },
          }),
        ),
      ),
    }),
  });
  return (
    <>
      <PageTitle title={t('hr.employees')} subtitle={t('hr.employeesBody')} />
      {editing ? (
        <EmployeeEditor
          key={editing === 'new' ? 'new' : editing.id}
          employee={editing === 'new' ? null : editing}
          onDone={() => setEditing(null)}
        />
      ) : (
        can(membership, 'hr', 'create') && (
          <Button onClick={() => setEditing('new')}>{t('hr.newEmployee')}</Button>
        )
      )}
      {viewing && <ContractsPanel key={viewing.id} employee={viewing} />}
      <Panel title={t('hr.employees')}>
        <div className="mb-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_12rem]">
          <Field
            label={t('hr.search')}
            placeholder={t('hr.searchPlaceholder')}
            value={term}
            onChange={(e) => setTerm(e.target.value)}
          />
          <Select
            label={t('hr.show')}
            value={status}
            onChange={(e) => {
              const value = e.target.value;
              setStatus(value === 'active' || value === 'left' ? value : '');
            }}
          >
            <option value="active">{t('hr.working')}</option>
            <option value="left">{t('hr.left')}</option>
            <option value="">{t('hr.everyone')}</option>
          </Select>
        </div>
        {employees.data?.results.length === 0 && (
          <p className="text-muted">{t('hr.noEmployees')}</p>
        )}
        <div className="overflow-x-auto" data-lenis-prevent>
          <table className={TABLE}>
            <thead>
              <tr>
                <th className={TH}>{t('hr.fullName')}</th>
                <th className={TH}>{t('hr.jobTitle')}</th>
                <th className={TH}>{t('hr.department')}</th>
                <th className={NUM_TH}>{t('hr.basic')}</th>
                <th className={TH} />
              </tr>
            </thead>
            <tbody>
              {employees.data?.results.map((employee) => (
                <tr key={employee.id} className="border-t border-line">
                  <td className={TD}>
                    <button
                      type="button"
                      className="text-start underline underline-offset-4"
                      onClick={() => setViewing(employee)}
                    >
                      {employee.full_name}
                    </button>
                    <div className="font-mono text-xs text-muted">{employee.code}</div>
                  </td>
                  <td className={TD}>{employee.job_title}</td>
                  <td className={TD}>{employee.department_name ?? '-'}</td>
                  <td className={NUM}>
                    {employee.current_contract
                      ? formatMoney(employee.current_contract.basic_salary, i18n.resolvedLanguage)
                      : t('hr.noContract')}
                  </td>
                  <td className={`${TD} text-end`}>
                    {can(membership, 'hr', 'update') && (
                      <Button variant="ghost" onClick={() => setEditing(employee)}>
                        {t('workspace.edit')}
                      </Button>
                    )}
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
