"""Mint the first service token from the command line, before any UI exists:

    python -m app.service_token --name depot-sync --scope employees:depot-export

Prints the token once. Thereafter use the super-admin API
(/api/v1/admin/service-tokens) to list or revoke.
"""
import argparse

from app.core.security import hash_service_token, new_service_token
from app.db.session import SessionLocal
from app.migrate import migrate
from app.models.models import ServiceToken


def main() -> None:
    ap = argparse.ArgumentParser(description="Create an HRMS service token")
    ap.add_argument("--name", required=True, help="what this token is for, e.g. depot-sync")
    ap.add_argument("--scope", action="append", required=True,
                    help="scope to grant; repeat for more than one")
    args = ap.parse_args()
    migrate()
    token = new_service_token()
    with SessionLocal() as db:
        row = ServiceToken(name=args.name, token_hash=hash_service_token(token),
                           scopes=" ".join(args.scope))
        db.add(row)
        db.commit()
        print(f"[SERVICE TOKEN] {row.name} (id={row.id}) scopes={row.scopes}")
    print("\nCopy this now - it is not stored and cannot be shown again:\n")
    print(f"    {token}\n")


if __name__ == "__main__":
    main()
