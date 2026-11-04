"""The scopes a service token can carry.

One place so the admin UI can offer a checkbox list instead of asking an
admin to type a scope string exactly right - a typo there produces a token
that authenticates but 403s, which is a confusing failure to debug.
Every scope named here must be enforced by some route via
`core.deps.require_service_token(...)`.
"""

EMPLOYEES_EXPORT = "employees:depot-export"

SERVICE_SCOPES = [
    {
        "code": EMPLOYEES_EXPORT,
        "label": "Employee export feed",
        "description": "Read-only access to GET /api/v1/integrations/employees "
                       "and /employees/rules - the operating-crew feed consumed "
                       "by the depot app.",
    },
]

SCOPE_CODES = {s["code"] for s in SERVICE_SCOPES}
