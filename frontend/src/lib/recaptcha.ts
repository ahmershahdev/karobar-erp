// Loads Google's reCAPTCHA script once, on the forms that need it, never on other pages.
// The script tag is created by our own nonced code, so the CSP's 'strict-dynamic' admits it;
// the widget's iframes are allowed by frame-src in deploy/nginx/snippets/html.conf.

interface Grecaptcha {
  ready: (callback: () => void) => void;
  execute: (widget: number, options: { action: string }) => Promise<string>;
  render: (
    container: HTMLElement,
    options: {
      sitekey: string;
      theme?: 'dark' | 'light';
      size?: 'invisible';
      badge?: 'inline';
      callback?: (token: string) => void;
      'expired-callback'?: () => void;
    },
  ) => number;
  reset: (widget?: number) => void;
}

declare global {
  interface Window {
    grecaptcha?: Grecaptcha;
  }
}

const SCRIPT = 'https://www.google.com/recaptcha/api.js';
let loading: Promise<Grecaptcha> | null = null;

export function loadRecaptcha(): Promise<Grecaptcha> {
  if (loading) return loading;
  loading = new Promise<Grecaptcha>((resolve, reject) => {
    const script = document.createElement('script');
    // Explicit rendering, because Google's automatic v3 badge can only float over a screen corner.
    // We render it inside the form instead, and the same script draws the v2 checkbox on demand.
    script.src = `${SCRIPT}?render=explicit`;
    script.async = true;
    script.onload = () => {
      const api = window.grecaptcha;
      if (api) api.ready(() => resolve(api));
      else reject(new Error('reCAPTCHA did not load'));
    };
    script.onerror = () => {
      loading = null;
      reject(new Error('reCAPTCHA did not load'));
    };
    document.head.appendChild(script);
  });
  return loading;
}
