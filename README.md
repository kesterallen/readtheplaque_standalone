# PlaqueWorld 🏛️

A Python 3-tier web application for crowdsourcing historical plaques — similar to readtheplaque.com.

## Architecture

```
┌─────────────────────────────────────┐
│  Tier 1 — Frontend                  │
│  HTML/CSS/JS · Leaflet maps         │
│  Jinja2 templates · Vanilla JS      │
└──────────────┬──────────────────────┘
               │ HTTP
┌──────────────▼──────────────────────┐
│  Tier 2 — Application Server        │
│  Python · Flask                     │
│  REST API · File uploads            │
└──────────────┬──────────────────────┘
               │ SQLite3 Python driver
┌──────────────▼──────────────────────┐
│  Tier 3 — Database                  │
│  SQLite (plaques.db)                │
│  Auto-created on first run          │
└─────────────────────────────────────┘
```

## Features

- 🗺️ **Clustered world map** — Leaflet.js + MarkerCluster, CARTO tile layer
- 🔍 **Live search** — search by title, location, or plaque text (with debounce)
- 📤 **Upload form** — drag-and-drop image, click-to-pin map, geolocation
- 📄 **Detail pages** — full plaque view with mini-map
- 🌐 **REST API** — `/api/plaques` (GeoJSON), `/api/search?q=`, `/api/plaques/<id>`
- 🌙 **Dark mode** — respects `prefers-color-scheme`
- 📱 **Responsive** — works on mobile

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run
python app.py
```

Then open http://localhost:5000

The SQLite database (`plaques.db`) and upload directory are created automatically on first run, seeded with 15 sample plaques from around the world.

## Production Deployment

For production, use Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Or with Nginx as reverse proxy:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    client_max_body_size 20M;

    location /static/ {
        alias /path/to/plaquesite/static/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/plaques` | All plaques as GeoJSON FeatureCollection |
| GET | `/api/search?q=<query>` | Search plaques (max 30 results) |
| GET | `/api/plaques/<id>` | Single plaque by ID |
| POST | `/submit` | Upload new plaque (multipart/form-data) |

### POST /submit fields

| Field | Type | Required |
|-------|------|----------|
| title | text | ✅ |
| image | file | ✅ |
| latitude | text | ✅ |
| longitude | text | ✅ |
| description | text | optional |
| location | text | optional |
| submitted_by | text | optional |

## Project Structure

```
plaquesite/
├── app.py                 # Flask app + routes + DB logic
├── plaques.db             # SQLite database (auto-created)
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html          # Base layout with nav/footer
│   ├── index.html         # Homepage with search + recent grid
│   ├── map.html           # Full-page clustered map
│   ├── submit.html        # Upload form with map picker
│   └── detail.html        # Individual plaque page
└── static/
    ├── css/
    │   └── style.css      # All styles with CSS variables + dark mode
    └── uploads/           # Uploaded images stored here
```
