# Security model

- Each business's data is filtered by the server on every query, and a request for another
  business's record answers "not found". A test checks every endpoint this way.
- Sign-in uses secure, HttpOnly session cookies with CSRF protection. Passwords are hashed with
  Argon2id and must be at least 12 characters.
- Every endpoint is rate limited, with strict limits on sign-in.
- The web app runs under a strict Content Security Policy with a fresh nonce on every page load.
- Stock levels, document numbers and balances are changed under database row locks, so two
  cashiers can't sell the same last item.
- Every change to business data goes in an audit log that can't be edited.
- Bill pictures (logos, signatures) are checked and re-saved as a clean copy; nothing is kept as
  uploaded.
- Chat messages are signed one after another, so a changed or removed message is caught.
- On a public demo server, the shared demo account can't change itself, email anyone, or reach
  outside the demo businesses, and the demo is put back every night.

Full details: [docs/security.md](https://github.com/ahmershahdev/karobar-erp/blob/main/docs/security.md).
Report problems privately as described in
[SECURITY.md](https://github.com/ahmershahdev/karobar-erp/blob/main/SECURITY.md).
