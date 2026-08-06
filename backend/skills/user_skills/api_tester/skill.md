---
name: api-tester
description: API testing, endpoint validation, performance testing, mock data generation, and automated API workflows
emoji: 🔌
priority: 2
---

## Instructions

When user needs API testing help, or says:
- "API test koro"
- "Endpoint check koro"
- "API performance dekhao"
- "Mock data banao"
- "Postman collection create koro"

Activate **API Tester Mode**:

### 1. 🔌 Quick API Testing

```
🔌 API QUICK TEST

Testing: GET /api/users/123

**REQUEST:**
```
GET https://jsonplaceholder.typicode.com/users/1
Headers:
  Content-Type: application/json
  Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**RESPONSE:**
Status: ✅ 200 OK
Time: 234ms
Size: 521 bytes

```json
{
  "id": 1,
  "name": "Leanne Graham",
  "username": "Bret",
  "email": "Sincere@april.biz",
  "address": {
    "street": "Kulas Light",
    "city": "Gwenborough"
  }
}
```

**VALIDATION:**
✅ Status code: 200
✅ Response time: < 500ms
✅ Has required fields: id, name, email
✅ Email format valid
✅ Response size acceptable
```

### 2. 🎯 Comprehensive API Test Suite

```
🎯 API TEST SUITE

**ENDPOINT:** POST /api/auth/login

**TEST CASES:**

**✅ TC001: Valid Login**
```json
Request:
{
  "email": "test@example.com",
  "password": "Password123!"
}

Expected: 200 OK + JWT token
Actual: ✅ PASS
Response Time: 145ms
```

**❌ TC002: Invalid Email**
```json
Request:
{
  "email": "invalid-email",
  "password": "Password123!"
}

Expected: 400 Bad Request
Actual: ❌ FAIL (Got 500 instead of 400)
```

**✅ TC003: Missing Password**
```json
Request:
{
  "email": "test@example.com"
}

Expected: 400 Bad Request + error message
Actual: ✅ PASS
Error: "Password is required"
```

**✅ TC004: SQL Injection Attack**
```json
Request:
{
  "email": "admin@test.com",
  "password": "' OR '1'='1"
}

Expected: 400/401 (Not 200!)
Actual: ✅ PASS (Properly blocked)
```

**📊 SUMMARY:**
- Total Tests: 15
- Passed: 13 (87%)
- Failed: 2 (13%)
- Average Response: 178ms
- Security Issues: 0
```

### 3. 🏃 Performance Testing

```
🏃 API PERFORMANCE TEST

**LOAD TEST:** GET /api/products

**TEST SCENARIO:**
- Virtual Users: 100
- Duration: 5 minutes
- Ramp-up: 30 seconds

**RESULTS:**

**📊 Response Times:**
- Average: 245ms
- Median: 198ms
- 95th percentile: 450ms
- 99th percentile: 890ms
- Max: 1.2s

**🔥 Throughput:**
- Requests/sec: 387
- Total Requests: 116,100
- Failed Requests: 23 (0.02%)

**📈 PERFORMANCE GRAPH:**
```
Response Time Trend:
400ms ┤     ╭─╮
350ms ┤   ╭─╯ ╰─╮
300ms ┤ ╭─╯     ╰─╮
250ms ┼─╯         ╰───
200ms ┤
      └─────────────────
      0min 2min 4min 5min
```

**⚠️ ISSUES FOUND:**
1. Response time spikes at 3min mark
2. Memory usage increases during test
3. DB connection pool exhausted at 80 users

**💡 RECOMMENDATIONS:**
- Optimize database queries
- Increase connection pool size
- Add response caching
- Implement rate limiting
```

### 4. 🤖 Mock API Generator

```
🤖 MOCK API GENERATOR

**API:** E-commerce Product API

**AUTO-GENERATED ENDPOINTS:**

**GET /api/products**
```json
[
  {
    "id": 1,
    "name": "Wireless Bluetooth Headphones",
    "price": 79.99,
    "category": "Electronics",
    "in_stock": true,
    "rating": 4.5,
    "reviews": 127,
    "images": [
      "https://fake-api.com/images/product1-1.jpg",
      "https://fake-api.com/images/product1-2.jpg"
    ],
    "description": "High-quality wireless headphones with noise cancellation",
    "brand": "TechSound",
    "color": "Black",
    "weight": "250g",
    "created_at": "2026-03-15T10:30:00Z"
  }
]
```

**POST /api/products**
```json
Request Body:
{
  "name": "New Product",
  "price": 99.99,
  "category": "Electronics"
}

Response: 201 Created
{
  "id": 101,
  "name": "New Product",
  "price": 99.99,
  "category": "Electronics",
  "in_stock": true,
  "created_at": "2026-08-04T15:22:30Z"
}
```

**MOCK SERVER STARTED:**
🌐 http://localhost:3001
📝 Swagger UI: http://localhost:3001/docs
🔄 Auto-refresh: Enabled
📊 Request logging: Enabled

**FEATURES:**
✅ Realistic fake data
✅ Random delays (50-200ms)
✅ Error scenarios (5% failure rate)
✅ CORS enabled
✅ Request/response logging
```

### 5. 📋 API Documentation Generator

```
📋 API DOCUMENTATION

**AUTO-GENERATED FROM TESTS**

# User Management API

## Authentication
All endpoints require JWT token in header:
```
Authorization: Bearer <token>
```

## Endpoints

### 1. User Registration
**POST** `/api/auth/register`

**Request:**
```json
{
  "name": "string (required, min: 2, max: 50)",
  "email": "string (required, valid email)",
  "password": "string (required, min: 8, must contain number)"
}
```

**Responses:**
- **201 Created:** User successfully created
- **400 Bad Request:** Validation errors
- **409 Conflict:** Email already exists

**Example:**
```bash
curl -X POST https://api.example.com/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com", 
    "password": "SecurePass123"
  }'
```

### 2. Get User Profile
**GET** `/api/users/{id}`

**Parameters:**
- `id` (path, integer): User ID

**Responses:**
- **200 OK:** User data returned
- **401 Unauthorized:** Invalid/missing token
- **404 Not Found:** User doesn't exist

**Rate Limiting:** 100 requests/minute per user

**Caching:** Responses cached for 5 minutes
```

### 6. 🔒 API Security Testing

```
🔒 API SECURITY SCAN

**SECURITY TEST REPORT**

**ENDPOINT:** /api/users

**✅ PASSED TESTS:**

1. **Authentication Required**
   - Test: Access without token
   - Result: ✅ 401 Unauthorized (Correct)

2. **JWT Token Validation** 
   - Test: Invalid/expired tokens
   - Result: ✅ Properly rejected

3. **Input Validation**
   - Test: XSS, SQL injection, script injection
   - Result: ✅ All blocked

4. **Rate Limiting**
   - Test: 1000 requests in 1 minute
   - Result: ✅ Blocked after 100 requests

**⚠️ FAILED TESTS:**

5. **HTTPS Enforcement**
   - Test: HTTP request
   - Result: ❌ Should redirect to HTTPS (Got 200)
   - Risk: Medium

6. **Sensitive Data Exposure**
   - Test: Error messages
   - Result: ❌ Database error exposed in response
   - Risk: High

**🚨 VULNERABILITIES FOUND:**

**HIGH RISK:**
- Database stack traces in error responses
- User passwords returned in /api/users endpoint (!)

**MEDIUM RISK:**
- No HTTPS enforcement
- Missing CORS policy
- Weak password requirements

**LOW RISK:**
- Verbose server headers
- No request ID tracing

**📋 REMEDIATION:**
1. Remove passwords from user responses (URGENT)
2. Add generic error messages
3. Enforce HTTPS redirects
4. Update password policy (min 12 chars)
5. Add security headers
```

### 7. 📊 API Monitoring Dashboard

```
📊 API MONITORING DASHBOARD

**Real-time Metrics** (Last 24 hours)

**📈 REQUEST VOLUME:**
```
Requests per Hour:
800 ┤     ╭─────╮
600 ┤   ╭─╯     ╰─╮
400 ┤ ╭─╯         ╰─╮
200 ┼─╯             ╰───
  0 ┤
    └─────────────────────
    6AM  12PM  6PM  12AM
```

**⚡ RESPONSE TIMES:**
- Average: 156ms (Target: < 200ms) ✅
- P95: 340ms (Target: < 500ms) ✅  
- P99: 890ms (Target: < 1000ms) ✅

**📊 STATUS CODES:**
- 2xx Success: 94.3% (145,230 requests)
- 4xx Client Error: 4.2% (6,470 requests)
- 5xx Server Error: 1.5% (2,310 requests) ⚠️

**🔥 TOP ENDPOINTS:**
1. GET /api/products - 45% traffic
2. POST /api/auth/login - 18% traffic  
3. GET /api/users/me - 12% traffic
4. POST /api/orders - 8% traffic

**⚠️ ALERTS:**
1. Error rate spike at 2:30 PM (7% errors)
2. Slow query on /api/analytics (1.2s avg)
3. High memory usage on server-02 (89%)

**🎯 SLA STATUS:**
- Uptime: 99.94% ✅ (Target: 99.9%)
- Availability: 99.97% ✅
- Error Rate: 1.5% ✅ (Target: < 2%)
```

### 8. 🧪 API Testing Automation

```
🧪 AUTOMATED TEST PIPELINE

**CI/CD Integration**

**Stage 1: Unit Tests**
```yaml
# .github/workflows/api-tests.yml
name: API Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run API Tests
        run: |
          npm run test:api
          newman run postman-collection.json
```

**Stage 2: Contract Testing**
```bash
# Verify API matches OpenAPI spec
swagger-codegen validate -i api-spec.yaml

# Consumer contract testing (Pact)
pact-broker publish-pacts \
  --consumer-app-version $GIT_COMMIT \
  --branch $GIT_BRANCH
```

**Stage 3: Load Testing**
```javascript
// k6 load test script
import http from 'k6/http';
import { check } from 'k6';

export let options = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '5m', target: 500 },
    { duration: '2m', target: 0 }
  ]
};

export default function() {
  let response = http.get('https://api.example.com/products');
  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500
  });
}
```

**Stage 4: Security Scanning**
```bash
# OWASP ZAP security scan
docker run -v $(pwd):/zap/wrk/:rw \
  owasp/zap2docker-stable zap-api-scan.py \
  -t https://api.example.com/openapi.json \
  -f openapi
```

**📊 TEST RESULTS:**
```
✅ Unit Tests: 127/127 passed
✅ Integration Tests: 45/45 passed  
✅ Contract Tests: 12/12 passed
✅ Load Tests: All thresholds met
⚠️ Security Scan: 2 medium risks found

Build Status: ✅ PASSED
Deploy to Staging: ✅ APPROVED
```
```

### 9. 📱 API Client Generation

```
📱 API CLIENT GENERATOR

**GENERATED CLIENTS FROM OPENAPI SPEC**

**JavaScript/TypeScript Client:**
```typescript
// Auto-generated API client
import { UserApi, Configuration } from './generated/api';

const config = new Configuration({
  basePath: 'https://api.example.com',
  apiKey: 'your-api-key'
});

const userApi = new UserApi(config);

// Type-safe API calls
const user = await userApi.getUserById(123);
// user.name is typed as string
// user.email is typed as string
```

**Python Client:**
```python
# Auto-generated Python client
from api_client import ApiClient, UsersApi

client = ApiClient(host='https://api.example.com')
client.set_default_header('Authorization', 'Bearer token')

users_api = UsersApi(client)
user = users_api.get_user_by_id(123)
print(user.name)  # Type hints included
```

**cURL Examples:**
```bash
# Get all users
curl -X GET "https://api.example.com/users" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Create new user  
curl -X POST "https://api.example.com/users" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com"
  }'

# Update user
curl -X PUT "https://api.example.com/users/123" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"name": "John Smith"}'
```

**Postman Collection:**
```json
{
  "info": { "name": "User API Collection" },
  "item": [
    {
      "name": "Get Users",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/users",
        "header": [
          {
            "key": "Authorization", 
            "value": "Bearer {{token}}"
          }
        ]
      },
      "test": "pm.test('Status 200', () => pm.response.to.have.status(200));"
    }
  ],
  "variable": [
    {"key": "base_url", "value": "https://api.example.com"}
  ]
}
```
```

### 10. 🔄 API Workflow Testing

```
🔄 API WORKFLOW TESTING

**E-COMMERCE USER JOURNEY**

**Workflow: Complete Purchase Flow**

**Step 1: User Registration** ✅
```
POST /api/auth/register
Request: {"name": "Test User", "email": "test@example.com", "password": "Test123!"}
Response: 201 Created
Variables Captured:
  - user_id: 456
  - auth_token: eyJhbGciOiJIUzI1NiIs...
```

**Step 2: Browse Products** ✅
```
GET /api/products?category=electronics
Headers: Authorization: Bearer {{auth_token}}
Response: 200 OK (24 products found)
Variables Captured:
  - product_id: 789 (Selected "Laptop Pro")
  - product_price: 1299.99
```

**Step 3: Add to Cart** ✅
```
POST /api/cart/items
Body: {"product_id": 789, "quantity": 1}
Headers: Authorization: Bearer {{auth_token}}  
Response: 201 Created
Variables Captured:
  - cart_item_id: 101
  - cart_total: 1299.99
```

**Step 4: Apply Discount** ✅
```
POST /api/cart/discount
Body: {"code": "SAVE20"}
Headers: Authorization: Bearer {{auth_token}}
Response: 200 OK
Variables Captured:
  - discount_amount: 260.00
  - final_total: 1039.99
```

**Step 5: Checkout** ✅
```
POST /api/orders
Body: {
  "payment_method": "card", 
  "card_token": "tok_test_123",
  "shipping_address": {...}
}
Headers: Authorization: Bearer {{auth_token}}
Response: 201 Created
Variables Captured:
  - order_id: 555
  - payment_status: "completed"
```

**Step 6: Order Confirmation** ✅
```
GET /api/orders/555
Headers: Authorization: Bearer {{auth_token}}
Response: 200 OK
Validation:
  ✅ Order status: "confirmed"
  ✅ Total amount: 1039.99
  ✅ Payment completed: true
```

**📊 WORKFLOW RESULTS:**
- Total Steps: 6
- Passed: 6 ✅
- Failed: 0
- Total Time: 1.2 seconds
- Data Consistency: ✅ Verified

**🔄 ROLLBACK TEST:**
Testing order cancellation...
```
DELETE /api/orders/555
Response: 200 OK
Validation:
  ✅ Order marked as cancelled
  ✅ Payment refund initiated  
  ✅ Inventory restored
```
```

### Response Style

- Show actual HTTP requests/responses
- Include realistic test data
- Visual progress indicators
- Color-coded test results (✅❌⚠️)
- Performance metrics with graphs
- Security-focused recommendations
- Always provide working examples
