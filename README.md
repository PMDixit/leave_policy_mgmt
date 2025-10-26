# Leave Policy Management System

A comprehensive Django-based REST API for managing leave policies and applications in a multi-tenant microservice architecture. This system implements secure APIs for HR managers to create/configure leave policies and for employees to apply for leave with automated validation, multi-level approval workflows, and comprehensive business rule enforcement.

## Features

### Policy Management
- ✅ Multi-tenant leave policy creation and management
- ✅ Auto-versioning for policy modifications
- ✅ Hierarchical approval workflows (HR Manager → CHRO)
- ✅ Configurable leave entitlements and restrictions
- ✅ Policy applicability based on roles/departments
- ✅ Policy exclusions for specific roles
- ✅ Support for Annual, Sick, Casual, Maternity, Paternity, Sabbatical, Unpaid leave types

### Leave Applications
- ✅ Employee leave application submission with comprehensive validation
- ✅ Automated policy selection and validation
- ✅ Date range validation with half-day support
- ✅ Document requirement enforcement based on leave type/duration
- ✅ Multi-level approval routing based on organizational hierarchy
- ✅ Real-time leave balance tracking and validation
- ✅ Employee self-cancellation for pending applications
- ✅ Complete audit trail with comments and status history

### Security & Architecture
- ✅ Multi-tenancy support with tenant isolation
- ✅ JWT token-based authentication (external auth service integration)
- ✅ Role-based permissions (HR Admin, Policy Manager, Employee)
- ✅ Comprehensive input validation and business rule enforcement
- ✅ Audit logging for all leave transactions

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

### Useful commands
- Rebuild after code changes: `docker-compose up --build`
- Tail logs: `docker-compose logs -f app` (or `nginx`, `db`)
- Create superuser:
  ```bash
  docker-compose exec app python manage.py createsuperuser --settings=config.settings.development
  ```
- Stop: `docker-compose down`
- Stop and remove volumes (DB/static/media): `docker-compose down -v`

### Environment overrides (optional)
docker-compose already sets sane dev defaults. You can override via environment variables or `.env`:
```bash
DEBUG=True
DJANGO_SETTINGS_MODULE=config.settings.development
DB_NAME=leave_policy_db
DB_USER=postgres
DB_PASSWORD=password
ALLOWED_HOSTS=app,localhost,127.0.0.1
```

Notes:
- nginx is exposed on host port 8000 and proxies to the Django app on port 8000.
- Static files are served by nginx from the shared `staticfiles` volume.

## API Documentation

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
    "policy_name": "Annual Leave Policy 2024",
    "policy_type": "leave_time_off",
    "description": "Standard annual leave policy",
    "entitlement": ["Permanent"],
    "employment_duration_years": 1,
    "employment_duration_months": 0,
    "employment_duration_days": 0,
    "carry_forward": 5,
    "encashment": 5,
    "notice_period": 3,
    "limit_per_month": 2,
    "approval_route": [
      {"approver_id": "hr-manager-id", "approver_name": "HR Manager", "approver_role": "HR Manager"},
      {"approver_id": "chro-id", "approver_name": "Chief HR Officer", "approver_role": "CHRO"}
    ]
  }'
```

#### Submit a Leave Application
```bash
curl -X POST "http://localhost:8000/api/v1/leave/application/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "leave_category_id": "annual-category-uuid",
    "start_date": "2024-12-01",
    "end_date": "2024-12-05",
    "total_days": 5,
    "is_half_day": false,
    "reason": "Family vacation",
    "document_url": "https://example.com/medical-cert.pdf"
  }'
```

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

### Policy Validation Rules
- Auto-versioning for policy modifications
- Carry forward cannot exceed 365 days
- Encashment cannot exceed carry forward limit
- Hierarchical approval workflows (HR Manager → CHRO)
- Employment duration validation (years, months, days)
- Policy applicability based on employee roles/departments
- Policy exclusions for specific roles

### Leave Application Validation Rules
- **Date Validation**: Start date ≤ end date, dates not in past
- **Total Days Calculation**: Automatic validation against date range
- **Half-day Support**: 0.5 days for half-day applications
- **Balance Validation**: Sufficient leave balance for annual leave
- **Document Requirements**: Automatic based on leave type and duration
  - Sick leave > 3 days requires medical certificate
  - Category-based documentation thresholds
- **Overlapping Leave Prevention**: No concurrent leave applications
- **Monthly Limits**: Configurable applications per month per category
- **Notice Period Requirements**: Minimum advance notice
- **Employment Restrictions**: Role-based leave restrictions
- **Blackout Periods**: Configurable date restrictions

### Application Workflow
- **Status Flow**: Draft → Pending → Approved/Approved (unpaid)/Rejected/Cancelled
- **Employee Cancellation**: Only pending/draft applications can be cancelled by employees
- **Multi-level Approval**: Based on organizational hierarchy and policy rules
- **Automatic Balance Deduction**: On approval (for paid leave types)
- **Unpaid Leave Support**: Special "Approved (unpaid)" status for unpaid leave types
- **Audit Trail**: Complete history of status changes, comments, and approver actions

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

### API Documentation
Interactive API docs available at `/api/v1/docs/` (Swagger UI) and `/api/v1/redoc/` (ReDoc)

## Deployment

### Environment Variables
Copy and customize the `.env.example` file for your environment. Refer to the file for all available configuration options.

### CORS and CSRF Configuration
The application includes configurable CORS and CSRF settings for secure frontend integration:

- **`CORS_ALLOWED_ORIGINS`**: Comma-separated list of allowed origins (e.g., your React/Vue frontend URLs)
- **`CORS_ALLOW_CREDENTIALS`**: Enable/disable credentials in CORS requests
- **`CSRF_TRUSTED_ORIGINS`**: Comma-separated list of trusted origins for CSRF protection
- **`CSRF_COOKIE_SECURE`**: Use secure CSRF cookies (set to `True` in production with HTTPS)

**Development defaults:**
```bash
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080
CORS_ALLOW_CREDENTIALS=True
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080
CSRF_COOKIE_SECURE=False
```

**Production example:**
```bash
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com,https://www.your-frontend-domain.com
CORS_ALLOW_CREDENTIALS=True
CSRF_TRUSTED_ORIGINS=https://your-frontend-domain.com,https://www.your-frontend-domain.com
CSRF_COOKIE_SECURE=True
```

### Production Deployment
1. Set DEBUG=False
2. Use PostgreSQL database
3. Configure proper ALLOWED_HOSTS
4. Set up proper logging
5. Enable SSL/HTTPS
6. Configure static file serving

## License

This project is licensed under the MIT License.

## Development

### Running Tests

```bash
poetry run python manage.py test
```

### Code Formatting

```bash
poetry run black .
poetry run isort .
```

### Linting

```bash
poetry run flake8 .
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


As Per UI: 

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
