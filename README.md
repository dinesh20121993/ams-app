# Attendance Management System (AMS)

A Python Flask app for managing student attendance via QR codes.

## Project Structure

```
ams-app/
├── app.py            # Flask application entry point
├── database.py       # SQLite schema & connection helpers
├── requirements.txt  # Python dependencies
├── render.yaml       # Render.com deployment config
├── templates/
│   └── index.html    # Home page
└── static/
    └── style.css     # Global stylesheet
```

## Local Setup

### 1. Create and activate a virtual environment

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialise the database

```bash
python database.py
```

This creates `ams.db` with three tables: `students`, `sessions`, and `attendance`.

### 4. Run the development server

```bash
python app.py
```

Open <http://127.0.0.1:5000> in your browser.

## Deployment (Render)

Push to GitHub, connect the repo on [render.com](https://render.com), and the
`render.yaml` file handles the rest. The start command is:

```
gunicorn app:app
```
