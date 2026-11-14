# Self hosting

Karobar runs as seven containers: `web` (nginx with the built app), `api` (Django under gunicorn),
`worker` (Celery, for emails and nightly jobs), `chat` (a second Celery worker that only writes
chat answers, so a long nightly job never keeps someone waiting), `beat` (the Celery schedule for
nightly jobs), `mysql` and `redis`. The files are in `deploy/`.

1. Copy `deploy/.env.example` to `deploy/.env` and fill in every value. Generate secrets with a
   password manager or `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
   Choose an unguessable `DJANGO_ADMIN_URL` such as `manage-7f3c9a/`. Email goes through Resend
   (`RESEND_API_KEY`). The chat needs `GROQ_API_KEY` and a stable `CHAT_SIGNING_KEY`; leave both
   empty to keep it off. Leave `DEMO_MODE` off unless the server is a public demo.
2. Build and start:

   ```sh
   docker compose -f deploy/compose.prod.yaml up -d --build
   docker compose -f deploy/compose.prod.yaml exec api python manage.py migrate
   docker compose -f deploy/compose.prod.yaml exec api python manage.py createsuperuser
   ```

3. Put a TLS proxy (Caddy, Traefik or your host's nginx) in front of `127.0.0.1:8080`. If it is
   a separate nginx, add `set_real_ip_from` for it so rate limits see real client addresses.

Real PDFs (bills, payslips) are made by WeasyPrint inside the `api` image, which has the fonts for
Urdu and Arabic.

Back up the `mysql-data` volume daily with `mysqldump --single-transaction`, keep copies off the
server, and test a restore now and then.
