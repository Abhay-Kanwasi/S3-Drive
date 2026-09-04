"""
Grant-based folder access control.

Checks whether a user's group memberships grant them access to a given
S3 prefix. Admins bypass all checks. Legacy s3_explorer fallback removed
(intentional for independent greenfield).
"""

from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.auth import CurrentUser, ADMIN_ROLE_IDS
from db.models import GroupMembership, FolderGrant, UserGroup


def get_user_granted_prefixes(
    user_id: int,
    org_id: int,
    db: Session,
) -> List[Tuple[str, str]]:
    """
    Return all (prefix, access_level) pairs the user has via group memberships.
    Only returns grants for the specified org.
    """
    rows = (
        db.query(FolderGrant.prefix, FolderGrant.access_level)
        .join(UserGroup, FolderGrant.group_id == UserGroup.id)
        .join(GroupMembership, GroupMembership.group_id == UserGroup.id)
        .filter(
            GroupMembership.user_id == user_id,
            FolderGrant.org_id == org_id,
        )
        .all()
    )
    return [(r.prefix, r.access_level) for r in rows]


def _user_has_any_memberships(user_id: int, org_id: int, db: Session) -> bool:
    """Check if the user belongs to at least one group in this org."""
    return (
        db.query(GroupMembership.id)
        .join(UserGroup, GroupMembership.group_id == UserGroup.id)
        .filter(
            GroupMembership.user_id == user_id,
            UserGroup.org_id == org_id,
        )
        .first()
    ) is not None


def check_prefix_access(
    user: CurrentUser,
    org_id: int,
    prefix: str,
    db: Session,
    require_write: bool = False,
) -> None:
    """
    Verify that the user can access the given prefix.

    - Admins (role 1, 3, 4): always allowed, no check.
    - Users with memberships: must have a FolderGrant whose prefix covers
      the requested path.  Write operations require access_level='read_write'.

    Raises HTTPException(403) on denial.
    """
    if user.role_id in ADMIN_ROLE_IDS:
        return

    if not _user_has_any_memberships(user.id, org_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No folder access granted for this organization",
        )

    grants = get_user_granted_prefixes(user.id, org_id, db)

    if not grants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No folder access granted for this organization",
        )

    norm_prefix = prefix if prefix.endswith("/") or prefix == "" else prefix + "/"

    for grant_prefix, access_level in grants:
        if require_write:
            # Writes: grant must directly cover the path (no upward reach).
            # e.g. grant on "A/B/" allows writing to "A/B/" and "A/B/C/"
            #      but NOT to "A/" (parent of the grant).
            if not norm_prefix.startswith(grant_prefix):
                continue
            if access_level != "read_write":
                continue
        else:
            # Reads: grant covers path OR path leads toward grant (navigation).
            if not (norm_prefix.startswith(grant_prefix) or grant_prefix.startswith(norm_prefix)):
                continue
        return

    action = "write to" if require_write else "access"
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"No grant covers this path. You do not have permission to {action} '{prefix}'",
    )


def prefix_is_accessible(
    user: CurrentUser,
    org_id: int,
    prefix: str,
    db: Session,
) -> bool:
    """Same rules as check_prefix_access (read) without raising."""
    try:
        check_prefix_access(user, org_id, prefix, db, require_write=False)
        return True
    except HTTPException:
        return False


def filter_folders_by_grants(
    user: CurrentUser,
    org_id: int,
    folders: list,
    current_prefix: str,
    db: Session,
) -> list:
    """
    Filter a list of folder items to only those the user has grants for.
    Admins see everything. Ungrouped users see nothing.

    A folder is visible if:
    - A grant covers the current_prefix (user has access to this directory) — show
      ALL subfolders since the user is already authorized at this level, OR
    - The folder key is a parent of a grant (navigation waypoint), OR
    - A grant is a prefix of the folder key (grant covers the folder).
    """
    if user.role_id in ADMIN_ROLE_IDS:
        return folders

    if not _user_has_any_memberships(user.id, org_id, db):
        return []

    grants = get_user_granted_prefixes(user.id, org_id, db)
    if not grants:
        return []

    grant_prefixes = [g[0] for g in grants]
    norm_prefix = current_prefix if current_prefix.endswith("/") or current_prefix == "" else current_prefix + "/"

    # If any grant directly covers the current browsing prefix,
    # show all folders at this level (user has full access here)
    for gp in grant_prefixes:
        if norm_prefix.startswith(gp):
            return folders

    # Otherwise, filter: show a folder if
    # 1. A grant covers it (grant is prefix of folder key), OR
    # 2. A grant is inside it (folder is a navigation waypoint), OR
    # 3. The folder was created by this user within this prefix
    visible = []
    for folder in folders:
        folder_key = folder.key if hasattr(folder, "key") else folder.get("key", "")
        # Check if folder is created by this user (user-created folders are always visible to their creator)
        created_by = folder.created_by if hasattr(folder, "created_by") else folder.get("created_by")
        if created_by is not None and str(created_by) == str(user.id):
            visible.append(folder)
            continue
        for gp in grant_prefixes:
            if folder_key.startswith(gp) or gp.startswith(folder_key):
                visible.append(folder)
                break

    return visible


def filter_files_by_grants(
    user: CurrentUser,
    org_id: int,
    files: list,
    current_prefix: str,
    db: Session,
) -> list:
    """
    Filter files to only those within a granted prefix.
    A file is visible only if a grant covers its location (grant prefix
    is a prefix of the file's parent directory).

    Unlike folders, files do NOT get shown just because a deeper grant exists.
    """
    if user.role_id in ADMIN_ROLE_IDS:
        return files

    if not _user_has_any_memberships(user.id, org_id, db):
        return []

    grants = get_user_granted_prefixes(user.id, org_id, db)
    if not grants:
        return []

    grant_prefixes = [g[0] for g in grants]

    visible = []
    for f in files:
        file_key = f.key if hasattr(f, "key") else f.get("key", "")
        for gp in grant_prefixes:
            if file_key.startswith(gp):
                visible.append(f)
                break

    return visible
