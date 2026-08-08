from db.postgresdb import Session
from db.models import Explorer


def get_all_folders_from_user_id(user_id: int):
    db = Session()
    try:
        folders = db.query(Explorer).filter(Explorer.user_id == user_id).all()
        return folders
    finally:
        db.close()


def get_bucket_name_from_base_path(base_path: str):
    db = Session()
    try:
        bucket_name = db.query(Explorer).filter(Explorer.folder_path == base_path).first()
        return bucket_name.bucket_name if bucket_name else None
    finally:
        db.close()
