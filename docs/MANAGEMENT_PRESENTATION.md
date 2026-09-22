---
marp: true
theme: default
paginate: true
size: 16:9
header: 'NCS Visitor Management System'
footer: 'Management Briefing · September 2026'
style: |
  :root {
    --ncs-green: #0f6f3f;
    --ncs-deep: #123629;
    --ncs-gold: #d9a441;
  }
  section {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #ffffff;
    color: #16241d;
    padding: 48px 56px;
  }
  section.lead {
    background: linear-gradient(135deg, #123629 0%, #0f6f3f 100%);
    color: #ffffff;
  }
  section.lead h1, section.lead h2 { color: #ffffff; }
  h1 { color: var(--ncs-deep); font-weight: 800; }
  h2 { color: var(--ncs-deep); font-weight: 800; border-bottom: 3px solid var(--ncs-gold); padding-bottom: 8px; }
  h3 { color: var(--ncs-green); }
  strong { color: var(--ncs-deep); }
  table { font-size: 0.82em; }
  th { background: var(--ncs-green); color: #fff; }
  blockquote { border-left: 4px solid var(--ncs-gold); background: #f4f7f5; padding: 12px 18px; font-style: normal; }
  .tag { display: inline-block; background: var(--ncs-gold); color: #16241d; font-weight: 700; padding: 2px 12px; border-radius: 999px; font-size: 0.75em; }
  img { border: 1px solid #dce5df; border-radius: 6px; }
  section::after { color: #5e6f66; }
---

<!-- _class: lead -->
<!-- _paginate: false -->

# NCS Visitor Management System

### Modernising front-desk visitor control

**Management Briefing**
September 2026

---

## The problem we set out to solve

Our reception desks ran on **paper visitor registers**.

| The issue | The cost |
| --- | --- |
| Handwritten entries | Illegible and inconsistent records |
| No central search | Returning visitors re-register every time |
| Manual numbering | Lost references and no audit trail |
| No live view | No way to know who is on site *right now* |
| Manual reporting | Hours spent counting entries by hand |

> **Bottom line:** the organisation could not answer basic security questions about who entered its facilities, when, and why.

---

## What the system delivers

A **digital visitor control platform** covering the full reception workflow.

<!-- _class: lead -->

- **Register** visitors once, reuse them forever
- **Identify** returning visitors by phone, email or face
- **Issue** a unique reference and QR-coded slip per visit
- **Track** sign-in and sign-out in real time
- **Report** on any date range in seconds

---

## How it works — the three-step workflow

![w:1000](images/08-visits-today.png)

**1. Identify** → search or register the visitor
**2. Record** → capture purpose, host, documents, group size
**3. Close** → sign the visitor out when they leave

---

## The reception screen

![w:1050](images/12-officer-checkin.png)

One screen guides the officer. No training manual needed at the desk.

---

## Key capability: instant visitor lookup

![w:1000](images/10-checkin.png)

- Search by **phone or email** — returning visitors found in one second
- **Optional face check** speeds up regular visitors
- Duplicate records are **prevented automatically** by phone number
- Visitor photographs are captured on a clean white background for identification

---

## Key capability: complete visit history

![w:1050](images/09-visits-history.png)

- Search **all** visits by name, phone, visit number, host or destination
- Filter by **status, purpose, month, year or exact date range**
- **Export to CSV** for Excel or Google Sheets

> What used to take hours of manual counting now takes seconds.

---

## Key capability: live site presence

![w:1050](images/08-visits-today.png)

The desk can see, at a glance, **everyone currently on site**, and sign them out
with a single click — a directly measurable security improvement.

---

## Security and accountability built in

| Control | What it gives us |
| --- | --- |
| **Individual accounts** | Every action is traceable to a person, not a shared PIN |
| **Hashed passwords** | Credentials cannot be read from the database |
| **Role-based access** | Officers see only reception; admins see administration |
| **Named audit trail** | Each visit records who created it and who signed it out |
| **One active visit per day** | Blocks duplicate or unclosed entries |
| **Protected admin actions** | Administrators cannot lock themselves out |

---

## Two modules, two audiences

| | **Reception** | **Admin** |
| --- | --- | --- |
| **Users** | Desk and security officers | System administrators |
| **Focus** | Check-in, sign-out, history | Users, roles, locations, reports |
| **Lands on** | Visitor Check-In | Admin Dashboard |

The system decides automatically after login, based on the user's role.

---

## Administration at a glance

![w:1050](images/03-admin-dashboard.png)

Live counts of visitors, visits, site occupancy, users and locations — an
operational picture for supervisors at any moment.

---

## Managing people and permissions

![w:1000](images/04-admin-users.png)

- Create, edit, disable or delete user accounts
- Assign roles; change them without touching code
- **Disable rather than delete** to preserve audit history

---

## Roles are configurable, not hard-coded

![w:1000](images/05-admin-roles.png)

New roles can be created by administrators and pointed at the appropriate module.
The organisation is not locked into two fixed permission levels.

---

## Reporting for management

![w:1050](images/07-admin-reports.png)

Answers questions such as:

- How many official visitors did we host this month?
- Which departments receive the most visitors?
- Who was on site on the day of a specific incident?
- What are our peak visiting periods?

All exportable, all filterable by flexible date ranges.

---

## Organisational structure supported

![w:1000](images/06-admin-locations.png)

Departments, commands and units are modelled with parent-child relationships,
allowing destinations to reflect the real command structure.

---

## Privacy and data protection

Visitor information is **personal data** and is treated accordingly.

- Visitor photographs are excluded from source control
- Databases and captured images are kept out of the repository
- Passwords are stored only as salted hashes
- Access requires authentication and a recognised role

> **Note:** Before production deployment, add encryption at rest, a formal retention
> policy, scheduled secure backups and complete audit logging.

---

## What has been delivered

| Capability | Status |
| --- | --- |
| Visitor registration and lookup | ✅ Delivered |
| Photograph capture and portrait processing | ✅ Delivered |
| Visit creation with QR slips | ✅ Delivered |
| Sign-in / sign-out tracking | ✅ Delivered |
| Daily and historical reporting with export | ✅ Delivered |
| User accounts, roles and permissions | ✅ Delivered |
| Admin dashboard and user management | ✅ Delivered |
| Biometric fingerprint / voice capture | 🔜 Future (fields reserved) |

---

## Where this can go next

<!-- _class: lead -->

**Phase 2 candidates**

- Badge printing and QR scanning at gates
- SMS or email visitor notifications
- Photo-to-host alerts when a visitor arrives
- Cloud hosting with automatic backups
- Mobile app for security patrols
- Integration with access-control hardware

---

## Recommended next steps

1. **Pilot** at one reception desk for two weeks
2. Gather **officer feedback** and refine the workflow
3. **Harden** for production: backups, retention policy, HTTPS
4. **Train** reception staff using the published User Guide
5. **Roll out** to remaining facilities

> The prototype is functional and demonstrated. The remaining work is operational
> hardening and rollout, not core development.

---

## The value proposition

| Before | After |
| --- | --- |
| Paper registers | Searchable digital records |
| Manual counting | Instant reports |
| No live occupancy view | Real-time site presence |
| Shared desk PIN | Named, auditable accounts |
| Re-typing returning visitors | One-second lookup |
| No management visibility | Dashboard and exports on demand |

---

<!-- _class: lead -->
<!-- _paginate: false -->

# Thank you

### NCS Visitor Management System

**Questions and discussion**

Author: Yange Henry Terzugwe
Software Developer • AI & Robotics Practitioner

---

*NCS Visitor Management System — Management Briefing, September 2026*