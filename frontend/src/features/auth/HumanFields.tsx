import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { loadRecaptcha } from '../../lib/recaptcha';

// A field people never see or reach with the keyboard; form-filling bots tend to fill it in.
export function Honeypot({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div aria-hidden="true" className="sr-only">
      <label>
        Website
        <input
          type="text"
          name="website"
          tabIndex={-1}
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    </div>
  );
}

export function Checkbox({
  siteKey,
  v3Key,
  onToken,
  onFailed,
}: {
  siteKey: string;
  v3Key: string;
  onToken: (token: string) => void;
  onFailed: () => void;
}) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = box.current;
    if (!container) return;
    // StrictMode runs this twice before the script arrives; only the live run may render.
    let active = true;
    const render = async () => {
      const grecaptcha = await loadRecaptcha(v3Key);
      if (!active || container.childElementCount) return;
      grecaptcha.render(container, {
        sitekey: siteKey,
        theme: 'light',
        callback: onToken,
        'expired-callback': () => onToken(''),
      });
    };
    render().catch(() => {
      if (active) onFailed();
    });
    return () => {
      active = false;
    };
  }, [siteKey, v3Key, onToken, onFailed]);
  return (
    <div className="space-y-3 rounded-2xl border border-line bg-surface p-4">
      <p className="text-sm text-ink">{t('auth.robotCheck')}</p>
      {/* Google's checkbox is a fixed 304 by 78 pixel iframe; the box keeps that space so the
          form doesn't jump when it loads, and scales it down on very narrow phones. */}
      <div className="h-[78px] origin-left max-[360px]:scale-90 rtl:origin-right" ref={box} />
    </div>
  );
}

/**
 * Google allows hiding the floating reCAPTCHA badge as long as the form says it is protected and
 * links to Google's privacy policy and terms; the badge otherwise sits over the page corner.
 */
export function RecaptchaNotice() {
  const { t } = useTranslation();
  const link = 'text-muted underline underline-offset-2 hover:text-ink';
  return (
    <p className="text-center text-xs text-muted">
      {t('auth.recaptchaNotice.protected')}{' '}
      <a
        className={link}
        href="https://policies.google.com/privacy"
        target="_blank"
        rel="noreferrer"
      >
        {t('auth.recaptchaNotice.privacy')}
      </a>{' '}
      {t('auth.recaptchaNotice.and')}{' '}
      <a className={link} href="https://policies.google.com/terms" target="_blank" rel="noreferrer">
        {t('auth.recaptchaNotice.terms')}
      </a>{' '}
      {t('auth.recaptchaNotice.apply')}
    </p>
  );
}
