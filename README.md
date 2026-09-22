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

## Documentation

Full documentation lives in [`docs/`](docs/):

| Document | Audience |
| --- | --- |
| [User Guide](docs/USER_GUIDE.md) | Reception officers and administrators — step-by-step guide with screenshots, suitable for training |
| [Management Presentation](docs/MANAGEMENT_PRESENTATION.md) | Management briefing slides |
| [Technical Documentation](docs/TECHNICAL_DOCUMENTATION.md) | Developers — architecture, data model, API reference and extension guide |
| [Business Requirements Specification](docs/BUSINESS_REQUIREMENTS.md) | Formal requirements, acceptance criteria and risks |

## Users, Roles and Modules

Authentication is database-backed. Every user belongs to a role, and each role
defines the **landing module** the user is redirected to after login.

| Role | Landing module | Access |
| --- | --- | --- |
| Admin | `/admin/dashboard` | Dashboard, users, roles, locations, reports, plus the reception module |
| Officer | `/checkin` | Reception check-in, today's visits and visit history only |

Roles are stored in the `role` table and are manageable from the admin module,
so additional roles can be created without code changes. The built-in `Admin`
and `Officer` roles cannot be deleted.

User passwords are stored as salted hashes (Werkzeug `scrypt`), never in plain
text.

### Admin Module

- **Dashboard** — visitor, visit, user and location counts, plus recent visits
- **Users** — create, edit, enable/disable and delete users; assign roles
- **Roles** — create and edit roles, including their landing module
- **Locations** — manage departments, commands and units
- **Reports** — filterable visit reports with CSV export

Admins cannot disable, delete or demote their own account, preventing lockout.

### Default Admin

On first run, if no users exist, an admin account is created:

- Service No: `DEFAULT_ADMIN_SERVICE_NO` (default `ADMIN`)
- Password: `DEFAULT_ADMIN_PASSWORD` (default `NCS-1234`)

Change these before any real deployment.

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
- `GET /api/visits/history` filtered visit history (search, status, purpose, month, year, date range)

Admin-only endpoints live under `/api/admin/` and return `403` for non-admin users.

## Data Validation

- Visitor names are stored uppercase, with collapsed whitespace
- Phone numbers accept digits only and must be exactly 11 digits
- Passwords must be at least 6 characters
- A visitor cannot hold two active visits on the same day

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

Staff sign in from the landing page login modal using a Service No and password.
Admins are taken to the admin dashboard; officers are taken to the reception
check-in screen. See **Users, Roles and Modules** above for the default admin
credentials and role behaviour.

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

### If ngrok stops working

The usual cause is a **leftover ngrok agent** from a previous run. A reserved
domain can only be claimed by one agent at a time, so a stale process makes the
next start fail with:

```text
ERR_NGROK_334: The endpoint 'https://…ngrok-free.dev' is already online.
```

Fix it by clearing the stale agent:

```bash
pkill -f ngrok
```

Then start the app again. The application now cleans up after itself on exit
(including Ctrl+C and `kill`), and prints a clear message instead of a raw error
if the endpoint is still held.

## Status

**Prototype / proof of concept.** The current code demonstrates the visitor-management workflow; it is not presented as a production-hardened security system.

## Author

**Yange Henry Terzugwe**  
Software Developer • AI & Robotics Practitioner
