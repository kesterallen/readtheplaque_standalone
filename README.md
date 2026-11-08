# Read The Plaque 🏛️

Read The Plaque is a Flask-based crowdsourced map of historical plaques and memorial markers from around the world. Visitors can browse approved plaques, view detail pages, submit new entries with photos and GPS coordinates, and explore nearby locations via a map interface.

## Architecture

```text
┌──────────────────────────────────────────────┐
│ Tier 1 — Frontend                            │
│ HTML + Jinja2 templates + vanilla JS         │
└──────────────────────┬───────────────────────┘
                       │ HTTP
┌──────────────────────▼───────────────────────┐
│ Tier 2 — Flask application                  │
│ app.py + routes/*.py                         │
│ request validation, uploads, admin flows     │
└──────────────────────┬───────────────────────┘
                       │ SQLite3
┌──────────────────────▼───────────────────────┐
│ Tier 3 — Database                            │
│ SQLite file at /data/plaques.db or repo dir │
│ tables: plaques, plaque_images, tags        │
└──────────────────────────────────────────────┘
```

## Features

- 🗺️ Interactive map with plaque markers and nearby-plaque lookup
- 🔎 Search by title and description
- 📤 Image upload and GPS position capture
- 📄 Plaque detail pages with share metadata and gallery support
- 🧑‍💼 Admin queue for reviewing submitted plaques
- 🏷️ Tagging and featured-plaque workflows
- 📱 Responsive layout with dark-mode styling

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000.

The app creates its database and upload directories automatically on first run. By default it stores data under `/data` when that directory exists, otherwise in the project root.

## Configuration

Core settings live in `config.py` and can be overridden with environment variables:

- `ADMIN_PASSWORD` — admin login password
- `SECRET_KEY` — Flask session secret
- `CARTO_API_KEY` — map tile configuration
- `SITE_URL` — canonical URL for share previews
- `HCAPTCHA_SITEKEY` / `HCAPTCHA_SECRET` — bot protection
- `RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW` — submission throttling

## Project structure

```text
.
├── app.py
├── config.py
├── database.py
├── models.py
├── requirements.txt
├── routes/
├── scripts/
├── static/
├── templates/
└── tests/
    ├── test_api_routes.py
    ├── test_database.py
    ├── test_models.py
    └── test_submissions.py
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/plaques` | All approved plaques as GeoJSON |
| GET | `/api/plaques/geo` | Lightweight GeoJSON for map pins |
| GET | `/api/search?q=` | Search approved plaques |
| GET | `/api/nearby/<lat>/<lng>` | Nearby plaques from a coordinate pair |
| GET | `/api/plaques/<id>` | Single approved plaque by ID |
| POST | `/submit` | Submit a plaque and images |

## Tests

The test suite uses Python's standard-library `unittest` framework and a temporary SQLite database. Run it with:

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs the same command on pushes and pull requests.

## Deployment

The project runs behind Gunicorn. For Fly.io, the app stores uploads and the database under `/data` so they persist across deployments.
