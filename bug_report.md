# Bug Report

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L86)
**The bug**: Grace window allowed bookings that started up to 5 minutes in the past to be created, violating the rule that `start_time` must be strictly in the future. This could let users create bookings that overlap or start immediately, breaking scheduling guarantees.
**How you fixed it**: Removed the 5-minute grace allowance and changed the check to require `start > now` (implemented as `if start <= now:` raising `INVALID_BOOKING_WINDOW`).

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L93)
**The bug**: Duration validation only checked the maximum bound and didn't prevent negative or zero durations (when `end <= start`) or fractional-hour durations. This allowed invalid bookings and inconsistent pricing.
**How you fixed it**: Enforced that the duration is a whole number of hours and added a minimum check so `MIN_DURATION_HOURS <= duration_hours <= MAX_DURATION_HOURS`; raised `INVALID_BOOKING_WINDOW` on violation.

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L50)
**The bug**: Overlap detection used `<=` comparisons which treated back-to-back bookings as conflicts. That incorrectly rejected valid adjacent bookings.
**How you fixed it**: Updated overlap logic to use strict `<` comparisons: overlap iff `existing.start < new.end and new.start < existing.end`, allowing back-to-back bookings.

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L97,app/routers/bookings.py#L104)
**The bug**: Race conditions during booking creation allowed two concurrent requests to read no-conflict and write conflicting bookings or exceed user quota.
**How you fixed it**: Locked critical rows during the transaction by selecting the `Room` with `.with_for_update()` and locking the `User` row before quota checks (`.with_for_update()`), preventing concurrent transactions from observing stale state.

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L130)
**The bug**: Pagination and ordering were incorrect: results were sorted descending, offset calculation skipped the first page, and the limit was hardcoded to 10. This produced missing or misordered pages.
**How you fixed it**: Changed to `order_by(Booking.start_time.asc(), Booking.id.asc())`, `.offset((page - 1) * limit)`, and `.limit(limit)` so pages are sequential and size-respecting.

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L174)
**The bug**: `get_booking` response mistakenly overwrote the real booking `start_time` with the `created_at` timestamp in the serialized response, breaking the API contract and confusing clients.
**How you fixed it**: Removed the erroneous assignment so `start_time` in the response reflects the actual booking `start_time`.

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L176)
**The bug**: Members could read other members' bookings because there was no ownership check; only room/org ownership was enforced.
**How you fixed it**: Added an authorization check: if `user.role != "admin" and booking.user_id != user.id`, return 404 (BOOKING_NOT_FOUND), so members access only their bookings while admins can access any booking in the org.

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L200)
**The bug**: Concurrent cancellation requests could both pass the `status != "cancelled"` check and cause double refunds; the booking row was not locked during cancellation.
**How you fixed it**: Selected the booking using `.with_for_update()` in `cancel_booking` to lock the row for the duration of the cancellation transaction, preventing concurrent double-refunds.

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L206)
**The bug**: Refund thresholds and rounding were incorrect: the `> 48` check excluded exactly 48-hour notices from full refunds, the under-24-hour branch incorrectly returned 50%, and `round()` (banker's rounding) could round half-cents down unexpectedly.
**How you fixed it**: Corrected thresholds to `if notice >= 48h -> 100%`, `elif notice >= 24h -> 50%`, `else -> 0%`. Replaced `round()` with `Decimal` arithmetic and `quantize(..., ROUND_HALF_UP)` to ensure half-cents round up.

---

**File and line number(s)**: [app/routers/bookings.py](app/routers/bookings.py#L3)
**The bug**: Rounding change required a decimal import but it wasn't present.
**How you fixed it**: Added `from decimal import Decimal, ROUND_HALF_UP` at the top of the file and used `Decimal` for refund calculations.

---

**File and line number(s)**: [app/routers/admin.py](app/routers/admin.py#L1-L60)
**What the bug was** (A - Multi-tenancy export): The `/admin/export` endpoint accepted a `room_id` but did not verify the room belonged to the requesting admin's organization, allowing an admin from one org to export another org's room data.
**How you fixed it**: Added an explicit ownership check when `room_id` is provided; if the room isn't found in the admin's org, return 404.

---

**File and line number(s)**: [app/routers/admin.py](app/routers/admin.py#L10-L40)
**What the bug was** (C - Stale caching): `usage_report` read from and wrote to a cache, but booking creation didn't invalidate the cache, so reports could be stale.
**How you fixed it**: Removed the cache read/write for `usage_report` so the endpoint always queries the live database and reflects current state immediately.

---

**File and line number(s)**: [app/routers/auth.py](app/routers/auth.py#L20-L46)
**What the bug was** (A - Duplicate username bypass): `register` returned the existing user's details when a username already existed, silently allowing duplicate registration attempts and returning 200 instead of signalling an error.
**How you fixed it**: Changed behavior to raise `AppError(409, "USERNAME_TAKEN", "Username already taken")` when a duplicate username is detected.

---

**File and line number(s)**: [app/routers/auth.py](app/routers/auth.py#L48-L68)
**What the bug was** (B - Refresh token reuse): `/auth/refresh` issued new tokens but did not invalidate the presented refresh token, allowing infinite reuse.
**How you fixed it**: Revoke the presented refresh token's payload (`revoke_access_token(data)`) before issuing new tokens so refresh tokens are single-use.

---

**File and line number(s)**: [app/routers/rooms.py](app/routers/rooms.py#L1-L12)
**What the bug was** (A - Timezone TypeError): In `/rooms/{room_id}/availability`, `day_start` and `day_end` were naive datetimes; comparing to timezone-aware `Booking.start_time` could raise `TypeError`.
**How you fixed it**: Imported `timezone` and made `day_start` timezone-aware using `.replace(tzinfo=timezone.utc)` before computing `day_end`.

---

**File and line number(s)**: [app/timeutils.py](app/timeutils.py#L1-L40)
**What the bug was** (Timezone conversion): `parse_input_datetime` stripped timezone offsets by calling `dt.replace(tzinfo=None)` on offset-aware inputs, which discarded the offset instead of converting to UTC. This caused offset datetimes (e.g. `2026-07-09T20:00:00+06:00`) to be stored incorrectly as if they were already UTC.
**How you fixed it**: Converted offset-aware inputs to UTC using `dt = dt.astimezone(timezone.utc).replace(tzinfo=None)` so stored datetimes are naive UTC but correctly normalized.

---

**File and line number(s)**: [app/auth.py](app/auth.py#L1-L120)
**What the bug was** (Token revocation mismatch): `get_token_payload` checked `payload.get("sub")` against `_revoked_tokens`, but revoked tokens are recorded by token id (`jti`). Because it compared the wrong field, revoked tokens (from logout or refresh) were not rejected.
**How you fixed it**: Changed the check to `if payload.get("jti") in _revoked_tokens:` so tokens revoked by `revoke_access_token(payload)` are properly rejected.

---

**File and line number(s)**: [app/services/export.py](app/services/export.py#L1-L120)
**What the bug was** (Multi-tenancy export leak): `generate_export` previously called `fetch_bookings_raw(db, room_id)` when `include_all=True` and a `room_id` was supplied; `fetch_bookings_raw` didn't check `Room.org_id`, so an admin could export another org's room data.
**How you fixed it**: Removed the unsafe path and always use `_fetch_scoped(db, org_id, ..., room_id)` so exports remain scoped to the requesting organization even when `include_all=True`.

---

**File and line number(s)**: [app/services/notifications.py](app/services/notifications.py#L1-L40)
**What the bug was** (Deadlock): `notify_created` acquired `_email_lock` then `_audit_lock`, while `notify_cancelled` acquired them in reverse order; concurrent create+cancel could deadlock.
**How you fixed it**: Made `notify_cancelled` acquire locks in the same order as `notify_created` (first `_email_lock`, then `_audit_lock`) to guarantee a consistent lock ordering and prevent deadlocks.

---

**File and line number(s)**: [app/services/ratelimit.py](app/services/ratelimit.py#L1-L80)
**What the bug was** (Rate limiter race): The rate limiter performed a read-modify-write cycle on an in-memory per-user bucket without synchronization; concurrent requests could interleave and bypass the request limit.
**How you fixed it**: Added a `threading.Lock()` and wrapped the bucket update logic inside `with _lock:` so the read/trim/append/write is atomic per user and the rate limit holds under concurrent requests.

---

**File and line number(s)**: [app/services/reference.py](app/services/reference.py#L1-L40)
**What the bug was** (Duplicate reference codes): `next_reference_code` read and incremented a shared counter without synchronization, producing duplicate reference codes under concurrent creation.
**How you fixed it**: Introduced a module-level `threading.Lock()` and acquire it while issuing the next code so codes remain unique even under concurrent requests.

---

**File and line number(s)**: [app/services/refunds.py](app/services/refunds.py#L1-L120)
**What the bug was** (Floating-point refund math): `log_refund` used floating-point arithmetic and `int()` truncation to compute cents, which can produce off-by-one-cent discrepancies due to float imprecision.
**How you fixed it**: Switched to `Decimal` arithmetic and `quantize(Decimal('1'), rounding=ROUND_HALF_UP)` to compute cent amounts deterministically and match the rounding used by the cancel endpoint.

---

**File and line number(s)**: [app/services/stats.py](app/services/stats.py#L1-L80)
**What the bug was** (Stats race): `record_create` and `record_cancel` read-modify-wrote the shared `_stats` map without synchronization, allowing concurrent updates to clobber each other and drift from the actual DB state.
**How you fixed it**: Added a `threading.Lock()` and wrapped updates and reads in `with _lock:` to ensure atomic updates and correct live stats under concurrency.
