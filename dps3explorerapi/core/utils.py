from db.postgresdb import Session


def get_bucket_name_from_base_path(base_path: str):
    """Resolve bucket name from org base path via organizations table."""
    from db.models import Organization
    db = Session()
    try:
        org = db.query(Organization).filter(Organization.bucket_name == base_path, Organization.is_active == True).first()
        return org.bucket_name if org else None
    finally:
        db.close()
