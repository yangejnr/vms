# Visitor Management System (VMS)

A Flask-based visitor management prototype for structured visitor registration, check-in/check-out tracking and QR-coded visit records.

## Purpose

The project explores how a reception or security team can replace paper visitor registers with a searchable digital workflow. It models visitors separately from individual visits so returning visitors can be identified while each new visit receives its own reference and status trail.

## Current Prototype

The application includes:

- visitor registration and lookup
- name, phone, email and address capture
- organization, ID type, ID number and gender capture
- optional visitor photograph capture
- optimized visitor portrait storage with a white background
- visit-purpose and group-size recording
- host/officer and destination recording
- generated visit reference numbers
- QR-code generation for visits
- sign-in and sign-out state tracking
- same-day visit listing
- SQLite persistence for local development
- Flask templates and static frontend assets

## Backend Records

Visitor and visit records are stored in the local SQLite database under `instance/`.
Runtime visitor photos are stored under `instance/photos/` and are intentionally
excluded from source control.

Authenticated desk officers can use these JSON endpoints:

- `GET /api/visitors` lists stored visitor records
- `GET /api/visitors?q=term` searches visitors by name, phone, email, organization or ID number
- `GET /api/visitor/<id>` returns one visitor with visit history
- `GET /api/visitor/<id>/photo` returns the stored portrait
- `GET /api/visits` lists recent visit records
- `GET /api/visits?status=in` lists active visits

## Architecture

```text
Browser / Reception UI
         │
         ▼
      Flask App
         │
    ┌────┴─────┐
    ▼          ▼
SQLAlchemy   QR Generator
    │
    ▼
SQLite (development)
```

The current prototype is contained primarily in `ncs_vms/`.

## Privacy and Data Handling

Visitor information and captured photographs are runtime data and **must not be committed to source control**. The repository now excludes local databases, visitor photographs, environment files and virtual environments through `.gitignore`.

Any production deployment handling personal information should additionally implement authentication, role-based access, encryption, retention policies, audit logging, secure backups and appropriate data-protection controls.

## Technology

- Python
- Flask
- Flask-SQLAlchemy
- SQLite
- HTML/CSS templates
- QR code generation

## Local Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python ncs_vms/app.py
```

The app runs on <http://localhost:5100> by default. Override the port with `PORT`.

Desk officers sign in from the landing page login modal before visitor records can be
captured. Use a Service No and the configured Password. Set `DESK_OFFICER_CODE`
to change the default prototype password, which is `NCS-1234`.

## Ngrok Tunnel

Ngrok support is optional and disabled by default. To expose the local Flask app:

```bash
source venv/bin/activate
export NCS_ENABLE_NGROK=1
export NGROK_AUTHTOKEN=your_ngrok_token
python ncs_vms/app.py
```

The public ngrok URL is printed in the terminal when the tunnel starts.

Optional settings:

- `NGROK_DOMAIN` for a reserved/static ngrok domain
- `NGROK_REGION` for an ngrok region
- `PORT` for the local Flask port, defaulting to `5100`

## Status

**Prototype / proof of concept.** The current code demonstrates the visitor-management workflow; it is not presented as a production-hardened security system.

## Author

**Yange Henry Terzugwe**  
Software Developer • AI & Robotics Practitioner
