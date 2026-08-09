from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from db.postgresdb import get_db
from db.models import Organization, GroupMembership, UserGroup
from core.auth import CurrentUser, get_current_user, ADMIN_ROLE_IDS, GLOBAL_ADMIN_ROLE_IDS

router = APIRouter()


@router.get("/")
def ping():
    return JSONResponse(status_code=200, content="UAM healthy")


@router.get("/folders")
def get_organisations(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Grant-based: orgs from group memberships
    response = []
    member_org_ids = (
        db.query(UserGroup.org_id)
        .join(GroupMembership, GroupMembership.group_id == UserGroup.id)
        .filter(GroupMembership.user_id == user.id)
        .distinct()
        .all()
    )
    seen_org_ids = set()

    if grant_org_ids:
        grant_orgs = db.query(Organization).filter(Organization.id.in_(grant_org_ids), Organization.is_active == True).all()
        for org in grant_orgs:
            seen_org_ids.add(org.id)
            response.append({
                "folder_name": org.org_name,
                "folder_path": "",
                "bucket_name": org.bucket_name,
                "org_id": org.id,
                "org_name": org.org_name,
            })

    # Admins: show onboarded orgs
    if user.role_id in ADMIN_ROLE_IDS:
        if user.role_id in GLOBAL_ADMIN_ROLE_IDS:
            # Global admins: all orgs, no dedup (legacy + org entries are both needed)
            admin_orgs = db.query(Organization).filter(Organization.is_active == True).all()
            for org in admin_orgs:
                response.append({
                    "folder_name": org.org_name,
                    "folder_path": "",
                    "bucket_name": org.bucket_name,
                    "org_id": org.id,
                    "org_name": org.org_name,
                })
        else:
            # Organization admins: only own subscription, dedup against legacy/grant entries
            admin_orgs = db.query(Organization).filter(
                Organization.is_active == True,
                Organization.subscription_id == user.subscription_id,
            ).all()
            for org in admin_orgs:
                if org.id not in seen_org_ids:
                    response.append({
                        "folder_name": org.org_name,
                        "folder_path": "",
                        "bucket_name": org.bucket_name,
                        "org_id": org.id,
                        "org_name": org.org_name,
                    })
                    seen_org_ids.add(org.id)

    return response


@router.get("/items")
def get_admin_list_item(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.is_admin:
        return [{"name": "Admin Panel", "url_path": "/admin"}]
    else:
        return [{}]
