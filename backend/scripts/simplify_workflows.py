"""Run from backend: python -m scripts.simplify_workflows --help."""

import argparse
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import Principal
from app.database import engine
from app.models import Membership, MembershipStatus, Organization, PermissionRole, UserProfile
from app.workflow_simplification import WorkflowSimplification, simplify_workflows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or apply audited workflow simplification."
    )
    parser.add_argument("--organization", required=True, help="Organization slug")
    parser.add_argument("--actor", required=True, help="Exact active administrator full name")
    parser.add_argument("--config", required=True, help="Private JSON configuration path")
    parser.add_argument(
        "--apply", action="store_true", help="Commit; omitted means rollback preview"
    )
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as file:
        config = WorkflowSimplification.model_validate(json.load(file))
    with Session(engine) as db:
        actors = db.execute(
            select(UserProfile, Membership, PermissionRole)
            .join(Membership, Membership.user_profile_id == UserProfile.id)
            .join(Organization, Membership.organization_id == Organization.id)
            .join(PermissionRole, Membership.permission_role_id == PermissionRole.id)
            .where(
                Organization.slug == args.organization,
                UserProfile.full_name == args.actor,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.removed_at.is_(None),
                PermissionRole.code == "admin",
            )
        ).all()
        if len(actors) != 1:
            raise ValueError("Escolha um administrador ativo e inequívoco da organização.")
        profile, membership, access = actors[0]
        principal = Principal(None, profile, membership, access)  # type: ignore[arg-type]
        result = simplify_workflows(db, principal, config, apply=args.apply)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({"applied": args.apply, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
