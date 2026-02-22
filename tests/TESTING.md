# Testing Guide

This document describes how to run and understand the test suite for the NTRIP stations finder application.

## Quick Start

### Install Test Dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` file includes all test dependencies:
- `pytest>=7.4.0` - Test framework
- `pytest-asyncio>=0.21.0` - Async test support
- `httpx>=0.24.0` - HTTP client for FastAPI testing

### Run All Tests

```bash
pytest tests/
```

### Run Tests with Verbose Output

```bash
pytest tests/ -v
```

### Run Specific Test File

```bash
pytest tests/test_rate_limiting.py -v
pytest tests/test_api_endpoints.py -v
```

### Run Specific Test Class

```bash
pytest tests/test_api_endpoints.py::TestIndexEndpoint -v
```

### Run Specific Test

```bash
pytest tests/test_api_endpoints.py::TestIndexEndpoint::test_index_returns_200 -v
```

## Test Structure

### Test Files

#### `tests/test_rate_limiting.py` (8 tests)
Tests for rate limiting configuration and functionality:

- **TestRateLimiting**
  - `test_search_requires_address_or_coordinates` - Validates search input requirements
  - `test_search_with_coordinates` - Tests search with explicit lat/lon
  - `test_empty_database_search_error` - Verifies proper error handling
  - `test_index_page_loads` - Checks home page displays correctly
  - `test_refresh_endpoint_works` - Validates refresh endpoint JSON response

- **TestRateLimitConfiguration**
  - `test_rate_limit_from_env` - Verifies search rate limit is read from .env file
  - `test_rate_limit_decorator_applied` - Confirms slowapi decorator is active on /search
  - `test_refresh_rate_limit_from_env` - Verifies refresh rate limit is read from .env file

#### `tests/test_api_endpoints.py` (23 tests)
Comprehensive tests for API endpoints, database operations, and NTRIP functions:

- **TestIndexEndpoint** (4 tests)
  - Homepage loads successfully
  - Form and controls are present
  - Country dropdown exists
  - Station count displays

- **TestSearchEndpoint** (5 tests)
  - Invalid input handling
  - Search with coordinates
  - Coordinate validation
  - Empty database handling
  - HTML response format

- **TestRefreshEndpoint** (3 tests)
  - JSON response format
  - Response structure validation
  - Rate limit decorator is applied

- **TestDatabaseSeeding** (5 tests)
  - Countries table is populated
  - Countries are sorted alphabetically
  - Station count accuracy
  - Last updated timestamp
  - Station data retrieval

- **TestNTRIPFunctionality** (5 tests)
  - Haversine distance calculation
  - Nearest station finding
  - Handling requests for more stations than available
  - NTRIP sourcetable parsing
  - Invalid line filtering

### Test Configuration

**pytest.ini** - Pytest configuration file:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
```

### Fixtures

**conftest.py** provides shared test fixtures:

- `temp_db` - Creates a temporary SQLite database for each test
  - Automatically creates tables
  - Seeds countries from CSV
  - Cleans up after test completes
  - Handles Windows file lock issues

- `client` - FastAPI TestClient with test database
  - Uses `temp_db` fixture
  - Overrides database dependency
  - Ready for HTTP requests

## What's Tested

### Rate Limiting
- ✅ Search rate limit read from `.env` file (`GEOAPIFY_API_RATE_LIMIT`)
- ✅ Refresh rate limit read from `.env` file (`REFRESH_DB_RATE_LIMIT`)
- ✅ slowapi decorator applied to `/search` endpoint
- ✅ slowapi decorator applied to `/refresh` endpoint
- ✅ Configuration format validation (e.g., "5/second", "10/minute", "1/day")

### API Endpoints
- ✅ `GET /` - Index page loads with form, country dropdown, and station count
- ✅ `POST /search` - Search validation, error handling, result formatting, rate limited (5/second)
- ✅ `POST /refresh` - JSON response structure, rate limited (1/day)

### Database Operations
- ✅ Countries table seeding (249 countries from CSV)
- ✅ Alphabetical sorting of countries
- ✅ Station count tracking
- ✅ Last updated timestamp management
- ✅ Station data retrieval as dictionaries

### NTRIP Functions
- ✅ Haversine distance calculation (great-circle distance)
- ✅ Finding nearest stations
- ✅ Sourcetable parsing from NTRIP protocol
- ✅ Invalid line filtering in sourcetable

### Input Validation
- ✅ Address/coordinate requirement in search
- ✅ Numeric coordinate validation
- ✅ Empty database handling
- ✅ Empty input detection

## Running Tests in CI/CD

To run tests in a continuous integration environment:

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests with coverage (if pytest-cov is added to requirements)
pytest tests/ -v --cov=app --cov-report=html

# Run tests and stop on first failure
pytest tests/ -v -x

# Run tests with timeout (if pytest-timeout is added to requirements)
pytest tests/ -v --timeout=10
```

## Common Test Commands

```bash
# Run all tests and show summary
pytest tests/

# Run tests and show which tests took longest
pytest tests/ -v --durations=10

# Run only tests matching a pattern
pytest tests/ -k "rate_limit" -v

# Run tests and stop on first failure
pytest tests/ -x

# Run tests with detailed output
pytest tests/ -vv

# Run tests and print print statements
pytest tests/ -s
```

## Troubleshooting

### Tests fail with "address or coordinates" error
This is expected if you're testing with an empty database. The search endpoint requires stations in the database to return results.

### Tests fail with file lock errors on Windows
The temporary database cleanup may fail due to SQLite file locks. This is handled gracefully - the files are cleaned up by the OS eventually. The tests still pass.

### Rate limit tests don't trigger 429 errors
The tests use a test client that bypasses actual rate limiting time windows. Real rate limiting is verified by the configuration tests. For manual testing:
- Make 6+ requests within 1 second to trigger the search rate limit
- Try refreshing the database more than once per day to trigger the refresh rate limit

### Refresh endpoint returns 429 rate limit error
The refresh endpoint is limited to 1 request per day per IP. If your tests call it multiple times, you may see "Rate limit exceeded" errors. This is expected behavior - the rate limiting is working correctly. Each test run gets a fresh test client with a unique (mocked) IP.

## Test Coverage

Current test coverage includes:
- ✅ All major API endpoints
- ✅ Database operations and seeding
- ✅ Core NTRIP functionality
- ✅ Input validation
- ✅ Rate limiting configuration
- ✅ Error handling

## Adding New Tests

To add new tests:

1. Create a test function starting with `test_`
2. Use the `client` fixture for HTTP requests
3. Use the `temp_db` fixture for database operations
4. Follow the existing test structure and naming conventions
5. Run `pytest tests/ -v` to verify

Example:

```python
def test_new_feature(self, client, temp_db):
    """Test description."""
    response = client.get("/endpoint")
    assert response.status_code == 200
    assert "expected content" in response.text
```

## Notes

- Tests use isolated temporary databases to avoid affecting production data
- FastAPI TestClient is used for synchronous HTTP testing
- Async functions are automatically handled by pytest-asyncio
- All tests are independent and can run in any order
- Database cleanup handles Windows file locking gracefully
