"""Server-only account role/status management with an audited reason."""

import argparse
import json
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from api.accounts import AccountStore
from api.database import Database
from api.product_models import Account
from api.product_schemas import RoleBody
from api.settings import Settings
from api.store import StoreError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=["user", "editor", "admin"])
    status = parser.add_mutually_exclusive_group()
    status.add_argument("--disable", action="store_true")
    status.add_argument("--enable", action="store_true")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--version", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not os.environ.get("DATABASE_URL"):
        parser.error("Set DATABASE_URL explicitly; this command does not load .env")
    if not args.role and not args.disable and not args.enable:
        parser.error("Choose --role, --disable or --enable")
    reason = args.reason.strip()
    if not 3 <= len(reason) <= 500:
        parser.error("Reason must contain 3 to 500 characters")
    if args.version is not None and args.version < 1:
        parser.error("Version must be positive")
    database = None
    try:
        settings = Settings.from_env()
        database = Database(settings.database_url.get_secret_value())
        with database.session() as session:
            account = session.scalar(
                select(Account).where(Account.email == args.email.strip().casefold())
            )
            if account is None:
                parser.exit(1, "Account was not found; register it first.\n")
            identifier = account.id
            body = RoleBody(
                role=args.role or account.role,
                version=args.version or account.version,
                disabled=True if args.disable else False if args.enable else account.disabled,
            )
        if args.dry_run:
            result = {"account_id": identifier, **body.model_dump(), "dry_run": True}
        else:
            changed = AccountStore(database, settings).role(identifier, body, reason=reason)
            result = {key: changed[key] for key in ("account_id", "role", "disabled", "version")}
            result["audit_recorded"] = True
        print(json.dumps(result))
        return 0
    except StoreError as error:
        parser.exit(1, f"Account update failed: {error.code}.\n")
    except (SQLAlchemyError, ValueError):
        parser.exit(
            1, "Account update failed; check explicit server configuration and migrations.\n"
        )
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
