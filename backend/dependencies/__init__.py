"""FastAPI dependency factories, grouped by concern.

- :mod:`dependencies.auth` -- the session cookie, CSRF, tenant scope, roles
- :mod:`dependencies.authz` -- ``require_roles`` route guards
- :mod:`dependencies.context` -- request-scoped helpers and ``APP_NAME``
- :mod:`dependencies.singletons` -- LRU-cached process-wide singletons
- :mod:`dependencies.repository` -- per-request repositories and the DB session
- :mod:`dependencies.service` -- per-request services (use cases)

Import from the submodule that defines what you need.
"""
