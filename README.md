<<<<<<< HEAD
# BVS
=======
# Community-based beneficiary validation
>>>>>>> 735726af4bb2ba1850e15b2f6c3799562e4f73b2

BVS is a Django-based beneficiary registry and validation system for managing household records, beneficiary profiles, employee workflows, and grievance handling.

## Project overview

The application includes:

- A login and dashboard experience
- A beneficiary registry and detail views
- Beneficiary location and photo management
- Program and employee management
- Validation workflows and grievance resolution
- Import/export support for registry data

## Tech stack

- Python
- Django 5.2
- SQLite (default development database)
- Pandas
- Pillow

## Project structure

```text
bvs/
├── manage.py
├── requirements.txt
├── db.sqlite3
├── bvs/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── bvsbackend/
│   ├── admin.py
│   ├── apps.py
│   ├── forms.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   ├── views.py
│   ├── migrations/
│   ├── static/
│   └── templates/
└── README.md
```

## Prerequisites

- Python 3.10+
- pip
- A virtual environment is recommended

## Setup

1. Open a terminal in the project root:

```bash
cd bvs
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Apply database migrations:

```bash
python manage.py migrate
```

5. Create an admin user (optional but recommended):

```bash
python manage.py createsuperuser
```

## Run the app

Start the development server:

```bash
python manage.py runserver
```

Then open:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/admin/ (redirects to dashboard by default)

## Environment variables

The project supports a few optional environment variables defined in the Django settings:

```bash
export DJANGO_DEBUG=true
export DJANGO_SECRET_KEY=your-secret-key
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
```

If `DJANGO_SECRET_KEY` is not set while `DEBUG` is false, Django will raise an error.

## Common commands

Check project health:

```bash
python manage.py check
```

Run tests:

```bash
python manage.py test
```

Collect static files (if needed for deployment):

```bash
python manage.py collectstatic
```

## Notes

- The default database is SQLite for local development.
- Static files live under `bvsbackend/static/`.
- Templates are organized under `bvsbackend/templates/`.
- The project is set up for local development and should be hardened before production deployment.

## License

This project does not currently include a license file. If this repository is intended for public use, add an appropriate license before distribution.
