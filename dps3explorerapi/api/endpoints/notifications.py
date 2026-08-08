"""
User notification endpoints (Phase 3.6).

- GET    /notifications        — list user's notifications (newest first, limit 50)
- POST   /notifications/read   — mark notifications as read
- DELETE /notifications/{id}   — dismiss (hard-delete) a notification
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user
from db.postgresdb import get_db
from db.models import UserNotification

router = APIRouter()


class ReadRequest(BaseModel):
    ids: Optional[List[int]] = None
    all: Optional[bool] = None


@router.get("")
async def list_notifications(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return user's notifications (newest first, max 50) with unread count."""
    notifications = (
        db.query(UserNotification)
        .filter(UserNotification.user_id == user.id)
        .order_by(UserNotification.created_at.desc())
        .limit(50)
        .all()
    )

    unread_count = (
        db.query(UserNotification)
        .filter(UserNotification.user_id == user.id, UserNotification.is_read == False)
        .count()
    )

    items = [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]

    return {"items": items, "unread_count": unread_count}


@router.post("/read")
async def mark_read(
    payload: ReadRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark notifications as read. Provide either `ids` or `all: true` (not both)."""
    has_ids = payload.ids is not None and len(payload.ids) > 0
    has_all = payload.all is True

    if has_ids == has_all:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of 'ids' (non-empty list) or 'all: true'",
        )

    if has_all:
        db.query(UserNotification).filter(
            UserNotification.user_id == user.id,
            UserNotification.is_read == False,
        ).update({"is_read": True})
    else:
        db.query(UserNotification).filter(
            UserNotification.user_id == user.id,
            UserNotification.id.in_(payload.ids),
        ).update({"is_read": True}, synchronize_session="fetch")

    db.commit()
    return {"status": "ok"}


@router.delete("/{notification_id}")
async def dismiss_notification(
    notification_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hard-delete a notification. Returns 404 if not found or not owned by user."""
    notif = db.query(UserNotification).filter(
        UserNotification.id == notification_id,
        UserNotification.user_id == user.id,
    ).first()

    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.delete(notif)
    db.commit()
    return {"status": "deleted"}
