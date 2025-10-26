# Leave Policy Management System

A comprehensive Django-based REST API for managing leave policies and applications in a multi-tenant microservice architecture. This system implements secure APIs for HR managers to create/configure leave policies and for employees to apply for leave with automated validation, multi-level approval workflows, and comprehensive business rule enforcement.

### ERD
<img width="1377" height="942" alt="image" src="https://github.com/user-attachments/assets/bfeb503a-faff-43a6-b144-331d275e3ad1" />


## Setup Instructions

### Prerequisites

- Python 3.13+
- Poetry (for dependency management)
- PostgreSQL (recommended for production)

### Installation

1. **Clone the repository:**
```bash
git clone <repository-url>
cd leave_policy_mgmt
```

2. **Install dependencies with Poetry:**
```bash
poetry install
```

3. **Configure environment variables:**
Copy the example environment file and customize it:
```bash
cp .env.example .env
```

Then edit the `.env` file with your specific configuration. The `.env.example` file contains all required environment variables with development defaults, including CORS and CSRF settings for frontend integration.

4. **Run database migrations:**
```bash
poetry run python manage.py migrate
```

5. **Create a superuser (for admin access):**
```bash
poetry run python manage.py createsuperuser
```

6. **Run the development server:**
```bash
poetry run python manage.py runserver
```

The API will be available at `http://localhost:8000/api/v1/`

## Run with Docker Compose (Development)

This project ships with a Dockerized development setup. Development mode is enforced in all Docker configs by default.

- DJANGO_SETTINGS_MODULE: `config.settings.development` (default in Dockerfile and docker-compose)
- DEBUG: `True` (default in docker-compose)
- Package manager: `uv` with `requirements.txt`

### Prerequisites
- Docker
- Docker Compose

### Quick start
```bash
cp .env.example .env   # optional, defaults work out-of-the-box
docker-compose up --build
```

### What happens on startup
- Runs database migrations: `python manage.py migrate --settings=config.settings.development`
- Collects static files: `python manage.py collectstatic --noinput --clear`
- Starts Gunicorn app server behind nginx

### URLs (development)
- App root: `http://localhost:8000/`
- Health: `http://localhost:8000/health/`
- API base: `http://localhost:8000/api/v1/`
- Admin: `http://localhost:8000/admin/`

Notes:
- nginx is exposed on host port 8000 and proxies to the Django app on port 8000.
- Static files are served by nginx from the shared `staticfiles` volume.

## API Documentation

Interactive API docs available at `/api/v1/docs/` (Swagger UI) and `/api/v1/redoc/` (ReDoc)
<img width="1920" height="1076" alt="image" src="https://github.com/user-attachments/assets/a57c7bd7-ca4f-419a-8bcb-84cf989561eb" />

<img width="1920" height="1076" alt="image" src="https://github.com/user-attachments/assets/704d21d4-0633-4908-bcd5-1cbf52c4f2eb" />

### Authentication
All API endpoints require JWT authentication via Bearer token in the Authorization header.

### Base URL
```
https://your-domain.com/api/v1/
```

### Core Endpoints

#### Policy Management (`/api/v1/policy/`)

**Policy Management - Policies**
- `GET /policy/` - List leave policies
- `POST /policy/` - Create leave policy (with auto-versioning)
- `GET /policy/{id}/` - Retrieve leave policy
- `PUT /policy/{id}/` - Update leave policy (creates new version if approved)
- `DELETE /policy/{id}/` - Delete leave policy
- `POST /policy/{id}/approve/` - Approve policy version
- `POST /policy/{id}/reject/` - Reject policy version

#### Leave Management (`/api/v1/leave/`)

**Leave Management - Categories**
- `GET /category/` - List leave categories
- `POST /category/` - Create leave category (HR/Admin only)
- `GET /category/{id}/` - Retrieve leave category
- `PUT /category/{id}/` - Update leave category (HR/Admin only)
- `DELETE /category/{id}/` - Delete leave category (HR/Admin only)

**Leave Management - Applications**
- `GET /application/` - List leave applications
- `POST /application/` - Create leave application (with policy validation)
- `GET /application/{id}/` - Retrieve leave application
- `POST /application/{id}/cancel/` - Cancel pending application (employee only)

**Leave Management - Approvals**
- `POST /approval/{id}/approve/` - Approve leave application
- `POST /approval/{id}/reject/` - Reject leave application
- `GET /workflow/` - List approval workflows

**Leave Management - Comments**
- `GET /application-comment/{id}/comments/` - Get application comments
- `POST /application-comment/{id}/add_comment/` - Add comment to application
- `GET /comment/` - List all comments
- `POST /comment/` - Create comment
- `GET /comment/{id}/` - Retrieve comment
- `PUT /comment/{id}/` - Update comment
- `DELETE /comment/{id}/` - Delete comment

**Leave Management - Balances**
- `GET /balance/` - List leave balances (own balance for employees, all for HR)

### Example API Usage

#### Create a Leave Policy
```bash
curl -X POST "http://localhost:8000/api/v1/policy/policy/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "data":"data"
  }'
```

#### Submit a Leave Application
```bash
curl -X POST "http://localhost:8000/api/v1/leave/application/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "data":"data"
  }'
```

### As Per The Given UI: 

Create Policy: `POST: /api/v1/policy/`

Policy List Page: `GET: /api/v1/policy/`

View Individual Policy: `GET: /api/v1/policy/{id}/`

Edit Policy: `PUT/PATCH: /api/v1/policy/{id}/`

Apply Leave: 
  1. GET Leave Category: `GET: /api/v1/leave/category/`
  2. GET Policies On Category: `GET: /api/v1/policy?leave_category={id}`
  3. GET Leave Balance: `GET: /api/v1/leave/balance?leave_category_id={id}&employee_id={emp_id}&year={year}`
  4. CREATE Leave Application: `POST: /api/v1/leave/application/`

Leave Approval With Comment:
  1. GET Pending Applications: `GET: /api/v1/leave/application?status=pending`
  2. View Application Details: `GET: /api/v1/leave/application/{id}/`
  3. GET Application Comments: `GET: /api/v1/leave/application-comment/{id}/comments/`
  4. ADD Comment: `POST: /api/v1/leave/application-comment/{id}/add_comment/`
  5. APPROVE Application: `POST: /api/v1/leave/approval/{id}/approve/`
  6. REJECT Application: `POST: /api/v1/leave/approval/{id}/reject/`

Authentication:
  - All endpoints require JWT token in Authorization header
  - Format: `Bearer {token}`
  - External authentication service integration

## Project Structure

```
leave_policy_mgmt/
├── config/                          # Django project configuration
│   ├── settings/                   # Environment-specific settings
│   │   ├── base.py                 # Base settings
│   │   ├── development.py          # Development settings
│   │   ├── staging.py              # Staging settings
│   │   └── production.py           # Production settings
│   ├── urls.py                     # Main URL configuration
│   ├── wsgi.py                     # WSGI configuration
│   └── asgi.py                     # ASGI configuration
├── apps/                           # Django applications
│   ├── policy/                     # Policy Management App
│   │   ├── models.py               # Policy models (policies, approvals)
│   │   ├── services.py             # Policy business logic
│   │   ├── factories.py            # Test data factories
│   │   ├── apps.py                 # App configuration
│   │   └── migrations/             # Database migrations
│   ├── leave/                      # Leave Management App
│   │   ├── models.py               # Leave models (categories, applications, balances, comments, workflows)
│   │   ├── services.py             # Leave business logic
│   │   ├── factories.py            # Test data factories
│   │   ├── apps.py                 # App configuration
│   │   └── migrations/             # Database migrations
│   └── api/                        # API layer
│       └── v1/                     # API version 1
│           ├── policy/             # Policy API endpoints
│           │   ├── api.py          # Policy views (ViewSets)
│           │   ├── serializers.py  # Policy data serializers
│           │   ├── permissions.py  # Policy permissions
│           │   ├── tests/          # Policy API tests
│           │   │   └── test_policy.py
│           │   └── urls.py         # Policy URL patterns
│           ├── leave/              # Leave API endpoints
│           │   ├── api.py          # Leave views (ViewSets)
│           │   ├── serializers.py  # Leave data serializers
│           │   ├── permissions.py  # Leave permissions
│           │   ├── tests/          # Leave API tests
│           │   │   ├── test_application.py
│           │   │   ├── test_balance.py
│           │   │   ├── test_category.py
│           │   │   ├── test_comment.py
│           │   │   └── test_workflow.py
│           │   └── urls.py         # Leave URL patterns
│           └── urls.py             # Main API v1 URLs (docs, schema)
├── core/                           # Shared utilities
│   ├── authentication.py           # JWT authentication
│   ├── middleware.py               # Tenant middleware
│   ├── pagination.py               # Standard pagination
│   ├── permissions.py              # Base permissions
│   ├── schema.py                   # OpenAPI schema extensions
│   ├── logging.py                  # Request/response logging
│   ├── exceptions.py               # Custom exceptions
│   └── responses.py                # Response utilities
├── manage.py                       # Django management script
├── pyproject.toml                  # Poetry configuration
├── poetry.lock                     # Poetry lock file
├── db.sqlite3                      # Development database
└── README.md                       # This file
```

## Business Rules Implemented

### Multi-tenancy & Security
- Complete tenant isolation at database level
- JWT token validation with external auth service
- Role-based permissions (Employee, HR, Admin)
- Critical field protection (status, policy selection, etc.)
- Comprehensive input validation and sanitization

## Development

### Running Tests
```bash
poetry run python manage.py test
```

### API Schema
Access the OpenAPI schema at `/api/v1/schema/`


## Deployment

### Environment Variables
Copy and customize the `.env.example` file for your environment. Refer to the file for all available configuration options.

## Development

### Running Tests

```bash
poetry run python manage.py test
```



### API Schema & Documentation

- **OpenAPI Schema**: `/api/v1/schema/`
- **Swagger UI**: `/api/v1/docs/`
- **ReDoc**: `/api/v1/redoc/`

## Deployment

The project supports multiple environments:
- Development (SQLite)
- Staging (PostgreSQL)
- Production (PostgreSQL with SSL)

Set the appropriate settings module using the `DJANGO_SETTINGS_MODULE` environment variable.
