# Visitor Management System (VMS)

A Flask-based visitor management prototype for structured visitor registration, check-in/check-out tracking and QR-coded visit records.

## Purpose

The project explores how a reception or security team can replace paper visitor registers with a searchable digital workflow. It models visitors separately from individual visits so returning visitors can be identified while each new visit receives its own reference and status trail.

## Current Prototype

The application includes:

- visitor registration and lookup
- name, phone, email and address capture
- optional visitor photograph capture
- visit-purpose and group-size recording
- generated visit reference numbers
- QR-code generation for visits
- sign-in and sign-out state tracking
- same-day visit listing
- SQLite persistence for local development
- Flask templates and static frontend assets

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

## Status

**Prototype / proof of concept.** The current code demonstrates the visitor-management workflow; it is not presented as a production-hardened security system.

## Author

**Yange Henry Terzugwe**  
Software Developer • AI & Robotics Practitioner
