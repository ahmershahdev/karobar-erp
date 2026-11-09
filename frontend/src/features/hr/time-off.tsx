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
import { errorText, useTenantAction, useWorkspace } from '../workspace/hooks';
import { NUM, NUM_TH, TABLE, TD, TH } from '../workspace/table';
import { PageTitle, Panel } from '../workspace/ui';
import { PROVINCES } from './provinces';

type Settings = components['schemas']['HrSettings'];
type DayEntry = components['schemas']['DayEntry'];

const KEYS = ['hr-employees', 'hr-leave', 'hr-leave-types', 'hr-holidays', 'hr-settings', 'hr-day'];
// Monday first, as the weekday numbers count: Monday is 0, Sunday is 6.
const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

function useEmployees() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'hr-employees', 'working'],
    queryFn: () =>
      allPages((cursor) =>
        unwrap(
          api.GET('/api/hr/employees/', {
            params: { query: { status: 'active', page_size: 200, cursor } as never },
          }),
        ),
      ),
  });
}

function useLeaveTypes() {
  const { membership } = useWorkspace();
  return useQuery({
    queryKey: [membership.tenant_id, 'hr-leave-types'],
    queryFn: () => unwrap(api.GET('/api/hr/leave-types/')),
  });
}

function weekdayName(day: number, locale: string | undefined): string {
  // 5 January 2026 was a Monday, so adding the weekday number gives that day's name.
  return new Intl.DateTimeFormat(locale, { weekday: 'long' }).format(new Date(2026, 0, 5 + day));
}

// Leave

function LeaveTypes() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const kinds = useLeaveTypes();
  const save = useTenantAction(KEYS);
  const [name, setName] = useState('');
  const [days, setDays] = useState('');
  const [paid, setPaid] = useState(true);
  return (
    <Panel title={t('hr.leaveTypes')}>
      <ul className="mb-4 divide-y divide-line">
        {kinds.data?.map((kind) => (
          <li key={kind.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <span>
              <span className="font-medium">{kind.name}</span>{' '}
              <span className="text-sm text-muted">
                {Number(kind.days_per_year) > 0
                  ? t('hr.daysAYear', { days: Number(kind.days_per_year) })
                  : t('hr.noLimit')}{' '}
                · {kind.paid === false ? t('hr.unpaid') : t('hr.paid')}
              </span>
            </span>
            {can(membership, 'hr', 'delete') && (
              <ConfirmButton
                onConfirm={() =>
                  save.mutate(() =>
                    unwrap(
                      api.DELETE('/api/hr/leave-types/{id}/', {
                        params: { path: { id: kind.id } },
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
      {can(membership, 'hr', 'create') && (
        <form
          className="grid gap-4 md:grid-cols-[minmax(0,1fr)_10rem_auto_auto] md:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            const body = { name, days_per_year: days || '0', paid } as never;
            save.mutate(() => unwrap(api.POST('/api/hr/leave-types/', { body })), {
              onSuccess: () => {
                setName('');
                setDays('');
              },
            });
          }}
        >
          <Field
            label={t('hr.leaveTypeName')}
            placeholder={t('hr.leaveTypePlaceholder')}
            required
            maxLength={60}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Field
            label={t('hr.daysPerYear')}
            type="number"
            min="0"
            max="366"
            step="0.5"
            inputMode="decimal"
            placeholder="14"
            hint={t('hr.daysPerYearHint')}
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
          <label className="flex min-h-11 items-center gap-2">
            <input
              type="checkbox"
              className="size-5"
              checked={paid}
              onChange={(e) => setPaid(e.target.checked)}
            />
            {t('hr.paid')}
          </label>
          <Button type="submit" disabled={save.isPending}>
            {t('hr.add')}
          </Button>
        </form>
      )}
      {save.isError && <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>}
    </Panel>
  );
}

function Balances({ employee }: { employee: number }) {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const balances = useQuery({
    queryKey: [membership.tenant_id, 'hr-leave', 'balances', employee],
    queryFn: () => unwrap(api.GET('/api/hr/leave/balances/', { params: { query: { employee } } })),
  });
  if (!balances.data?.length) return null;
  return (
    <div className="overflow-x-auto" data-lenis-prevent>
      <table className={TABLE}>
        <thead>
          <tr>
            <th className={TH}>{t('hr.leaveType')}</th>
            <th className={NUM_TH}>{t('hr.taken')}</th>
            <th className={NUM_TH}>{t('hr.waiting')}</th>
            <th className={NUM_TH}>{t('hr.leftThisYear')}</th>
          </tr>
        </thead>
        <tbody>
          {balances.data.map((row) => (
            <tr key={row.leave_type} className="border-t border-line">
              <td className={TD}>{row.name}</td>
              <td className={NUM}>{Number(row.taken)}</td>
              <td className={NUM}>{Number(row.pending)}</td>
              <td className={NUM}>{row.left == null ? t('hr.noLimit') : Number(row.left)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LeavePage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const employees = useEmployees();
  const kinds = useLeaveTypes();
  const save = useTenantAction(KEYS);
  const empty = { employee: '', leave_type: '', starts_on: today(), ends_on: today(), note: '' };
  const [form, setForm] = useState(empty);
  const [status, setStatus] = useState<'pending' | 'approved' | 'rejected' | 'cancelled' | ''>(
    'pending',
  );
  const set = (patch: Partial<typeof empty>) => setForm({ ...form, ...patch });
  const requests = useQuery({
    queryKey: [membership.tenant_id, 'hr-leave', status],
    queryFn: () =>
      allPages((cursor) =>
        unwrap(
          api.GET('/api/hr/leave/', {
            params: { query: { ...(status ? { status } : {}), page_size: 200, cursor } as never },
          }),
        ),
      ),
  });
  const decide = (id: number, approve: boolean) =>
    save.mutate(() =>
      unwrap(
        approve
          ? api.POST('/api/hr/leave/{id}/approve/', { params: { path: { id } } })
          : api.POST('/api/hr/leave/{id}/reject/', { params: { path: { id } } }),
      ),
    );
  return (
    <>
      <PageTitle title={t('hr.leave')} subtitle={t('hr.leaveBody')} />
      {can(membership, 'hr', 'create') && (
        <Panel title={t('hr.askLeave')}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const body = {
                ...form,
                employee: Number(form.employee),
                leave_type: Number(form.leave_type),
              } as never;
              save.mutate(() => unwrap(api.POST('/api/hr/leave/', { body })), {
                onSuccess: () => setForm({ ...empty, employee: form.employee }),
              });
            }}
          >
            <div className="grid gap-4 md:grid-cols-2">
              <Select
                label={t('hr.employee')}
                required
                value={form.employee}
                onChange={(e) => set({ employee: e.target.value })}
              >
                <option value="">-</option>
                {employees.data?.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </Select>
              <Select
                label={t('hr.leaveType')}
                required
                value={form.leave_type}
                onChange={(e) => set({ leave_type: e.target.value })}
              >
                <option value="">-</option>
                {kinds.data
                  ?.filter((kind) => kind.is_active !== false)
                  .map((kind) => (
                    <option key={kind.id} value={kind.id}>
                      {kind.name}
                    </option>
                  ))}
              </Select>
              <Field
                label={t('hr.from')}
                type="date"
                required
                value={form.starts_on}
                onChange={(e) => set({ starts_on: e.target.value })}
              />
              <Field
                label={t('hr.to')}
                type="date"
                required
                value={form.ends_on}
                onChange={(e) => set({ ends_on: e.target.value })}
              />
              <Field
                label={t('hr.reason')}
                placeholder={t('hr.reasonPlaceholder')}
                maxLength={255}
                value={form.note}
                onChange={(e) => set({ note: e.target.value })}
              />
            </div>
            <Hint>{t('hr.askLeaveHint')}</Hint>
            {form.employee && <Balances employee={Number(form.employee)} />}
            <Button type="submit" disabled={save.isPending}>
              {t('hr.askLeaveButton')}
            </Button>
          </form>
        </Panel>
      )}
      {save.isError && <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>}
      <Panel title={t('hr.leaveRequests')}>
        <div className="mb-4 max-w-xs">
          <Select
            label={t('hr.show')}
            value={status}
            onChange={(e) => {
              const value = e.target.value;
              setStatus(
                value === 'pending' ||
                  value === 'approved' ||
                  value === 'rejected' ||
                  value === 'cancelled'
                  ? value
                  : '',
              );
            }}
          >
            <option value="pending">{t('hr.statuses.pending')}</option>
            <option value="approved">{t('hr.statuses.approved')}</option>
            <option value="rejected">{t('hr.statuses.rejected')}</option>
            <option value="cancelled">{t('hr.statuses.cancelled')}</option>
            <option value="">{t('hr.everyone')}</option>
          </Select>
        </div>
        {requests.data?.length === 0 && <p className="text-muted">{t('hr.noLeave')}</p>}
        <ul className="divide-y divide-line">
          {requests.data?.map((request) => (
            <li key={request.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <div className="font-medium">
                  {request.employee_name} · {request.leave_type_name}
                </div>
                <div className="text-sm text-muted tabular-nums">
                  {request.starts_on} – {request.ends_on} ·{' '}
                  {t('hr.workingDays', { days: Number(request.days) })} ·{' '}
                  {t(`hr.statuses.${request.status}`)}
                </div>
                {request.note && <div className="text-sm">{request.note}</div>}
              </div>
              {request.status === 'pending' && (
                <div className="flex flex-wrap gap-2">
                  {can(membership, 'hr', 'post') && (
                    <>
                      <Button onClick={() => decide(request.id, true)} disabled={save.isPending}>
                        {t('hr.approve')}
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => decide(request.id, false)}
                        disabled={save.isPending}
                      >
                        {t('hr.reject')}
                      </Button>
                    </>
                  )}
                  {can(membership, 'hr', 'delete') && (
                    <ConfirmButton
                      onConfirm={() =>
                        save.mutate(() =>
                          unwrap(
                            api.DELETE('/api/hr/leave/{id}/', {
                              params: { path: { id: request.id } },
                            }),
                          ),
                        )
                      }
                    >
                      {t('hr.withdraw')}
                    </ConfirmButton>
                  )}
                </div>
              )}
              {request.status === 'approved' && can(membership, 'hr', 'post') && (
                <CancelLeave id={request.id} starts={request.starts_on} ends={request.ends_on} />
              )}
            </li>
          ))}
        </ul>
      </Panel>
      <LeaveTypes />
    </>
  );
}

function CancelLeave({ id, starts, ends }: { id: number; starts: string; ends: string }) {
  const { t } = useTranslation();
  const save = useTenantAction(KEYS);
  const [backOn, setBackOn] = useState('');
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Field
        label={t('hr.backOn')}
        type="date"
        min={starts}
        max={ends}
        hint={t('hr.backOnHint')}
        value={backOn}
        onChange={(e) => setBackOn(e.target.value)}
      />
      <ConfirmButton
        message={backOn ? t('hr.cancelSomeConfirm') : t('hr.cancelAllConfirm')}
        disabled={save.isPending}
        onConfirm={() =>
          save.mutate(() =>
            unwrap(
              api.POST('/api/hr/leave/{id}/cancel/', {
                params: { path: { id } },
                body: { back_on: backOn || null },
              }),
            ),
          )
        }
      >
        {t('hr.cancelLeave')}
      </ConfirmButton>
      {save.isError && <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>}
    </div>
  );
}

// Attendance

export function AttendancePage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const [on, setOn] = useState(today());
  const [changes, setChanges] = useState<Record<number, { status: string; note: string }>>({});
  const save = useTenantAction(KEYS);
  const day = useQuery({
    queryKey: [membership.tenant_id, 'hr-day', on],
    queryFn: () => unwrap(api.GET('/api/hr/attendance/', { params: { query: { date: on } } })),
  });
  const value = (row: DayEntry) => changes[row.employee] ?? { status: row.status, note: row.note };
  const update = (row: DayEntry, patch: Partial<{ status: string; note: string }>) =>
    setChanges({ ...changes, [row.employee]: { ...value(row), ...patch } });
  const statuses = ['present', 'absent', 'half_day'] as const;
  return (
    <>
      <PageTitle title={t('hr.attendance')} subtitle={t('hr.attendanceBody')} />
      <Panel title={t('hr.markDay')}>
        <div className="mb-4 max-w-xs">
          <Field
            label={t('hr.day')}
            type="date"
            value={on}
            onChange={(e) => {
              setOn(e.target.value);
              setChanges({});
            }}
          />
        </div>
        {day.data && !day.data.working_day && (
          <Alert tone="success">
            {day.data.holiday
              ? t('hr.holidayToday', { name: day.data.holiday })
              : t('hr.weekendToday')}
          </Alert>
        )}
        {day.data?.people.length === 0 && <p className="text-muted">{t('hr.noEmployees')}</p>}
        <ul className="divide-y divide-line">
          {day.data?.people.map((row) => (
            <li
              key={row.employee}
              className="grid gap-2 py-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,16rem)] md:items-center"
            >
              <span>
                {row.full_name} <span className="font-mono text-xs text-muted">{row.code}</span>
                {row.on_leave && (
                  <span className="ms-2 rounded-full bg-raised px-2 py-0.5 text-xs">
                    {t('hr.onLeave')}
                  </span>
                )}
              </span>
              <div
                className="flex flex-wrap gap-1"
                role="radiogroup"
                aria-label={t('hr.attendanceFor', { name: row.full_name })}
              >
                {statuses.map((status) => (
                  <label
                    key={status}
                    className={`min-h-11 cursor-pointer rounded-full border px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-azure ${
                      value(row).status === status ? 'border-ink bg-raised' : 'border-line'
                    }`}
                  >
                    <input
                      type="radio"
                      className="sr-only"
                      name={`attendance-${row.employee}`}
                      checked={value(row).status === status}
                      onChange={() => update(row, { status })}
                    />
                    {t(`hr.attendanceStatus.${status}`)}
                  </label>
                ))}
              </div>
              <input
                aria-label={t('hr.note')}
                placeholder={t('hr.notePlaceholder')}
                maxLength={255}
                value={value(row).note}
                onChange={(e) => update(row, { note: e.target.value })}
                className="min-h-11 rounded-xl border border-line bg-canvas px-3"
              />
            </li>
          ))}
        </ul>
        <Hint>{t('hr.attendanceHint')}</Hint>
        {save.isError && (
          <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
        )}
        {save.isSuccess && <Alert tone="success">{t('hr.attendanceSaved')}</Alert>}
        {can(membership, 'hr', 'create') && (
          <Button
            className="mt-4"
            disabled={save.isPending || Object.keys(changes).length === 0}
            onClick={() => {
              const rows = Object.entries(changes).map(([employee, row]) => ({
                employee: Number(employee),
                ...row,
              }));
              save.mutate(
                () => unwrap(api.POST('/api/hr/attendance/', { body: { on, rows } as never })),
                {
                  onSuccess: () => setChanges({}),
                },
              );
            }}
          >
            {t('hr.saveDay')}
          </Button>
        )}
      </Panel>
    </>
  );
}

// Holidays and the working week

function WeekSettings({ settings }: { settings: Settings }) {
  const { t, i18n } = useTranslation();
  const { membership } = useWorkspace();
  const save = useTenantAction(KEYS);
  const [weekend, setWeekend] = useState<number[]>(settings.weekend);
  const [country, setCountry] = useState(settings.holiday_country);
  const [years, setYears] = useState(String(settings.id_retention_years ?? 6));
  const [province, setProvince] = useState<string>(settings.default_province ?? '');
  const editable = can(membership, 'hr', 'update');
  return (
    <Panel title={t('hr.workWeek')}>
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          const body = {
            weekend,
            holiday_country: country,
            id_retention_years: Number(years),
            default_province: province,
          } as never;
          save.mutate(() => unwrap(api.PATCH('/api/hr/settings/', { body })));
        }}
      >
        <fieldset disabled={!editable} className="space-y-5">
          <div className="space-y-2">
            <p className="label">{t('hr.weekendDays')}</p>
            <div className="flex flex-wrap gap-2">
              {WEEKDAYS.map((day) => (
                <label
                  key={day}
                  className="flex min-h-11 items-center gap-2 rounded-full border border-line px-3 focus-within:ring-2 focus-within:ring-azure"
                >
                  <input
                    type="checkbox"
                    className="size-5"
                    checked={weekend.includes(day)}
                    onChange={(e) =>
                      setWeekend(
                        e.target.checked
                          ? [...weekend, day].sort((a, b) => a - b)
                          : weekend.filter((d) => d !== day),
                      )
                    }
                  />
                  {weekdayName(day, i18n.resolvedLanguage)}
                </label>
              ))}
            </div>
            <Hint>{t('hr.weekendHint')}</Hint>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Select
              label={t('hr.holidayCountry')}
              value={country}
              onChange={(e) => setCountry(e.target.value as Settings['holiday_country'])}
            >
              <option value="PK">{t('hr.countries.PK')}</option>
              <option value="AE">{t('hr.countries.AE')}</option>
              <option value="SA">{t('hr.countries.SA')}</option>
            </Select>
            <Field
              label={t('hr.idRetention')}
              type="number"
              min="6"
              max="50"
              hint={t('hr.idRetentionHint')}
              value={years}
              onChange={(e) => setYears(e.target.value)}
            />
            <Select
              label={t('hr.defaultProvince')}
              hint={t('hr.defaultProvinceHint')}
              value={province}
              onChange={(e) => setProvince(e.target.value)}
            >
              <option value="">-</option>
              {PROVINCES.map((code) => (
                <option key={code} value={code}>
                  {t(`hr.provinces.${code}`)}
                </option>
              ))}
            </Select>
          </div>
        </fieldset>
        {save.isError && (
          <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
        )}
        {save.isSuccess && <Alert tone="success">{t('hr.saved')}</Alert>}
        {editable && (
          <Button type="submit" disabled={save.isPending}>
            {t('hr.save')}
          </Button>
        )}
      </form>
    </Panel>
  );
}

export function HolidaysPage() {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const [year, setYear] = useState(new Date().getFullYear());
  const save = useTenantAction(KEYS);
  const settings = useQuery({
    queryKey: [membership.tenant_id, 'hr-settings'],
    queryFn: () => unwrap(api.GET('/api/hr/settings/')),
  });
  const holidays = useQuery({
    queryKey: [membership.tenant_id, 'hr-holidays', year],
    queryFn: () => unwrap(api.GET('/api/hr/holidays/', { params: { query: { year } } })),
  });
  const [on, setOn] = useState('');
  const [name, setName] = useState('');
  return (
    <>
      <PageTitle title={t('hr.holidays')} subtitle={t('hr.holidaysBody')} />
      {settings.data && (
        <WeekSettings key={JSON.stringify(settings.data)} settings={settings.data} />
      )}
      <Panel title={t('hr.holidaysIn', { year })}>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <Field
            label={t('hr.year')}
            type="number"
            min="2000"
            max="2100"
            value={year}
            onChange={(e) => setYear(Number(e.target.value) || year)}
          />
          {can(membership, 'hr', 'create') && (
            <Button
              disabled={save.isPending}
              onClick={() =>
                save.mutate(() => unwrap(api.POST('/api/hr/holidays/fill/', { body: { year } })))
              }
            >
              {t('hr.fillHolidays')}
            </Button>
          )}
        </div>
        <Hint>{t('hr.fillHint')}</Hint>
        {holidays.data?.length === 0 && <p className="mt-3 text-muted">{t('hr.noHolidays')}</p>}
        <ul className="mt-3 divide-y divide-line">
          {holidays.data?.map((holiday) => (
            <li key={holiday.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <span>
                <span className="font-mono text-sm tabular-nums">{holiday.on}</span> {holiday.name}
                {holiday.source && (
                  <span className="block text-xs text-muted">{holiday.source}</span>
                )}
              </span>
              {can(membership, 'hr', 'delete') && (
                <ConfirmButton
                  onConfirm={() =>
                    save.mutate(() =>
                      unwrap(
                        api.DELETE('/api/hr/holidays/{id}/', {
                          params: { path: { id: holiday.id } },
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
        {can(membership, 'hr', 'create') && (
          <form
            className="mt-4 grid gap-4 md:grid-cols-[12rem_minmax(0,1fr)_auto] md:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate(
                () => unwrap(api.POST('/api/hr/holidays/', { body: { on, name } as never })),
                {
                  onSuccess: () => {
                    setOn('');
                    setName('');
                  },
                },
              );
            }}
          >
            <Field
              label={t('hr.day')}
              type="date"
              required
              value={on}
              onChange={(e) => setOn(e.target.value)}
            />
            <Field
              label={t('hr.holidayName')}
              placeholder={t('hr.holidayPlaceholder')}
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Button type="submit" disabled={save.isPending}>
              {t('hr.add')}
            </Button>
          </form>
        )}
        {save.isError && (
          <Alert tone="error">{errorText(save.error, t('signIn.unavailable'))}</Alert>
        )}
      </Panel>
    </>
  );
}
