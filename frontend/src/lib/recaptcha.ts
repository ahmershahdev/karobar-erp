// Loads Google's reCAPTCHA script once, on the forms that need it, never on other pages.
// The script tag is created by our own nonced code, so the CSP's 'strict-dynamic' admits it;
// the widget's iframes are allowed by frame-src in deploy/nginx/snippets/html.conf.

interface Grecaptcha {
  ready: (callback: () => void) => void;
  execute: (siteKey: string, options: { action: string }) => Promise<string>;
  render: (
    container: HTMLElement,
    options: {
      sitekey: string;
      theme?: 'dark' | 'light';
      callback: (token: string) => void;
      'expired-callback': () => void;
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

export function loadRecaptcha(v3SiteKey: string): Promise<Grecaptcha> {
  if (loading) return loading;
  loading = new Promise<Grecaptcha>((resolve, reject) => {
    const script = document.createElement('script');
    // render=<v3 key> loads v3; the same script can also render a v2 checkbox on demand.
    script.src = v3SiteKey ? `${SCRIPT}?render=${encodeURIComponent(v3SiteKey)}` : SCRIPT;
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
