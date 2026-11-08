import { useId, useState, type ComponentProps, type KeyboardEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { passwordChecks, passwordScore } from '../lib/password';

const INPUT =
  'w-full rounded-xl border border-line bg-canvas px-4 py-3.5 text-base outline-none transition-[border-color,box-shadow] placeholder:text-muted/70 focus:border-ink focus:shadow-[0_0_0_4px_var(--color-raised)] disabled:opacity-60';

export function Field({
  label,
  hint,
  ...props
}: { label: string; hint?: ReactNode } & ComponentProps<'input'>) {
  return (
    <label className="block space-y-2">
      <span className="label">{label}</span>
      <input {...props} className={INPUT} />
      {hint && <Hint>{hint}</Hint>}
    </label>
  );
}

// Red to amber to green, so the four steps read as a scale and not four shades of the accent.
const STRENGTH_COLORS = ['bg-red', 'bg-red', 'bg-yellow', 'bg-green', 'bg-green'];
const STRENGTH_TEXT = ['text-red', 'text-red', 'text-yellow', 'text-green', 'text-green'];

// A torch instead of the usual eye: switching it on shines light on the hidden password.
function Torch({ on }: { on: boolean }) {
  return (
    <svg viewBox="0 0 40 24" className="torch" data-on={on} aria-hidden="true">
      <path className="torch-beam" d="M15 8 0 1v22l15-7z" />
      <path className="torch-body" d="M15 6h3l3 3h15a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H21l-3 3h-3z" />
      <rect className="torch-switch" x="25" y="10.5" width="6" height="3" rx="1.5" />
    </svg>
  );
}

export function PasswordField({
  label,
  showStrength = false,
  ...props
}: { label: string; showStrength?: boolean } & Omit<ComponentProps<'input'>, 'type'>) {
  const { t } = useTranslation();
  const id = useId();
  const [visible, setVisible] = useState(false);
  const [caps, setCaps] = useState(false);
  const value = typeof props.value === 'string' ? props.value : '';
  const score = passwordScore(value);
  const checkCaps = (event: KeyboardEvent<HTMLInputElement>) => {
    setCaps(event.getModifierState('CapsLock'));
  };
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="label block">
        {label}
      </label>
      <div className="relative">
        <input
          {...props}
          id={id}
          type={visible ? 'text' : 'password'}
          onKeyUp={checkCaps}
          onKeyDown={checkCaps}
          className={`${INPUT} pe-12`}
        />
        <span aria-hidden="true" className="torch-glow" data-on={visible} />
        <button
          type="button"
          aria-label={visible ? t('auth.hide') : t('auth.show')}
          aria-pressed={visible}
          aria-controls={id}
          onClick={() => setVisible(!visible)}
          className="absolute inset-y-0 end-0 flex w-14 items-center justify-center text-muted transition-colors hover:text-ink"
        >
          <Torch on={visible} />
        </button>
      </div>
      {caps && (
        <p className="flex items-center gap-2 text-xs text-yellow" role="status">
          <span aria-hidden="true">&#8679;</span> {t('auth.caps')}
        </p>
      )}
      {showStrength && value && <StrengthMeter value={value} score={score} />}
    </div>
  );
}

// The meter fills as you type, even before the 12-character minimum, so it never sits blank
// and looks broken. Under it, three plain checks tick green as they are met.
function StrengthMeter({ value, score }: { value: string; score: number }) {
  const { t } = useTranslation();
  const checks = passwordChecks(value);
  const fill = score === 0 ? Math.min(checks.length / 12, 1) * 25 : score * 25;
  const items = [
    { ok: checks.longEnough, label: t('auth.passwordChecks.length', { count: checks.length }) },
    { ok: checks.varied, label: t('auth.passwordChecks.variety') },
    { ok: checks.noRepeats, label: t('auth.passwordChecks.repeats') },
  ];
  return (
    <div className="space-y-3 rounded-xl border border-line bg-canvas p-3.5" aria-live="polite">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className={`font-semibold ${STRENGTH_TEXT[score]}`}>
          {t(`auth.strength.${score}`)}
        </span>
        <span className="text-muted">{t(`auth.strengthTips.${score}`)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-line-strong" aria-hidden="true">
        <div
          className={`h-full rounded-full transition-[width,background-color] duration-500 ease-[var(--ease-out-expo)] ${STRENGTH_COLORS[score]}`}
          style={{ width: `${fill}%` }}
        />
      </div>
      <ul className="space-y-1.5 text-xs">
        {items.map((item) => (
          <li
            key={item.label}
            className={`flex items-center gap-2 transition-colors ${item.ok ? 'text-green' : 'text-muted'}`}
          >
            <span
              aria-hidden="true"
              className={`grid size-4 shrink-0 place-items-center rounded-full border text-[0.6rem] ${
                item.ok ? 'border-green bg-green/15' : 'border-line-strong'
              }`}
            >
              {item.ok ? '\u2713' : ''}
            </span>
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Select({
  label,
  hint,
  children,
  ...props
}: { label: string; hint?: ReactNode; children: ReactNode } & ComponentProps<'select'>) {
  return (
    <label className="block space-y-2">
      <span className="label">{label}</span>
      <select {...props} className={INPUT}>
        {children}
      </select>
      {hint && <Hint>{hint}</Hint>}
    </label>
  );
}

/** One plain sentence under a field saying what to put in it, for people new to business software. */
export function Hint({ children }: { children: ReactNode }) {
  return <span className="block text-xs leading-relaxed text-muted">{children}</span>;
}

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: { variant?: 'primary' | 'ghost' | 'danger' } & ComponentProps<'button'>) {
  const styles = {
    primary: 'bg-ink text-canvas hover:bg-azure',
    ghost: 'border border-line-strong text-ink hover:border-ink',
    danger: 'border border-red/40 text-red hover:bg-red/10',
  }[variant];
  return (
    <button
      type="button"
      {...props}
      className={`min-h-11 rounded-full px-5 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
    />
  );
}

// A small door that swings open on hover and stays open, glowing, while the request runs.
function Door({ open }: { open: boolean }) {
  return (
    <span aria-hidden="true" className="door relative" data-open={open}>
      <span className="door-light" />
      <span className="door-panel">
        <span className="door-knob" />
      </span>
    </span>
  );
}

/**
 * The main action of a form: full width, with an arrow that slides and a spinner while it works.
 * `door` swaps those for the door, for the buttons that take you in.
 */
export function SubmitButton({
  pending,
  door = false,
  children,
}: {
  pending: boolean;
  door?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="group relative flex w-full items-center justify-center gap-3 overflow-hidden rounded-full bg-ink py-4 font-medium text-canvas transition disabled:opacity-70"
    >
      <span className="absolute inset-0 origin-left scale-x-0 bg-azure transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:scale-x-100 rtl:origin-right" />
      <span className="relative">{children}</span>
      {door ? (
        <Door open={pending} />
      ) : pending ? (
        <span
          aria-hidden="true"
          className="relative size-4 animate-spin rounded-full border-2 border-canvas/30 border-t-canvas"
        />
      ) : (
        <span
          aria-hidden="true"
          className="relative transition-transform duration-500 group-hover:translate-x-1 rtl:rotate-180 rtl:group-hover:-translate-x-1"
        >
          &rarr;
        </span>
      )}
    </button>
  );
}

// 'notice' is for something the person should look at that is neither a failure nor done.
export function Alert({
  tone,
  children,
}: {
  tone: 'error' | 'success' | 'notice';
  children: ReactNode;
}) {
  const styles = {
    error: 'border-red/40 bg-red/10 text-red',
    success: 'border-green/40 bg-green/10 text-green',
    notice: 'border-yellow/40 bg-yellow/10 text-ink',
  }[tone];
  return (
    <p
      role={tone === 'error' ? 'alert' : 'status'}
      className={`rounded-xl border px-4 py-3 text-sm ${styles}`}
    >
      {children}
    </p>
  );
}
