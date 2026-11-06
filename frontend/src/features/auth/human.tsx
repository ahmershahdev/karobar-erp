import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '../../components/form';
import { api } from '../../lib/api/client';
import { ApiError, unwrap } from '../../lib/api/errors';
import { loadRecaptcha } from '../../lib/recaptcha';
import { Checkbox, Honeypot, RecaptchaBadge, RecaptchaNotice } from './HumanFields';

export function useAuthConfig() {
  return useQuery({
    queryKey: ['auth-config'],
    queryFn: () => unwrap(api.GET('/api/accounts/config/')),
    staleTime: Infinity,
  });
}

export function needsCheckbox(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    typeof error.body === 'object' &&
    error.body !== null &&
    (error.body as { code?: unknown }).code === 'captcha_v2_required'
  );
}

export interface HumanProof {
  website: string;
  captcha_v3?: string;
  captcha_v2?: string;
}

/**
 * The bot checks for one public form. `proof()` returns the fields to send with it: the
 * honeypot value, a fresh v3 token for `action`, or the v2 token once the checkbox has been
 * ticked. Call `requireCheckbox()` when the server answers captcha_v2_required.
 */
export function useHumanCheck(action: string) {
  const { t } = useTranslation();
  const config = useAuthConfig();
  const v3 = config.data?.recaptcha_v3_site_key ?? '';
  const v2 = config.data?.recaptcha_v2_site_key ?? '';
  const [honeypot, setHoneypot] = useState('');
  const [checkbox, setCheckbox] = useState(false);
  const [v2Token, setV2Token] = useState('');
  // Google accepts a v2 token once. After sending one the box has to be ticked again, and Google's
  // widget can't be reset from a ticked state here, so a new key mounts a fresh one.
  const [widget, setWidget] = useState(0);
  const [failed, setFailed] = useState(false);
  const onFailed = useCallback(() => setFailed(true), []);

  const badge = useRef<number | null>(null);
  const onBadge = useCallback((id: number) => {
    badge.current = id;
  }, []);

  useEffect(() => {
    if (v3 || v2) void loadRecaptcha().catch(() => undefined);
  }, [v3, v2]);

  const proof = useCallback(async (): Promise<HumanProof> => {
    if (checkbox && v2Token) {
      setV2Token('');
      setWidget((value) => value + 1);
      return { website: honeypot, captcha_v2: v2Token };
    }
    if (!v3 || badge.current === null) return { website: honeypot };
    try {
      const grecaptcha = await loadRecaptcha();
      return { website: honeypot, captcha_v3: await grecaptcha.execute(badge.current, { action }) };
    } catch {
      // If Google can't be reached the server decides; without a token it asks for the box.
      return { website: honeypot };
    }
  }, [action, checkbox, honeypot, v2Token, v3]);

  const requireCheckbox = useCallback(() => {
    setV2Token('');
    setFailed(false);
    setWidget((value) => value + 1);
    setCheckbox(true);
  }, []);

  // Asked for the box but it can't appear: its key is missing or Google can't be reached. Say so
  // and leave the button working, or the form would sit there disabled with no explanation.
  const noBox = checkbox && (failed || !v2);

  return {
    proof,
    requireCheckbox,
    honeypot: <Honeypot value={honeypot} onChange={setHoneypot} />,
    checkbox: noBox ? (
      <Alert tone="error">{t('signIn.unavailable')}</Alert>
    ) : checkbox ? (
      <Checkbox key={widget} siteKey={v2} onToken={setV2Token} onFailed={onFailed} />
    ) : null,
    notice: v3 ? (
      <RecaptchaBadge siteKey={v3} onWidget={onBadge} />
    ) : v2 ? (
      <RecaptchaNotice />
    ) : null,
    waitingForCheckbox: checkbox && !noBox && !v2Token,
  };
}
