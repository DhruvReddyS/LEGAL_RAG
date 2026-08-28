from __future__ import annotations

import argparse
import asyncio
import getpass

from app.core.database import AsyncSessionLocal
from app.models.enums import UserRole
from app.schemas.auth import RegisterRequest
from app.services.auth import create_user, get_user_by_email


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a police or advocate account without placing its password in shell history."
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=(UserRole.POLICE.value, UserRole.ADVOCATE.value))
    return parser.parse_args()


async def create_account(args: argparse.Namespace, password: str) -> None:
    registration = RegisterRequest(
        name=args.name,
        email=args.email,
        password=password,
        role=UserRole(args.role),
    )
    async with AsyncSessionLocal() as session:
        if await get_user_by_email(session, str(registration.email)) is not None:
            raise SystemExit("An account with this email already exists.")
        user = await create_user(session, registration)
        await session.commit()
        print(f"Created {user.role.value} account for {user.email}.")


def main() -> None:
    args = parse_args()
    password = getpass.getpass("Password (12–72 characters, not echoed): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    asyncio.run(create_account(args, password))


if __name__ == "__main__":
    main()
