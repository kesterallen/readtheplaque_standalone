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
# Create and activate a virtual environment (optional)
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Then open http://localhost:5000.

The app creates its database and upload directories automatically on first run. By default, data is stored under `/data` when that directory exists; otherwise it is stored in the project directory.

## Configuration

Core settings live in `config.py` and can be overridden with environment variables:

- `ADMIN_PASSWORD` — admin login password
- `SECRET_KEY` — Flask session secret
- `CARTO_API_KEY` — map tile configuration
- `SITE_URL` — canonical site URL for share previews
- `HCAPTCHA_SITEKEY` / `HCAPTCHA_SECRET` — bot protection
- `RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW` — submission throttling

## Project structure

```text
.
├── app.py                  # Flask app entry point
├── config.py               # app configuration and constants
├── database.py             # SQLite connection and schema initialization
├── models.py               # image, tag, slug, and sanitization helpers
├── requirements.txt
├── routes/
│   ├── __init__.py         # blueprint registration
│   ├── admin.py            # admin login, moderation, image management
│   ├── api.py              # JSON endpoints for GeoJSON, search, and nearby
│   ├── public.py           # public pages, plaque details, and browsing
│   └── submissions.py      # submission validation and image persistence
├── scripts/                # maintenance, backup, and import tools
├── static/                 # CSS, images, and audio assets
├── templates/              # Jinja2 page and email/feed templates
├── tests/
│   ├── test_database.py
│   ├── test_models.py
│   └── test_submissions.py
└── README.md
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/plaques` | All approved plaques as GeoJSON |
| GET | `/api/plaques/geo` | Lightweight GeoJSON for map pins |
| GET | `/api/search?q=` | Search approved plaques |
| GET | `/api/nearby/<lat>/<lng>` | Nearby plaques from a coordinate pair |
| GET | `/api/plaques/<id>` | Single plaque by ID |
| POST | `/submit` | Submit a plaque and images |

### Submit form fields

| Field | Type | Required |
|-------|------|----------|
| title | text | yes |
| images | file(s) | yes |
| latitude | number | yes |
| longitude | number | yes |
| description | text | optional |
| submitted_by | text | optional |
| tags | text | optional |

## Local testing

The project includes a minimal regression test suite using Python's standard-library `unittest` runner:

```bash
python -m unittest discover -s tests -v
```

## Deployment

For production, run behind Gunicorn and a reverse proxy, for example:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

For Fly.io or similar hosts, the app stores uploads and the database under `/data` so they persist across deployments.
