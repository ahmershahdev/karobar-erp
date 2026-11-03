import { useId, useState, type ComponentProps, type KeyboardEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { passwordScore } from '../lib/password';

const INPUT =
  'w-full rounded-xl border border-line bg-black/50 px-4 py-3.5 text-base outline-none transition-[border-color,box-shadow] placeholder:text-muted/50 focus:border-ember focus:shadow-[0_0_0_4px_color-mix(in_srgb,_var(--color-ember)_12%,_transparent)] disabled:opacity-60';

export function Field({
  label,
  hint,
  ...props
}: { label: string; hint?: ReactNode } & ComponentProps<'input'>) {
  return (
    <label className="block space-y-2">
      <span className="label">{label}</span>
      <input {...props} className={INPUT} />
      {hint}
    </label>
  );
}

// Red to amber to green, so the four steps read as a scale and not four shades of the accent.
const STRENGTH_COLORS = ['bg-red', 'bg-red', 'bg-yellow', 'bg-green', 'bg-green'];
const STRENGTH_TEXT = ['text-red', 'text-red', 'text-yellow', 'text-green', 'text-green'];

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
        <button
          type="button"
          aria-label={visible ? t('auth.hide') : t('auth.show')}
          aria-pressed={visible}
          aria-controls={id}
          onClick={() => setVisible(!visible)}
          className="absolute inset-y-0 end-0 flex w-12 items-center justify-center text-muted transition-colors hover:text-ember"
        >
          <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
            <path
              d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            />
            <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.5" />
            {visible && <path d="M4 20 20 4" stroke="currentColor" strokeWidth="1.5" />}
          </svg>
        </button>
      </div>
      {caps && (
        <p className="flex items-center gap-2 text-xs text-yellow" role="status">
          <span aria-hidden="true">&#8679;</span> {t('auth.caps')}
        </p>
      )}
      {showStrength && value && (
        <div className="space-y-1.5" aria-live="polite">
          <div className="flex gap-1" aria-hidden="true">
            {[1, 2, 3, 4].map((step) => (
              <span
                key={step}
                className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
                  score >= step ? STRENGTH_COLORS[score] : 'bg-line-strong'
                }`}
              />
            ))}
          </div>
          <p className={`text-xs font-medium ${STRENGTH_TEXT[score]}`}>
            {t(`auth.strength.${score}`)}
          </p>
        </div>
      )}
    </div>
  );
}

export function Select({
  label,
  children,
  ...props
}: { label: string; children: ReactNode } & ComponentProps<'select'>) {
  return (
    <label className="block space-y-2">
      <span className="label">{label}</span>
      <select {...props} className={INPUT}>
        {children}
      </select>
    </label>
  );
}

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: { variant?: 'primary' | 'ghost' | 'danger' } & ComponentProps<'button'>) {
  const styles = {
    primary: 'text-black [background:var(--gradient-molten)] hover:[background:var(--color-coral)]',
    ghost: 'border border-line-strong text-ink hover:border-ember hover:text-ember',
    danger: 'border border-coral/40 text-coral hover:bg-coral/10',
  }[variant];
  return (
    <button
      type="button"
      {...props}
      className={`rounded-full px-5 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
    />
  );
}

/** The main action of a form: full width, an arrow that slides, a spinner while it works. */
export function SubmitButton({ pending, children }: { pending: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="group relative flex w-full items-center justify-center gap-3 overflow-hidden rounded-full py-4 font-medium text-black transition disabled:opacity-70"
      style={{ background: 'var(--gradient-molten)' }}
    >
      <span className="absolute inset-0 origin-left scale-x-0 bg-coral transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:scale-x-100 rtl:origin-right" />
      <span className="relative">{children}</span>
      {pending ? (
        <span
          aria-hidden="true"
          className="relative size-4 animate-spin rounded-full border-2 border-black/30 border-t-black"
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

export function Alert({ tone, children }: { tone: 'error' | 'success'; children: ReactNode }) {
  const styles =
    tone === 'error'
      ? 'border-coral/40 bg-coral/10 text-coral'
      : 'border-mint/40 bg-mint/10 text-mint';
  return (
    <p
      role={tone === 'error' ? 'alert' : 'status'}
      className={`rounded-xl border px-4 py-3 text-sm ${styles}`}
    >
      {children}
    </p>
  );
}
