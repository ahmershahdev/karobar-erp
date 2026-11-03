import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';

import { api } from '../../lib/api/client';
import { ApiError, unwrap } from '../../lib/api/errors';
import { loadRecaptcha } from '../../lib/recaptcha';
import { Checkbox, Honeypot } from './HumanFields';

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
  const config = useAuthConfig();
  const v3 = config.data?.recaptcha_v3_site_key ?? '';
  const v2 = config.data?.recaptcha_v2_site_key ?? '';
  const [honeypot, setHoneypot] = useState('');
  const [checkbox, setCheckbox] = useState(false);
  const [v2Token, setV2Token] = useState('');

  useEffect(() => {
    if (v3 || v2) void loadRecaptcha(v3).catch(() => undefined);
  }, [v3, v2]);

  const proof = useCallback(async (): Promise<HumanProof> => {
    if (checkbox && v2Token) return { website: honeypot, captcha_v2: v2Token };
    if (!v3) return { website: honeypot };
    try {
      const grecaptcha = await loadRecaptcha(v3);
      return { website: honeypot, captcha_v3: await grecaptcha.execute(v3, { action }) };
    } catch {
      // If Google can't be reached the server decides; without a token it asks for the box.
      return { website: honeypot };
    }
  }, [action, checkbox, honeypot, v2Token, v3]);

  const requireCheckbox = useCallback(() => {
    setV2Token('');
    setCheckbox(Boolean(v2));
  }, [v2]);

  return {
    proof,
    requireCheckbox,
    honeypot: <Honeypot value={honeypot} onChange={setHoneypot} />,
    checkbox: checkbox ? <Checkbox siteKey={v2} v3Key={v3} onToken={setV2Token} /> : null,
    waitingForCheckbox: checkbox && !v2Token,
  };
}
