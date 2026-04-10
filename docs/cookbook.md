# Cookbook

Complete production patterns you can adapt directly.

---

## Refresh token rotation with grace period

A stateless access token + rotating refresh token auth system. Short-lived JWTs handle per-request validation without database lookups. Longer-lived refresh tokens rotate on each use with a grace window for concurrent requests.

Requires `pip install pyjwt`.

```python
# src/lib/auth.py
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from fluidkit import hooks, form, command, query, error, redirect, get_request_event, preserve


# ── Constants ────────────────────────────────────────────────────────────────

SECRET_KEY             = "change-this-in-production"
ACCESS_EXPIRE_SECONDS  = 15 * 60         # 15 minutes
REFRESH_EXPIRE_SECONDS = 7 * 24 * 3600  # 7 days
GRACE_SECONDS          = 5              # concurrent request window


# ── Simulated database ───────────────────────────────────────────────────────
# Replace with real database calls in production.
# preserve() keeps these alive across HMR reloads in dev.

class _UserDB:
    """Simulates a users table."""
    def __init__(self):
        self._users = {
            "alice": "password123",
            "bob":   "hunter2",
        }

    def verify(self, username: str, password: str) -> bool:
        return self._users.get(username) == password


class _SessionDB:
    """
    Simulates a refresh_tokens table.

    Schema per row:
        user_id        : str
        expires_at     : float   (unix timestamp)
        prev_token     : str | None
        prev_expires_at: float | None  (grace window end)
    """
    def __init__(self):
        self._store: dict[str, dict] = {}

    def get(self, token: str) -> dict | None:
        return self._store.get(token)

    def create(self, user_id: str, prev_token: str | None = None) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        self._store[token] = {
            "user_id":         user_id,
            "expires_at":      (now + timedelta(seconds=REFRESH_EXPIRE_SECONDS)).timestamp(),
            "prev_token":      prev_token,
            "prev_expires_at": (now + timedelta(seconds=GRACE_SECONDS)).timestamp() if prev_token else None,
        }
        return token

    def delete(self, token: str) -> None:
        self._store.pop(token, None)

    def find_by_prev_token(self, token: str) -> dict | None:
        """
        Find a session that lists this token as prev_token and is still
        within the grace window. Used to authenticate concurrent requests
        that arrived with the just-rotated old token.
        """
        now = datetime.now(timezone.utc).timestamp()
        for entry in self._store.values():
            prev_valid = (entry.get("prev_expires_at") or 0) > now
            if entry.get("prev_token") == token and prev_valid:
                return entry
        return None


user_db    = preserve(lambda: _UserDB())
session_db = preserve(lambda: _SessionDB())


# ── Token helpers ─────────────────────────────────────────────────────────────

def _create_access_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ACCESS_EXPIRE_SECONDS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _set_auth_cookies(event, access_token: str, refresh_token: str) -> None:
    event.cookies.set("access_token",  access_token,  httponly=True, path="/", samesite="lax")
    event.cookies.set("refresh_token", refresh_token, httponly=True, path="/", samesite="lax", max_age=REFRESH_EXPIRE_SECONDS)


def _clear_auth_cookies(event) -> None:
    event.cookies.set("access_token",  "", httponly=True, path="/", max_age=0)
    event.cookies.set("refresh_token", "", httponly=True, path="/", max_age=0)


# ── Auth hook ─────────────────────────────────────────────────────────────────

@hooks.handle
async def auth(event, resolve):
    """
    Runs before every remote function call.

    On valid access token   → set event.locals["user"], continue.
    On expired access token → attempt refresh rotation, continue.
    On valid refresh token  → issue new token pair, set event.locals["user"], continue.
    On grace period match   → authenticate without re-rotating, continue.
    On theft detection      → clear cookies, continue unauthenticated.
    No tokens present       → continue unauthenticated.

    Never blocks. Individual functions decide whether to require auth
    by checking event.locals.get("user").
    """
    access_token  = event.cookies.get("access_token")
    refresh_token = event.cookies.get("refresh_token")

    # 1. Validate access token — stateless, no DB lookup
    if access_token:
        try:
            payload = jwt.decode(access_token, SECRET_KEY, algorithms=["HS256"])
            event.locals["user"] = payload["user_id"]
            return await resolve(event)
        except jwt.ExpiredSignatureError:
            pass  # fall through to refresh rotation
        except jwt.InvalidTokenError:
            pass  # malformed — fall through unauthenticated

    # 2. Attempt refresh token rotation
    if refresh_token:
        now   = datetime.now(timezone.utc).timestamp()
        entry = session_db.get(refresh_token)

        if entry is None:
            # Token not in DB — check grace window.
            # Covers concurrent requests sent before a rotation completed:
            # request A already rotated this token, request B arrives with
            # the old one within the grace window. Authenticate B using the
            # session that A created, without issuing new tokens.
            grace = session_db.find_by_prev_token(refresh_token)
            if grace is None:
                # Unknown token outside grace — potential theft. Clear session.
                _clear_auth_cookies(event)
                return await resolve(event)
            event.locals["user"] = grace["user_id"]
            return await resolve(event)

        if entry["expires_at"] < now:
            # Refresh token expired — session ended through inactivity
            session_db.delete(refresh_token)
            _clear_auth_cookies(event)
            redirect(303, "/login")

        # Valid refresh token — rotate both.
        # Delete old entry first. New entry stores prev_token for grace window.
        user_id = entry["user_id"]
        session_db.delete(refresh_token)

        new_access  = _create_access_token(user_id)
        new_refresh = session_db.create(user_id, prev_token=refresh_token)

        _set_auth_cookies(event, new_access, new_refresh)
        event.locals["user"] = user_id

    # No tokens, expired session, or unauthenticated — continue.
    # event.locals["user"] is not set.
    return await resolve(event)


# ── Auth functions ────────────────────────────────────────────────────────────

@form
async def login(username: str, _password: str) -> None:
    if not user_db.verify(username, _password):
        error(401, "Invalid credentials")

    access  = _create_access_token(username)
    refresh = session_db.create(username)

    event = get_request_event()
    _set_auth_cookies(event, access, refresh)
    redirect(303, "/dashboard")


@command
async def logout() -> None:
    event = get_request_event()
    refresh_token = event.cookies.get("refresh_token")
    if refresh_token:
        session_db.delete(refresh_token)
    _clear_auth_cookies(event)


# ── Protected functions ───────────────────────────────────────────────────────

@query
async def get_current_user() -> dict | None:
    event = get_request_event()
    user_id = event.locals.get("user")
    if not user_id:
        return None
    return {"user_id": user_id}


@query
async def get_dashboard_data() -> dict:
    event = get_request_event()
    user_id = event.locals.get("user")
    if not user_id:
        error(401, "Unauthorized")
    return {"user_id": user_id, "data": "..."}
```

```svelte
<!-- src/routes/login/+page.svelte -->
<script>
  import { login } from '$lib/auth.remote';
</script>

<form {...login}>
  <input {...login.fields.username.as('text')} placeholder="Username" />
  <input {...login.fields._password.as('password')} placeholder="Password" />
  <button>Log in</button>
</form>
```

```svelte
<!-- src/routes/dashboard/+page.svelte -->
<script>
  import { get_dashboard_data, logout } from '$lib/auth.remote';
</script>

{#await get_dashboard_data()}
  <p>Loading...</p>
{:then data}
  <p>Welcome, {data.user_id}</p>
  <button onclick={async () => await logout()}>Log out</button>
{/await}
```

**How it works:**

`@hooks.handle` runs before every remote function call. It validates the access token first — a stateless JWT decode with no database lookup. If valid, `event.locals["user"]` is set and the request continues immediately.

If the access token is expired, the hook falls through to refresh rotation. The old token is deleted, a new access/refresh pair is created, both are set as `httpOnly` cookies, and `event.locals["user"]` is set for this request. The next request from the browser carries the new access token and skips the DB lookup entirely.

If neither token is present or both are invalid, `resolve(event)` is called without setting `event.locals["user"]`. Public functions like `login` work normally. Protected functions check `event.locals.get("user")` themselves and call `error(401)` if absent. For details on how cookie writes from hooks reach the browser correctly on every request type, see [Hooks — Generated src/hooks.server.ts](hooks.md#generated-srchooksserverts).

**Grace period for concurrent requests:** A page may fire several queries simultaneously, all carrying the same just-expired access token. When the first request rotates the tokens, subsequent requests arrive carrying the old refresh token. The new session entry stores the old token as `prev_token` with a short expiry (5 seconds). `find_by_prev_token` matches these and authenticates them without re-rotating. Outside that window, an unknown token is treated as a potential compromise and the session is cleared.

**Session lifetime:** Each successful rotation resets the refresh token expiry. Sessions stay alive through activity and expire after 7 days of inactivity.

**Production checklist:**
- Replace `_UserDB` with a real database lookup and proper password hashing (`bcrypt`, `argon2`)
- Replace `_SessionDB` with a database table or Redis store
- Set `SECRET_KEY` from an environment variable
- Add `secure=True` to cookie options when running over HTTPS
- Consider reducing `GRACE_SECONDS` to 3 if your infrastructure is fast
