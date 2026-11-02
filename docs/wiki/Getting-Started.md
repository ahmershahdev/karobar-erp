# Getting started

You need Docker, Python 3.12 and Node 22.

1. Clone the repository and start the database and cache:

   ```sh
   git clone https://github.com/ahmershahdev/karobar-erp.git
   cd karobar-erp
   docker compose up -d mysql redis
   ```

2. Start the API:

   ```sh
   cd backend
   python -m venv .venv
   .venv/bin/pip install -r requirements/dev.txt
   cp .env.example .env        # set DJANGO_SECRET_KEY to a long random string
   .venv/bin/python manage.py migrate
   .venv/bin/python manage.py createsuperuser
   .venv/bin/python manage.py runserver
   ```

3. Start the web app in another terminal:

   ```sh
   cd frontend
   npm ci
   npm run dev
   ```

4. Open <http://localhost:5173>. Sign in at `/app` with the user you created.

On Windows, use `.venv\Scripts\` in place of `.venv/bin/`.
