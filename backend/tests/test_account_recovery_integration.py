"""PLAT-04: password change, one-time reset, second factor, device sessions.

Mostly adversarial, because the happy paths are short and these routes are how
an account gets taken over: expired, reused and wrong-user credentials all have
to fail, and fail the same way to a stranger.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import AuditLog, PasswordResetCode, RecoveryCode, User, UserSecurity
from app.services import totp
from app.services.rate_limit import user_rate_limiter
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "Original-Password-1234"
NEW_PASSWORD = "Replacement-Password-5678"


@pytest.fixture(autouse=True)
async def _clean_limiter():
    await user_rate_limiter.clear()
    yield
    await user_rate_limiter.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _new_account(role: str = "citizen", password: str = PASSWORD) -> dict:
    email = unique_email(f"account-{role}")
    body = await provision_test_user(name="Account Holder", email=email, password=password, role=role)
    return {"email": email, "id": body["user"]["id"], "token": body["access_token"], "password": password}


async def _login(client: AsyncClient, email: str, password: str, **extra) -> tuple[int, dict]:
    response = await client.post("/auth/login", json={"email": email, "password": password, **extra})
    return response.status_code, response.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _enable_mfa(client: AsyncClient, account: dict) -> tuple[str, list[str]]:
    enrolled = await client.post(
        "/account/mfa/enroll", json={"password": account["password"]}, headers=_bearer(account["token"])
    )
    assert enrolled.status_code == 200, enrolled.text
    secret = enrolled.json()["secret"]
    confirmed = await client.post(
        "/account/mfa/confirm",
        json={"code": totp.code_at_step(secret, totp.current_step())},
        headers=_bearer(account["token"]),
    )
    assert confirmed.status_code == 200, confirmed.text
    return secret, confirmed.json()["codes"]


# ------------------------------------------------------------ changing a password


async def test_changing_a_password_requires_the_current_one() -> None:
    account = await _new_account()
    async with _client() as client:
        refused = await client.post(
            "/account/password",
            json={"current_password": "Not-The-Password-000", "new_password": NEW_PASSWORD},
            headers=_bearer(account["token"]),
        )
        assert refused.status_code == 403
        status, _ = await _login(client, account["email"], PASSWORD)
        assert status == 200


async def test_the_new_password_may_not_be_the_old_one_or_too_short() -> None:
    account = await _new_account()
    async with _client() as client:
        same = await client.post(
            "/account/password",
            json={"current_password": PASSWORD, "new_password": PASSWORD},
            headers=_bearer(account["token"]),
        )
        assert same.status_code == 422
        short = await client.post(
            "/account/password",
            json={"current_password": PASSWORD, "new_password": "short"},
            headers=_bearer(account["token"]),
        )
        assert short.status_code == 422


async def test_changing_a_password_ends_other_devices_and_keeps_this_one() -> None:
    account = await _new_account()
    async with _client() as client:
        _, laptop = await _login(client, account["email"], PASSWORD)
        _, phone = await _login(client, account["email"], PASSWORD)

        changed = await client.post(
            "/account/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=_bearer(laptop["access_token"]),
        )
        assert changed.status_code == 200, changed.text
        new_tokens = changed.json()

        assert (await client.get("/auth/me", headers=_bearer(phone["access_token"]))).status_code == 401
        assert (await client.post("/auth/refresh", json={"refresh_token": phone["refresh_token"]})).status_code == 401
        assert (await client.get("/auth/me", headers=_bearer(new_tokens["access_token"]))).status_code == 200

        old_status, _ = await _login(client, account["email"], PASSWORD)
        new_status, _ = await _login(client, account["email"], NEW_PASSWORD)
        assert (old_status, new_status) == (401, 200)


async def test_a_browser_session_gets_cookies_and_no_token_in_the_body() -> None:
    account = await _new_account()
    async with _client() as client:
        signed_in = await client.post(
            "/auth/cookie/login", json={"email": account["email"], "password": PASSWORD}, headers={"Origin": "http://test"}
        )
        assert signed_in.status_code == 200
        changed = await client.post(
            "/account/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers={"Origin": "http://test"},
        )
        assert changed.status_code == 200, changed.text
        assert "access_token" not in changed.json()
        assert (await client.get("/auth/me")).status_code == 200


async def test_step_up_guesses_are_throttled() -> None:
    account = await _new_account()
    async with _client() as client:
        statuses = [
            (
                await client.post(
                    "/account/password",
                    json={"current_password": f"Wrong-Guess-Number-{index}", "new_password": NEW_PASSWORD},
                    headers=_bearer(account["token"]),
                )
            ).status_code
            for index in range(7)
        ]
    assert statuses[:5] == [403] * 5
    assert statuses[5] == 429


# ------------------------------------------------------------- one-time reset codes


async def _issue(client: AsyncClient, admin: dict, email: str, **extra):
    return await client.post(
        "/account/admin/reset-code", json={"email": email, **extra}, headers=_bearer(admin["token"])
    )


async def _redeem(client: AsyncClient, email: str, code: str, password: str = NEW_PASSWORD):
    return await client.post(
        "/account/password-reset/redeem", json={"email": email, "code": code, "new_password": password}
    )


async def test_an_administrator_issued_code_resets_the_password_once() -> None:
    admin, target = await _new_account("admin"), await _new_account("police")
    async with _client() as client:
        issued = await _issue(client, admin, target["email"])
        assert issued.status_code == 200, issued.text
        code = issued.json()["code"]

        assert (await _redeem(client, target["email"], code)).status_code == 204
        old_status, _ = await _login(client, target["email"], PASSWORD)
        new_status, _ = await _login(client, target["email"], NEW_PASSWORD)
        assert (old_status, new_status) == (401, 200)

        # A second use changes nothing.
        reused = await _redeem(client, target["email"], code, "Attacker-Chosen-Password-9")
        assert reused.status_code == 400
        status, _ = await _login(client, target["email"], NEW_PASSWORD)
        assert status == 200


async def test_the_code_itself_is_never_stored() -> None:
    admin, target = await _new_account("admin"), await _new_account()
    async with _client() as client:
        code = (await _issue(client, admin, target["email"])).json()["code"]
    async with AsyncSessionLocal() as session:
        rows = (
            await session.scalars(
                select(PasswordResetCode).where(PasswordResetCode.user_id == uuid.UUID(target["id"]))
            )
        ).all()
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.action == "admin.reset_code_issued"))
        ).all()
    assert rows and all(code not in row.code_hash and row.code_hash != code for row in rows)
    assert all(code not in str(row.metadata_) for row in audit)


async def test_an_expired_code_does_not_work() -> None:
    admin, target = await _new_account("admin"), await _new_account()
    async with _client() as client:
        code = (await _issue(client, admin, target["email"])).json()["code"]
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(PasswordResetCode)
                .where(PasswordResetCode.user_id == uuid.UUID(target["id"]))
                .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
            await session.commit()
        assert (await _redeem(client, target["email"], code)).status_code == 400
        status, _ = await _login(client, target["email"], PASSWORD)
        assert status == 200


async def test_a_code_for_one_account_does_nothing_for_another() -> None:
    admin, target, victim = await _new_account("admin"), await _new_account(), await _new_account()
    async with _client() as client:
        code = (await _issue(client, admin, target["email"])).json()["code"]
        assert (await _redeem(client, victim["email"], code)).status_code == 400
        status, _ = await _login(client, victim["email"], PASSWORD)
        assert status == 200
        # And the attempt did not burn it for its rightful holder.
        assert (await _redeem(client, target["email"], code)).status_code == 204


async def test_issuing_a_new_code_kills_the_previous_one() -> None:
    admin, target = await _new_account("admin"), await _new_account()
    async with _client() as client:
        first = (await _issue(client, admin, target["email"])).json()["code"]
        second = (await _issue(client, admin, target["email"])).json()["code"]
        assert (await _redeem(client, target["email"], first)).status_code == 400
        assert (await _redeem(client, target["email"], second)).status_code == 204


async def test_every_refusal_reads_the_same_to_a_stranger() -> None:
    admin, target = await _new_account("admin"), await _new_account()
    async with _client() as client:
        await _issue(client, admin, target["email"])
        wrong_code = await _redeem(client, target["email"], "wrong-code-wrong-code")
        no_such_account = await _redeem(client, unique_email("nobody"), "wrong-code-wrong-code")
    assert wrong_code.status_code == no_such_account.status_code == 400
    assert wrong_code.json() == no_such_account.json()


async def test_a_suspended_account_cannot_be_reset_back_in() -> None:
    admin, target = await _new_account("admin"), await _new_account()
    async with _client() as client:
        code = (await _issue(client, admin, target["email"])).json()["code"]
        async with AsyncSessionLocal() as session:
            await session.execute(update(User).where(User.id == uuid.UUID(target["id"])).values(is_active=False))
            await session.commit()
        assert (await _redeem(client, target["email"], code)).status_code == 400


async def test_only_an_administrator_can_issue_and_never_for_themselves() -> None:
    admin, citizen, officer = await _new_account("admin"), await _new_account(), await _new_account("police")
    async with _client() as client:
        assert (await _issue(client, citizen, officer["email"])).status_code == 403
        assert (await _issue(client, officer, citizen["email"])).status_code == 403
        assert (await _issue(client, admin, admin["email"])).status_code == 409
        assert (await client.post("/account/admin/reset-code", json={"email": citizen["email"]})).status_code == 401


async def test_a_reset_ends_every_session_on_the_account() -> None:
    admin, target = await _new_account("admin"), await _new_account()
    async with _client() as client:
        _, session_tokens = await _login(client, target["email"], PASSWORD)
        code = (await _issue(client, admin, target["email"])).json()["code"]
        assert (await _redeem(client, target["email"], code)).status_code == 204
        assert (await client.get("/auth/me", headers=_bearer(session_tokens["access_token"]))).status_code == 401
        assert (
            await client.post("/auth/refresh", json={"refresh_token": session_tokens["refresh_token"]})
        ).status_code == 401


async def test_a_reset_does_not_remove_the_second_factor_unless_asked() -> None:
    admin, target = await _new_account("admin"), await _new_account("advocate")
    async with _client() as client:
        await _enable_mfa(client, target)
        code = (await _issue(client, admin, target["email"])).json()["code"]
        await _redeem(client, target["email"], code)
        status, body = await _login(client, target["email"], NEW_PASSWORD)
        assert (status, body["detail"]) == (401, "mfa_required")

        cleared = await _issue(client, admin, target["email"], reset_mfa=True)
        assert cleared.json()["mfa_cleared"] is True
        status, _ = await _login(client, target["email"], NEW_PASSWORD)
        assert status == 200


async def test_requesting_by_mail_says_nothing_about_the_address(monkeypatch) -> None:
    sent: list[tuple[str, str]] = []
    from app.services import account_security

    monkeypatch.setattr(account_security, "send_reset_mail", lambda to, code: sent.append((to, code)))
    monkeypatch.setattr(settings, "smtp_host", "mail.example.com")
    monkeypatch.setattr(settings, "smtp_from", "corpusil@example.com")
    target = await _new_account()
    async with _client() as client:
        known = await client.post("/account/password-reset/request", json={"email": target["email"]})
        unknown = await client.post("/account/password-reset/request", json={"email": unique_email("ghost")})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert [to for to, _ in sent] == [target["email"]]
        assert (await _redeem(client, target["email"], sent[0][1])).status_code == 204


async def test_with_no_mail_configured_nothing_is_issued() -> None:
    target = await _new_account()
    assert not settings.self_service_reset_available
    async with _client() as client:
        response = await client.post("/account/password-reset/request", json={"email": target["email"]})
    assert response.status_code == 202
    async with AsyncSessionLocal() as session:
        issued = (
            await session.scalars(
                select(PasswordResetCode).where(PasswordResetCode.user_id == uuid.UUID(target["id"]))
            )
        ).all()
    assert issued == []


# ------------------------------------------------------------------ second factor


async def test_sign_in_needs_the_code_only_after_the_password_is_right() -> None:
    account = await _new_account("police")
    async with _client() as client:
        secret, _ = await _enable_mfa(client, account)
        status, body = await _login(client, account["email"], "Not-The-Password-000")
        assert (status, body["detail"]) == (401, "Invalid email or password")
        status, body = await _login(client, account["email"], PASSWORD)
        assert (status, body["detail"]) == (401, "mfa_required")
        status, body = await _login(client, account["email"], PASSWORD, mfa_code="000000")
        assert (status, body["detail"]) == (401, "mfa_invalid")
        # A later step than the one spent on confirming enrolment.
        code = totp.code_at_step(secret, totp.current_step() + 1)
        status, body = await _login(client, account["email"], PASSWORD, mfa_code=code)
        assert status == 200, body
        assert "access_token" in body


async def test_a_code_cannot_be_replayed() -> None:
    account = await _new_account("police")
    async with _client() as client:
        secret, _ = await _enable_mfa(client, account)
        code = totp.code_at_step(secret, totp.current_step() + 1)
        first, _ = await _login(client, account["email"], PASSWORD, mfa_code=code)
        second, body = await _login(client, account["email"], PASSWORD, mfa_code=code)
    assert first == 200
    assert (second, body["detail"]) == (401, "mfa_invalid")


async def test_another_accounts_code_is_refused() -> None:
    first, second = await _new_account("police"), await _new_account("police")
    async with _client() as client:
        await _enable_mfa(client, first)
        other_secret, _ = await _enable_mfa(client, second)
        code = totp.code_at_step(other_secret, totp.current_step() + 1)
        status, body = await _login(client, first["email"], PASSWORD, mfa_code=code)
    assert (status, body["detail"]) == (401, "mfa_invalid")


async def test_a_recovery_code_works_exactly_once_and_only_for_its_owner() -> None:
    owner, stranger = await _new_account("advocate"), await _new_account("advocate")
    async with _client() as client:
        _, codes = await _enable_mfa(client, owner)
        await _enable_mfa(client, stranger)
        assert len(codes) == 10

        status, _ = await _login(client, stranger["email"], PASSWORD, recovery_code=codes[0])
        assert status == 401

        status, _ = await _login(client, owner["email"], PASSWORD, recovery_code=codes[0])
        assert status == 200
        status, body = await _login(client, owner["email"], PASSWORD, recovery_code=codes[0])
        assert (status, body["detail"]) == (401, "mfa_invalid")

        account_status = await client.get("/account/status", headers=_bearer(owner["token"]))
        assert account_status.json()["recovery_codes_remaining"] == 9


async def test_an_unfinished_enrolment_does_not_lock_anyone_out() -> None:
    account = await _new_account("police")
    async with _client() as client:
        enrolled = await client.post(
            "/account/mfa/enroll", json={"password": PASSWORD}, headers=_bearer(account["token"])
        )
        assert enrolled.status_code == 200
        wrong = await client.post(
            "/account/mfa/confirm", json={"code": "000000"}, headers=_bearer(account["token"])
        )
        assert wrong.status_code == 422
        status, _ = await _login(client, account["email"], PASSWORD)
        assert status == 200


async def test_enrolling_needs_the_password_and_cannot_overwrite_a_live_secret() -> None:
    account = await _new_account("police")
    async with _client() as client:
        refused = await client.post(
            "/account/mfa/enroll", json={"password": "Not-The-Password-000"}, headers=_bearer(account["token"])
        )
        assert refused.status_code == 403
        await _enable_mfa(client, account)
        again = await client.post(
            "/account/mfa/enroll", json={"password": PASSWORD}, headers=_bearer(account["token"])
        )
        assert again.status_code == 409


async def test_secrets_are_not_stored_in_the_clear() -> None:
    account = await _new_account("police")
    async with _client() as client:
        secret, codes = await _enable_mfa(client, account)
    user_id = uuid.UUID(account["id"])
    async with AsyncSessionLocal() as session:
        row = await session.get(UserSecurity, user_id)
        stored = (await session.scalars(select(RecoveryCode).where(RecoveryCode.user_id == user_id))).all()
        audit = (await session.scalars(select(AuditLog).where(AuditLog.user_id == user_id))).all()
    assert secret not in (row.totp_secret_encrypted or "")
    assert totp.decrypt_secret(row.totp_secret_encrypted or "") == secret
    hashes = {item.code_hash for item in stored}
    assert not hashes & set(codes)
    assert {totp.hash_one_time_value(code) for code in codes} == hashes
    assert not any(secret in str(item.metadata_) for item in audit)


async def test_turning_it_off_needs_password_and_a_factor() -> None:
    account = await _new_account("police")
    async with _client() as client:
        secret, _ = await _enable_mfa(client, account)
        headers = _bearer(account["token"])
        no_factor = await client.post("/account/mfa/disable", json={"password": PASSWORD}, headers=headers)
        assert no_factor.status_code == 403
        wrong_password = await client.post(
            "/account/mfa/disable",
            json={"password": "Not-The-Password-000", "mfa_code": totp.code_at_step(secret, totp.current_step() + 1)},
            headers=headers,
        )
        assert wrong_password.status_code == 403
        done = await client.post(
            "/account/mfa/disable",
            json={"password": PASSWORD, "mfa_code": totp.code_at_step(secret, totp.current_step() + 1)},
            headers=headers,
        )
        assert done.status_code == 204
        status, _ = await _login(client, account["email"], PASSWORD)
        assert status == 200


async def test_replacing_recovery_codes_kills_the_old_set() -> None:
    account = await _new_account("police")
    async with _client() as client:
        secret, old = await _enable_mfa(client, account)
        replaced = await client.post(
            "/account/mfa/recovery-codes",
            json={"password": PASSWORD, "mfa_code": totp.code_at_step(secret, totp.current_step() + 1)},
            headers=_bearer(account["token"]),
        )
        assert replaced.status_code == 200, replaced.text
        new = replaced.json()["codes"]
        assert not set(new) & set(old)
        status, _ = await _login(client, account["email"], PASSWORD, recovery_code=old[0])
        assert status == 401
        status, _ = await _login(client, account["email"], PASSWORD, recovery_code=new[0])
        assert status == 200


# ---------------------------------------------------------------- device sessions


async def test_the_device_list_shows_only_mine_and_marks_this_one() -> None:
    account, other = await _new_account(), await _new_account()
    async with _client() as client:
        _, first = await _login(client, account["email"], PASSWORD)
        _, second = await _login(client, account["email"], PASSWORD)
        await _login(client, other["email"], PASSWORD)
        listed = await client.get(
            "/account/sessions",
            headers={**_bearer(second["access_token"]), "User-Agent": "irrelevant"},
        )
    items = listed.json()["items"]
    assert len(items) == 2
    assert sum(item["current"] for item in items) == 1


async def test_revoking_a_device_takes_effect_at_once() -> None:
    account = await _new_account()
    async with _client() as client:
        _, laptop = await _login(client, account["email"], PASSWORD)
        _, phone = await _login(client, account["email"], PASSWORD)
        assert (await client.get("/auth/me", headers=_bearer(phone["access_token"]))).status_code == 200

        items = (await client.get("/account/sessions", headers=_bearer(laptop["access_token"]))).json()["items"]
        phone_id = next(item["id"] for item in items if not item["current"])
        revoked = await client.delete(f"/account/sessions/{phone_id}", headers=_bearer(laptop["access_token"]))
        assert revoked.status_code == 204

        assert (await client.get("/auth/me", headers=_bearer(phone["access_token"]))).status_code == 401
        assert (await client.post("/auth/refresh", json={"refresh_token": phone["refresh_token"]})).status_code == 401
        assert (await client.get("/auth/me", headers=_bearer(laptop["access_token"]))).status_code == 200


async def test_someone_elses_session_cannot_be_revoked_or_probed() -> None:
    account, attacker = await _new_account(), await _new_account()
    async with _client() as client:
        _, victim = await _login(client, account["email"], PASSWORD)
        _, intruder = await _login(client, attacker["email"], PASSWORD)
        victim_id = (await client.get("/account/sessions", headers=_bearer(victim["access_token"]))).json()["items"][0]["id"]

        attempt = await client.delete(f"/account/sessions/{victim_id}", headers=_bearer(intruder["access_token"]))
        made_up = await client.delete(f"/account/sessions/{uuid.uuid4()}", headers=_bearer(intruder["access_token"]))
        assert attempt.status_code == made_up.status_code == 404
        assert attempt.json() == made_up.json()
        assert (await client.get("/auth/me", headers=_bearer(victim["access_token"]))).status_code == 200


async def test_revoking_the_others_keeps_this_one() -> None:
    account = await _new_account()
    async with _client() as client:
        _, keep = await _login(client, account["email"], PASSWORD)
        _, other = await _login(client, account["email"], PASSWORD)
        result = await client.post("/account/sessions/revoke-others", headers=_bearer(keep["access_token"]))
        assert result.json()["revoked"] == 1
        assert (await client.get("/auth/me", headers=_bearer(keep["access_token"]))).status_code == 200
        assert (await client.get("/auth/me", headers=_bearer(other["access_token"]))).status_code == 401


async def test_signing_out_removes_the_device_from_the_list() -> None:
    account = await _new_account()
    async with _client() as browser, _client() as other:
        await browser.post("/auth/cookie/login", json={"email": account["email"], "password": PASSWORD}, headers={"Origin": "http://test"})
        _, watcher = await _login(other, account["email"], PASSWORD)
        before = (await other.get("/account/sessions", headers=_bearer(watcher["access_token"]))).json()["items"]
        assert len(before) == 2
        await browser.post("/auth/cookie/logout", headers={"Origin": "http://test"})
        after = (await other.get("/account/sessions", headers=_bearer(watcher["access_token"]))).json()["items"]
        assert len(after) == 1


async def test_only_a_label_is_kept_about_a_device() -> None:
    columns = (
        await _scalars_text(
            "select column_name from information_schema.columns where table_name='user_sessions'"
        )
    )
    assert not {"ip", "ip_address", "user_agent"} & set(columns)


async def _scalars_text(statement: str) -> list[str]:
    async with AsyncSessionLocal() as session:
        return list((await session.scalars(text(statement))).all())


# ----------------------------------------------------- the refresh grace window


async def test_a_second_tab_refreshing_inside_the_window_does_not_end_the_session() -> None:
    account = await _new_account()
    async with _client() as tab:
        await tab.post("/auth/cookie/login", json={"email": account["email"], "password": PASSWORD}, headers={"Origin": "http://test"})
        stale_refresh = tab.cookies.get("legal_rag_refresh")
        first = await tab.post("/auth/cookie/refresh", headers={"Origin": "http://test"})
        assert first.status_code == 200

        async with _client() as other_tab:
            other_tab.cookies.set("legal_rag_refresh", stale_refresh, path="/auth/cookie")
            late = await other_tab.post("/auth/cookie/refresh", headers={"Origin": "http://test"})
        assert late.status_code == 409
        assert "set-cookie" not in late.headers
        assert (await tab.get("/auth/me")).status_code == 200


async def test_the_same_replay_after_the_window_ends_everything() -> None:
    account = await _new_account()
    async with _client() as tab:
        await tab.post("/auth/cookie/login", json={"email": account["email"], "password": PASSWORD}, headers={"Origin": "http://test"})
        stale_refresh = tab.cookies.get("legal_rag_refresh")
        await tab.post("/auth/cookie/refresh", headers={"Origin": "http://test"})
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    "update revoked_refresh_tokens set revoked_at = now() - interval '1 hour' "
                    "where user_id = :user_id"
                ),
                {"user_id": uuid.UUID(account["id"])},
            )
            await session.commit()
        async with _client() as thief:
            thief.cookies.set("legal_rag_refresh", stale_refresh, path="/auth/cookie")
            replay = await thief.post("/auth/cookie/refresh", headers={"Origin": "http://test"})
        assert replay.status_code == 401
        assert (await tab.post("/auth/cookie/refresh", headers={"Origin": "http://test"})).status_code == 401


async def test_a_token_ended_by_sign_out_gets_no_grace() -> None:
    account = await _new_account()
    async with _client() as tab:
        await tab.post("/auth/cookie/login", json={"email": account["email"], "password": PASSWORD}, headers={"Origin": "http://test"})
        stale_refresh = tab.cookies.get("legal_rag_refresh")
        await tab.post("/auth/cookie/logout", headers={"Origin": "http://test"})
        async with _client() as thief:
            thief.cookies.set("legal_rag_refresh", stale_refresh, path="/auth/cookie")
            replay = await thief.post("/auth/cookie/refresh", headers={"Origin": "http://test"})
        assert replay.status_code == 401


async def test_the_grace_cannot_be_requested_on_the_bearer_route() -> None:
    account = await _new_account()
    async with _client() as client:
        _, tokens = await _login(client, account["email"], PASSWORD)
        await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        replay = await client.post(
            "/auth/refresh?reuse_grace_seconds=60", json={"refresh_token": tokens["refresh_token"]}
        )
    assert replay.status_code == 401


# ----------------------------------------------------------- forced password change


async def test_a_forced_change_blocks_the_product_but_not_the_change_itself() -> None:
    account = await _new_account("police")
    async with AsyncSessionLocal() as session:
        session.add(UserSecurity(user_id=uuid.UUID(account["id"]), must_change_password=True))
        await session.commit()
    async with _client() as client:
        blocked = await client.get("/chat/sessions", headers=_bearer(account["token"]))
        assert (blocked.status_code, blocked.json()["detail"]) == (403, "password_change_required")
        status = await client.get("/account/status", headers=_bearer(account["token"]))
        assert status.json()["must_change_password"] is True
        changed = await client.post(
            "/account/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=_bearer(account["token"]),
        )
        assert changed.status_code == 200
        allowed = await client.get("/chat/sessions", headers=_bearer(changed.json()["access_token"]))
        assert allowed.status_code == 200


async def test_an_account_an_administrator_created_must_change_its_password() -> None:
    admin = await _new_account("admin")
    email = unique_email("provisioned")
    async with _client() as client:
        created = await client.post(
            "/admin/users",
            json={"name": "New Officer", "email": email, "password": PASSWORD, "role": "police"},
            headers=_bearer(admin["token"]),
        )
        assert created.status_code == 201, created.text
        status, tokens = await _login(client, email, PASSWORD)
        assert status == 200
        blocked = await client.get("/cases", headers=_bearer(tokens["access_token"]))
        assert (blocked.status_code, blocked.json()["detail"]) == (403, "password_change_required")
