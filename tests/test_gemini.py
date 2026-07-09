import concurrent.futures
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def _time(offset_hours: int) -> str:
    """Helper to generate ISO UTC datetimes."""
    return (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).replace(
        minute=0, second=0, microsecond=0
    ).isoformat()

def setup_user(org_name, username):
    """Helper to register and login a user, returning auth headers."""
    client.post("/auth/register", json={"org_name": org_name, "username": username, "password": "pw"})
    res = client.post("/auth/login", json={"org_name": org_name, "username": username, "password": "pw"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}, res.json()["refresh_token"]

def test_auth_and_multitenancy():
    # 1. Duplicate Username (Rule 15)
    client.post("/auth/register", json={"org_name": "org1", "username": "user1", "password": "pw"})
    res = client.post("/auth/register", json={"org_name": "org1", "username": "user1", "password": "pw"})
    assert res.status_code == 409, "Duplicate username should return 409"

    # 2. Multi-tenancy Isolation (Rule 9)
    headers_a, _ = setup_user("org_a", "admin_a")
    headers_b, _ = setup_user("org_b", "admin_b")

    room_a = client.post("/rooms", json={"name": "Room A", "capacity": 4, "hourly_rate_cents": 1000}, headers=headers_a)
    room_id = room_a.json()["id"]

    # Admin B tries to fetch Admin A's room
    res = client.get(f"/rooms/{room_id}/availability?date={_time(24)[:10]}", headers=headers_b)
    assert res.status_code == 404, "Cross-org room access should return 404"

    # 3. Token Revocation & Refresh (Rule 8)
    _, refresh_token = setup_user("org_c", "user_c")
    
    # Use refresh token once (should succeed)
    res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    
    # Use SAME refresh token again (should fail because it's single-use)
    res2 = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert res2.status_code == 401, "Refresh tokens must be single-use"

def test_booking_rules_and_refunds():
    headers, _ = setup_user("org_math", "admin_math")
    room_res = client.post("/rooms", json={"name": "Math Room", "capacity": 4, "hourly_rate_cents": 999}, headers=headers)
    room_id = room_res.json()["id"]

    # 1. Grace Window (Rule 2) - Past booking
    res = client.post("/bookings", json={"room_id": room_id, "start_time": _time(-1), "end_time": _time(1)}, headers=headers)
    assert res.status_code == 400, "Past bookings should be rejected"

    # 2. Overlap (Rule 3)
    b1 = client.post("/bookings", json={"room_id": room_id, "start_time": _time(10), "end_time": _time(12)}, headers=headers)
    assert b1.status_code == 201
    
    # Back-to-back should succeed
    b2 = client.post("/bookings", json={"room_id": room_id, "start_time": _time(12), "end_time": _time(14)}, headers=headers)
    assert b2.status_code == 201
    
    # Overlap should fail
    b3 = client.post("/bookings", json={"room_id": room_id, "start_time": _time(11), "end_time": _time(13)}, headers=headers)
    assert b3.status_code == 409, "Overlapping bookings should return 409"

    # 3. Refund Math (Rule 6) - 999 cents * 2 hours = 1998 cents
    # Cancel > 48 hours (100%)
    b_100 = client.post("/bookings", json={"room_id": room_id, "start_time": _time(50), "end_time": _time(52)}, headers=headers)
    cancel_100 = client.post(f"/bookings/{b_100.json()['id']}/cancel", headers=headers)
    assert cancel_100.json()["refund_amount_cents"] == 1998

    # Cancel 24-48 hours (50% of 1998 = 999)
    b_50 = client.post("/bookings", json={"room_id": room_id, "start_time": _time(30), "end_time": _time(32)}, headers=headers)
    cancel_50 = client.post(f"/bookings/{b_50.json()['id']}/cancel", headers=headers)
    assert cancel_50.json()["refund_amount_cents"] == 999, "Banker's rounding failed for 50% refund"

def test_concurrency():
    headers, _ = setup_user("org_concurrent", "admin_concurrent")
    room_res = client.post("/rooms", json={"name": "Race Room", "capacity": 4, "hourly_rate_cents": 1000}, headers=headers)
    room_id = room_res.json()["id"]

    # 1. Double Booking Race Condition (Rule 3)
    # We will send 5 exact same booking requests at the exact same time.
    payload = {"room_id": room_id, "start_time": _time(100), "end_time": _time(102)}
    
    def make_booking():
        return client.post("/bookings", json=payload, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: make_booking(), range(5)))

    successes = [r for r in results if r.status_code == 201]
    conflicts = [r for r in results if r.status_code == 409]

    assert len(successes) == 1, f"Concurrency bug! {len(successes)} bookings succeeded for the same slot."
    assert len(conflicts) == 4, "The other 4 concurrent requests should have failed with 409 ROOM_CONFLICT"

    # 2. Stats Race Condition (Rule 14)
    stats = client.get(f"/rooms/{room_id}/stats", headers=headers).json()
    assert stats["total_confirmed_bookings"] == 1, "Stats count drifted due to race condition"
    assert stats["total_revenue_cents"] == 2000, "Stats revenue drifted due to race condition"