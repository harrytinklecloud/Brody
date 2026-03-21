# Brody.io

Brody.io is a paper-trading simulator with a plain HTML/CSS/JS frontend and a small Python backend for shared prices, trades, auth, and admin actions.

## Structure

- `index.html` - single-page frontend shell
- `styles.css` - dark terminal UI
- `app.js` - client app logic and polling
- `backend/server.py` - Flask + SQLite backend

## Local Run

Frontend:

```bash
python3 -m http.server 8080
```

Backend:

```bash
python3 backend/server.py
```

Then open:

- Frontend: `http://localhost:8080/Brody/`
- Backend: `http://localhost:8787`

## Default Admin

- Username: `jagan`
- Password: `vusd14509`

## Notes

- The frontend is plain HTML/CSS/JS so it can be deployed like a normal static site.
- Real synchronization comes from the backend, which stores prices and portfolios server-side in SQLite.
