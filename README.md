# Brody.io

Brody.io is a paper-trading simulator with a plain HTML/CSS/JS frontend and a small Python backend for shared prices, trades, auth, and admin actions.

## Structure

- `index.html` - single-page frontend shell
- `styles.css` - dark terminal UI
- `app.js` - client app logic and polling
- `api/*.py` - Vercel Python serverless functions
- `backend/server.py` - local development backend that mirrors the same logic

## Local Run

Frontend:

```bash
python3 -m http.server 8080
```

Local backend:

```bash
python3 backend/server.py
```

Then open:

- Frontend: `http://localhost:8080/Brody/`
- Backend: `http://localhost:8787`

## Default Admin

- Username: `jagan`
- Password: `vusd14509`

## Vercel

Add these environment variables in your Vercel project settings:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

The frontend will call `/api/*` automatically in production.

## Notes

- The frontend is plain HTML/CSS/JS so it can be deployed like a normal static site.
- Real synchronization comes from the backend layer, with Supabase as the shared source of truth.
