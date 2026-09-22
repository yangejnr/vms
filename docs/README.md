# NCS Visitor Management System — Documentation

This folder contains the full documentation set for the NCS Visitor Management
System. Each document serves a different audience.

| Document | Audience | Purpose |
| --- | --- | --- |
| [User Guide](USER_GUIDE.md) | Reception officers, administrators | Step-by-step operating instructions with screenshots. **Use this for training.** |
| [Management Presentation](MANAGEMENT_PRESENTATION.md) | Management, sponsors | Slide deck covering the problem, solution, value and next steps |
| [Technical Documentation](TECHNICAL_DOCUMENTATION.md) | Developers, maintainers | Architecture, data model, API reference, security notes and extension guide |
| [Business Requirements Specification](BUSINESS_REQUIREMENTS.md) | Management, stakeholders | Formal requirements, acceptance criteria, risks and go-live checklist |

---

## Quick Start by Role

**I am a reception officer**
→ Read the [User Guide](USER_GUIDE.md), sections 3 to 6.

**I am an administrator**
→ Read the [User Guide](USER_GUIDE.md), section 7 (Admin Module).

**I am presenting to management**
→ Open the [Management Presentation](MANAGEMENT_PRESENTATION.md).

**I am a developer taking over the code**
→ Start with the [Technical Documentation](TECHNICAL_DOCUMENTATION.md), then read
sections 9 (Instance Path) and 16 (Known Limitations) carefully.

**I need to sign off on requirements**
→ Review the [Business Requirements Specification](BUSINESS_REQUIREMENTS.md),
particularly sections 7 (Functional Requirements) and 14 (Acceptance Criteria).

---

## Word (.docx) versions

Ready-to-share Word documents are provided alongside the Markdown sources:

| Word document | Source |
| --- | --- |
| `USER_GUIDE.docx` | `USER_GUIDE.md` |
| `MANAGEMENT_PRESENTATION.docx` | `MANAGEMENT_PRESENTATION.md` |
| `TECHNICAL_DOCUMENTATION.docx` | `TECHNICAL_DOCUMENTATION.md` |
| `BUSINESS_REQUIREMENTS.docx` | `BUSINESS_REQUIREMENTS.md` |
| `README.docx` | `README.md` |

These are generated, fully formatted Word files with styled headings, colour-coded
tables, embedded screenshots, a running header, and page numbers in the footer.

### Regenerating the Word documents

After editing any Markdown source, regenerate the Word files:

```bash
./.venv/bin/python tools/md_to_docx.py               # all documents
./.venv/bin/python tools/md_to_docx.py docs/USER_GUIDE.md   # just one
```

The converter requires `python-docx` (`pip install python-docx`).

> **Updating the table of contents:** Word does not build TOC fields
> automatically. Open the document, right-click the table of contents line and
> choose **Update Field → Update entire table**.

---

## Rendering the Documents

All documents are written in **Markdown**, so they display on GitHub and in VS Code
with no extra tooling. The User Guide and Technical Documentation include relative
links to screenshots in `docs/images/`.

### Exporting to PDF

**VS Code:** open the document, then use the *Markdown PDF* extension
(`yzane.markdown-pdf`) → *Markdown PDF: Export (pdf)*.

**Pandoc:**

```bash
pandoc docs/USER_GUIDE.md -o user-guide.pdf \
  --toc --number-sections --resource-path=docs
```

### Rendering the presentation as slides

`MANAGEMENT_PRESENTATION.md` uses [Marp](https://marp.app/). Options:

```bash
# HTML slides
npx @marp-team/marp-cli docs/MANAGEMENT_PRESENTATION.md -o presentation.html

# PDF slides
npx @marp-team/marp-cli docs/MANAGEMENT_PRESENTATION.md --pdf -o presentation.pdf

# PowerPoint
npx @marp-team/marp-cli docs/MANAGEMENT_PRESENTATION.md --pptx -o presentation.pptx
```

The VS Code *Marp for VS Code* extension also previews it live.

---

## Screenshots

All screenshots in `docs/images/` were captured from the running application using
demonstration data (fictional visitors and service numbers). No real visitor
information is included.

| File | Shows |
| --- | --- |
| `01-landing-page.png` | Public landing page |
| `02-login-modal.png` | Login dialog |
| `03-admin-dashboard.png` | Admin dashboard with statistics |
| `04-admin-users.png` | User management |
| `05-admin-roles.png` | Role management |
| `06-admin-locations.png` | Location management |
| `07-admin-reports.png` | Visit reports with filters |
| `08-visits-today.png` | Today's visits with sign-out |
| `09-visits-history.png` | Visit history with filters |
| `10-checkin.png` | Reception check-in page |
| `11-add-user-modal.png` | Add-user form |
| `12-officer-checkin.png` | Officer view of check-in |

### Regenerating screenshots

If the interface changes, re-capture the images so the documentation stays accurate.
The screenshots were produced by seeding demo data, visiting each page at 1440×900
and saving a screenshot per page.

---

## Document Conventions

- **`code`** formatting indicates a field name, value, command or endpoint.
- Requirement IDs are stable: `FR-*` functional, `NFR-*` non-functional,
  `BR-*` business rule, `BO-*` objective, `AC-*` acceptance criterion, `R-*` risk,
  `FE-*` future enhancement.
- ✅ and ❌ indicate verified and outstanding respectively.

---

*NCS Visitor Management System — Documentation Index*