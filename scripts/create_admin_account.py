from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import LoginRequest
from app.services.auth import get_user_by_email


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the first administrator without placing its password in shell history."
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    return parser.parse_args()


async def create_account(args: argparse.Namespace, password: str) -> None:
    normalized_email = str(LoginRequest(email=args.email, password=password).email)
    normalized_name = " ".join(args.name.split())
    if len(normalized_name) < 2:
        raise SystemExit("Name must contain at least two visible characters.")
    if not 12 <= len(password) <= 72 or len(password.encode("utf-8")) > 72:
        raise SystemExit("Password must contain 12–72 characters and at most 72 UTF-8 bytes.")
    async with AsyncSessionLocal() as session:
        if await get_user_by_email(session, normalized_email) is not None:
            raise SystemExit("An account with this email already exists.")
        existing_admins = int(
            await session.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN))
            or 0
        )
        if existing_admins:
            raise SystemExit(
                "An administrator already exists. Additional admin creation is intentionally disabled."
            )
        user = User(
            name=normalized_name,
            email=normalized_email,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Created the bootstrap administrator for {user.email}.")


def main() -> None:
    args = parse_args()
    password = getpass.getpass("Password (12–72 characters, not echoed): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    asyncio.run(create_account(args, password))


if __name__ == "__main__":
    main()
