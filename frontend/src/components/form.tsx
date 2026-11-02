import type { ComponentProps, ReactNode } from 'react';

const INPUT =
  'w-full rounded-xl border border-line bg-black/50 px-4 py-3 text-base outline-none transition-colors placeholder:text-muted/60 focus:border-gold disabled:opacity-60';

export function Field({ label, ...props }: { label: string } & ComponentProps<'input'>) {
  return (
    <label className="block space-y-2">
      <span className="label">{label}</span>
      <input {...props} className={INPUT} />
    </label>
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
    primary: 'text-black [background:var(--gradient-molten)] hover:brightness-110',
    ghost: 'border border-line-strong text-ink hover:border-gold hover:text-gold',
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
