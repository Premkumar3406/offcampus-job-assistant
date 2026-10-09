
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
import sqlite3

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

DATABASE = "jobs.db"
ARBEITNOW_API = "https://www.arbeitnow.com/api/job-board-api"


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                location TEXT DEFAULT '',
                posted_at INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Saved',
                saved_at TEXT NOT NULL
            )
        """)


def get_fresh_jobs():
    """Fetch jobs and retain listings posted in the last 24 hours."""
    response = requests.get(
        ARBEITNOW_API,
        params={"page": 1},
        timeout=20
    )
    response.raise_for_status()
    payload = response.json()

    jobs = payload.get("data", [])
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    fresh_jobs = []

    for job in jobs:
        try:
            timestamp = int(job.get("created_at", 0))
            posted = datetime.fromtimestamp(
                timestamp, tz=timezone.utc
            )
        except (ValueError, TypeError, OSError):
            continue

        if not timestamp or not (cutoff <= posted <= now):
            continue

        fresh_jobs.append({
            "title": job.get("title", "Untitled role"),
            "company": job.get("company_name", "Unknown company"),
            "location": job.get("location", "Not specified"),
            "url": job.get("url", ""),
            "posted_at": timestamp,
            "posted_text": posted.strftime("%d %b %Y, %H:%M UTC"),
            "remote": bool(job.get("remote", False)),
            "tags": job.get("tags", []),
            "source": "Arbeitnow"
        })

    return fresh_jobs


def build_portal_links(role, location):
    """Create searches on portals; do not scrape their pages."""
    role = role.strip() or "software developer fresher"
    location = location.strip() or "India"

    linkedin_params = {
        "keywords": role,
        "location": location,
        "f_TPR": "r86400"
    }

    naukri_params = {
        "k": role,
        "l": location,
        "experience": "0"
    }

    return {
        "linkedin": (
            "https://www.linkedin.com/jobs/search/?"
            + urlencode(linkedin_params)
        ),
        "naukri": (
            "https://www.naukri.com/jobs-in-india?"
            + urlencode(naukri_params)
        )
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/jobs")
def search_jobs():
    role = request.args.get(
        "q", "software developer fresher"
    ).strip()

    location = request.args.get("location", "India").strip()

    try:
        jobs = get_fresh_jobs()
    except requests.RequestException:
        return jsonify({
            "jobs": [],
            "portals": build_portal_links(role, location),
            "error": (
                "The public job feed is temporarily unavailable. "
                "You can still use the portal search links."
            )
        }), 200
    except (ValueError, TypeError):
        return jsonify({
            "jobs": [],
            "portals": build_portal_links(role, location),
            "error": "The job feed returned an unexpected response."
        }), 200

    # Filter by role, tags, company, description, and location.
    role_terms = [
        word.lower()
        for word in role.split()
        if len(word) > 1
    ]
    location_terms = [
        word.lower()
        for word in location.split()
        if len(word) > 1 and word.lower() != "india"
    ]

    filtered = []

    for job in jobs:
        searchable = " ".join([
            job["title"],
            job["company"],
            job["location"],
            " ".join(job["tags"])
        ]).lower()

        if role_terms and not any(
            term in searchable for term in role_terms
        ):
            continue

        if location_terms and not any(
            term in job["location"].lower()
            for term in location_terms
        ):
            continue

        if not job["url"].startswith("https://"):
            continue

        filtered.append(job)

    filtered.sort(
        key=lambda job: job["posted_at"],
        reverse=True
    )

    return jsonify({
        "jobs": filtered,
        "count": len(filtered),
        "window_hours": 24,
        "portals": build_portal_links(role, location),
        "message": (
            "The feed is Europe-focused. Use portal searches "
            "for broader India-based fresher opportunities."
        )
    })


@app.route("/api/applications", methods=["GET"])
def list_applications():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT * FROM applications ORDER BY id DESC"
        ).fetchall()

    return jsonify([dict(row) for row in rows])


@app.route("/api/applications", methods=["POST"])
def save_application():
    data = request.get_json(silent=True) or {}

    title = str(data.get("title", "")).strip()
    company = str(data.get("company", "")).strip()
    url = str(data.get("url", "")).strip()
    location = str(data.get("location", "")).strip()
    posted_at = int(data.get("posted_at", 0) or 0)

    if not title or not company or not url:
        return jsonify({
            "error": "Title, company, and URL are required."
        }), 400

    if not url.startswith("https://"):
        return jsonify({"error": "Only HTTPS links are accepted."}), 400

    saved_at = datetime.now(timezone.utc).isoformat()

    try:
        with get_db() as connection:
            connection.execute("""
                INSERT INTO applications
                (title, company, url, location, posted_at,
                 status, saved_at)
                VALUES (?, ?, ?, ?, ?, 'Saved', ?)
            """, (
                title, company, url, location,
                posted_at, saved_at
            ))
    except sqlite3.IntegrityError:
        return jsonify({
            "error": "This job is already saved."
        }), 409

    return jsonify({"message": "Job saved successfully."}), 201


@app.route("/api/applications/<int:application_id>", methods=["PATCH"])
def update_application(application_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")

    allowed_statuses = {
        "Saved",
        "Ready to Apply",
        "Applied",
        "Interview",
        "Rejected",
        "Closed"
    }

    if status not in allowed_statuses:
        return jsonify({"error": "Invalid application status."}), 400

    with get_db() as connection:
        result = connection.execute(
            "UPDATE applications SET status = ? WHERE id = ?",
            (status, application_id)
        )

    if result.rowcount == 0:
        return jsonify({"error": "Application not found."}), 404

    return jsonify({"message": "Status updated."})



# Initialize the database for both local and cloud deployments.
initialize_database()

if __name__ == "__main__":
    app.run(debug=True)

