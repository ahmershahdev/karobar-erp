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
    <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
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
}: {
  siteKey: string;
  v3Key: string;
  onToken: (token: string) => void;
}) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = box.current;
    if (!container || container.childElementCount) return;
    void loadRecaptcha(v3Key).then((grecaptcha) => {
      grecaptcha.render(container, {
        sitekey: siteKey,
        theme: 'dark',
        callback: onToken,
        'expired-callback': () => onToken(''),
      });
    });
  }, [siteKey, v3Key, onToken]);
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted">{t('auth.robotCheck')}</p>
      <div ref={box} />
    </div>
  );
}
