from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from db.postgresdb import get_db
from db.models import Explorer, Org, GroupMembership, UserGroup
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
    response = []
    seen_org_ids = set()

    # Legacy: orgs from s3_explorer table
    folders = db.query(Explorer).filter(Explorer.user_id == user.id).all()

    org_by_bucket = {}
    if folders:
        bucket_names = list({f.bucket_name for f in folders})
        orgs = db.query(Org).filter(Org.bucket_name.in_(bucket_names), Org.is_active == True).all()
        for org in orgs:
            org_by_bucket[org.bucket_name] = org

    for _idx in folders:
        org = org_by_bucket.get(_idx.bucket_name)
        if org:
            seen_org_ids.add(org.id)
        response.append({
            "folder_name": _idx.folder_name,
            "folder_path": _idx.folder_path,
            "bucket_name": _idx.bucket_name,
            "org_id": org.id if org else None,
            "org_name": org.org_name if org else None,
        })

    # New: orgs from group memberships (grant-based access)
    member_org_ids = (
        db.query(UserGroup.org_id)
        .join(GroupMembership, GroupMembership.group_id == UserGroup.id)
        .filter(GroupMembership.user_id == user.id)
        .distinct()
        .all()
    )
    grant_org_ids = [r[0] for r in member_org_ids if r[0] not in seen_org_ids]

    if grant_org_ids:
        grant_orgs = db.query(Org).filter(Org.id.in_(grant_org_ids), Org.is_active == True).all()
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
            admin_orgs = db.query(Org).filter(Org.is_active == True).all()
            for org in admin_orgs:
                response.append({
                    "folder_name": org.org_name,
                    "folder_path": "",
                    "bucket_name": org.bucket_name,
                    "org_id": org.id,
                    "org_name": org.org_name,
                })
        else:
            # Org admins: only own subscription, dedup against legacy/grant entries
            admin_orgs = db.query(Org).filter(
                Org.is_active == True,
                Org.subscription_id == user.subscription_id,
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
