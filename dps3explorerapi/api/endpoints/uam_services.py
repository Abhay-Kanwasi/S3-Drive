"""
Compat shim for older /uam/* clients.

Primary sidebar listing is GET /browse/orgs. These routes remain for any
external callers still on the old paths.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api.endpoints.browse import _accessible_orgs_for_user
from core.auth import CurrentUser, get_current_user
from db.postgresdb import get_db

router = APIRouter()


@router.get("/")
def ping():
    return JSONResponse(status_code=200, content="explorer healthy")


@router.get("/folders")
def get_organisations(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deprecated alias of GET /browse/orgs."""
    return _accessible_orgs_for_user(user, db)


@router.get("/items")
def get_admin_list_item(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.is_admin:
        return [{"name": "Admin Panel", "url_path": "/admin"}]
    return [{}]
