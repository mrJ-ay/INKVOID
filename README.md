# INKVOID

INKVOID is a fiction writing site with a public story shelf, chapter reader, and author library. The frontend talks only to the INKVOID API. It does not use the FAKEPRESS API.

## Local development

1. Install Python 3.11 or newer.
2. In `backend`, install the packages from `requirements.txt`.
3. Copy `.env.example` to `.env`. Leave `DATABASE_URL` blank for a local SQLite database, or set it to a Supabase Postgres connection string.
4. The local development key is used automatically. Set a private `SECRET_KEY` before deploying; set `ENVIRONMENT=production` on the host.
5. Start the API from `backend` with `python -m uvicorn main:app --reload`.
6. Open `frontend/index.html` in a browser. The frontend uses `http://127.0.0.1:8000` by default.

The local database is created as `backend/inkvoid.db` and is ignored by Git. Existing FAKEPRESS database files are not used.

## Supabase setup

Create a separate Supabase project for INKVOID. Set these values in the backend environment (or the ignored local `.env` file):

- `DATABASE_URL`: the Postgres connection string copied from the project's **Connect** dialog. For a persistent backend, use a direct or session-pooler connection that matches the host's IP support.
- `SUPABASE_URL`: the new project's URL.
- `SUPABASE_SERVICE_ROLE_KEY`: a server-only key for image uploads. Never put it in frontend files or commit it.
- `SUPABASE_STORAGE_BUCKET`: public Storage bucket name; defaults to `inkvoid-images`.
- `SECRET_KEY`: a unique random signing key for INKVOID. Required in production.

Create the Storage bucket named in `SUPABASE_STORAGE_BUCKET` and make it public so uploaded story images can be read. SQLAlchemy creates the application tables when the API starts.

## GitHub

Before the first push, create or connect the INKVOID GitHub repository, then run `push.bat` from this folder. The ignore rules exclude `.env`, local databases, uploads, and Python cache files.
