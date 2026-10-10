# INKVOID

INKVOID is an independent fiction writing site with a public story shelf, chapter reader, and author library. It uses its own FastAPI backend and database; it does not use the FAKEPRESS API or database.

## Local development

1. Install Python 3.11 or newer.
2. In `backend`, install the packages from `requirements.txt`.
3. Copy `.env.example` to `.env`. Leave `DATABASE_URL` blank to use local SQLite, or set it to the PostgreSQL connection string for the INKVOID Neon project.
4. Set a private `SECRET_KEY` before deployment. Set `ENVIRONMENT=production` on the host and `CORS_ORIGINS` to the deployed frontend URL.
5. Start the API from `backend` with `python -m uvicorn main:app --reload`.
6. Open `frontend/index.html` in a browser. It uses `http://127.0.0.1:8000` by default; the deployed API URL is injected into `frontend/api-config.js` at build time.

The local database is created as `backend/inkvoid.db` and is ignored by Git. Existing FAKEPRESS database files are not used. SQLAlchemy creates the application tables when the API starts.

## Neon

Set `DATABASE_URL` to the connection string for the INKVOID Neon project. Keep the connection string, `SECRET_KEY`, and Neon Object Storage credentials in the backend host's secret environment variables. Never commit them or place them in frontend files. The private `inkvoid-images` bucket stores story banners; the API returns short-lived signed image URLs so the bucket can remain private. Uploads accept JPG, PNG, WEBP, and GIF files up to 5 MB.

## GitHub

The repository is public. The ignore rules exclude `.env`, local databases, uploads, and Python cache files. Run `push.bat` from this folder to publish changes.

## Publication

New stories are private drafts by default. Authors can publish or unpublish them from the writing editor. Public endpoints and comments only expose published stories; owners can see all their own drafts in the library.
