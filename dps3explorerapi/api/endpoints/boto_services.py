from fastapi import APIRouter, UploadFile, File, Form, Response, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from db.boto_core import (
    BOTO,
    TrashBOTO,
    create_multipart_upload,
    uploadPart,
    complete_upload,
    put_objects,
    get_metadata,
    generate_token,
)
from db.postgresdb import get_db
from models.request.request import Folder, Initiate
from db.models import TokenRepository, Explorer, Org, FolderMetadata, PlatformSettings
from core.audit import audit_log, audit_actor_fields
from datetime import datetime
from core.utils import get_all_folders_from_user_id
import boto3
from core.auth import CurrentUser, get_current_user, ADMIN_ROLE_IDS
from core.config import settings
from core.permissions import check_prefix_access


router = APIRouter()


def _resolve_bucket(user_id: int, base_path: str, db: Session = None) -> str:
    """Resolve bucket name from legacy s3_explorer rows or org table.

    Resolution order:
    1. Match folder_path in s3_explorer (legacy behavior)
    2. Match bucket_name in s3_explorer (org-aware basePath = bucket_name)
    3. Match bucket_name in Org table (group-only users with no legacy entries)
    """
    if db is not None:
        folders = db.query(Explorer).filter(Explorer.user_id == user_id).all()
    else:
        folders = get_all_folders_from_user_id(user_id)

    # 1. Legacy: exact folder_path match
    matches = [f for f in folders if f.folder_path == base_path]
    if matches:
        return matches[0].bucket_name

    # 2. Org-aware: basePath is the bucket_name itself
    matches = [f for f in folders if f.bucket_name == base_path]
    if matches:
        return matches[0].bucket_name

    # 3. Org table fallback: for users with no s3_explorer entries
    if db and base_path:
        org = db.query(Org).filter(Org.bucket_name == base_path, Org.is_active == True).first()
        if org:
            return org.bucket_name

    raise HTTPException(
        status_code=404,
        detail="No matching folder configuration found. Please use the organization explorer.",
    )


class DeleteReq(BaseModel):
    userid: str
    basePath: str
    filename: str
    file_key: str
    author: str


class Finalised(BaseModel):
    filename: str
    author: str
    file_key: str
    uploadID: str
    userid: int
    basePath: str
    e_tag: list


@router.get("/health", status_code=200)
def send_email():
    """
    Health Check
    """
    return {"Status": "Healthy"}


@router.get("/upload-constraints", status_code=200)
def get_upload_constraints(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return current upload rules (extensions + max size + colors) for any authenticated user."""
    from api.endpoints.admin import _get_or_create_settings, DEFAULT_EXTENSIONS

    row = _get_or_create_settings(db)
    ext_objects = []
    if row and row.allowed_extensions:
        for entry in row.allowed_extensions:
            if isinstance(entry, dict):
                ext_objects.append({"ext": entry.get("ext", ""), "color": entry.get("color", "#6b7280")})
            else:
                ext_objects.append({"ext": str(entry), "color": "#6b7280"})
    else:
        ext_objects = list(DEFAULT_EXTENSIONS)

    allowed = sorted(_get_allowed_extensions(db) | COMPOUND_EXTENSIONS)
    max_bytes = _get_max_upload_bytes(db)
    return {
        "allowed_extensions": allowed,
        "extension_colors": ext_objects,
        "max_upload_bytes": max_bytes,
    }


@router.get("/folders", status_code=200)
def get_all_folders(user: CurrentUser = Depends(get_current_user)):
    boto = BOTO()
    response: list = boto.get_all_folders_from_permitted_root(key="")
    return response


@router.post("/folders", status_code=201)
def create_folders(folder: Folder, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    bucket_name = _resolve_bucket(user.id, folder.basePath, db)

    is_admin = user.role_id in ADMIN_ROLE_IDS
    if not is_admin:
        parts = [p for p in folder.name.rstrip("/").split("/") if p]
        if len(parts) < 2:
            raise HTTPException(
                status_code=403,
                detail="Users can only create subfolders inside admin-created folders",
            )
        org = db.query(Org).filter(
            Org.bucket_name == bucket_name, Org.is_active == True
        ).first()
        if not org:
            raise HTTPException(
                status_code=403,
                detail="No onboarded organization found for this bucket",
            )

        parent_prefix = "/".join(parts[:-1]) + "/" if len(parts) > 1 else ""
        check_prefix_access(user, org.id, parent_prefix, db, require_write=True)

    boto = BOTO()
    content: list = boto.create_folder(bucket_name=bucket_name, key=folder.name)

    # Track ownership in FolderMetadata (same as new /folders/create endpoint)
    folder_key = folder.name if folder.name.endswith("/") else folder.name + "/"
    org = db.query(Org).filter(
        Org.bucket_name == bucket_name, Org.is_active == True
    ).first()
    if org:
        existing_meta = db.query(FolderMetadata).filter(
            FolderMetadata.org_id == org.id,
            FolderMetadata.key == folder_key,
        ).first()
        if not existing_meta:
            role_label = "admin" if is_admin else "user"
            db.add(FolderMetadata(
                org_id=org.id,
                key=folder_key,
                created_by=user.id,
                created_by_role=role_label,
            ))
            db.commit()

    return content


@router.post("/event", status_code=200)
def check_if_folder_exists(folder: Folder, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    boto = BOTO()
    bucket_name = _resolve_bucket(user.id, folder.basePath, db)
    content: list = boto.check_if_folder_exists(
        bucket_name=bucket_name, key=folder.name
    )
    if content:
        return JSONResponse(
            status_code=400,
            content="*Folder name already exists. Please enter a different folder name",
        )
    return JSONResponse(status_code=200, content="")


@router.post("/content")
async def get_all_content_v2(folder: Folder, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _folder_name = folder.name.split("/")[-2]
    bucket_name = _resolve_bucket(user.id, folder.basePath, db)

    if user.role_id not in ADMIN_ROLE_IDS:
        org = db.query(Org).filter(
            Org.bucket_name == bucket_name, Org.is_active == True
        ).first()
        if org:
            check_prefix_access(user, org.id, folder.name, db, require_write=False)

    boto = BOTO()
    content: list = boto.get_all_content_from_path(
        bucket_name=bucket_name, key=folder.name
    )
    response = dict()
    response["content"] = content
    folder_name = folder.name.split("/")
    response["key"] = [i for i in folder_name if len(i) > 0]
    response["path"] = folder.name
    return response


FALLBACK_EXTENSIONS = {
    ".parquet", ".orc", ".csv", ".json", ".zip", ".gz", ".xlsx",
    ".txt", ".pdf", ".docx", ".png",
}

COMPOUND_EXTENSIONS = {".csv.gz"}


def _get_allowed_extensions(db: Session) -> set:
    """Load allowed extensions from PlatformSettings. Falls back to defaults."""
    row = db.query(PlatformSettings).filter(PlatformSettings.id == 1).first()
    if row and row.allowed_extensions:
        exts = set()
        for entry in row.allowed_extensions:
            if isinstance(entry, dict):
                exts.add(entry.get("ext", "").lower())
            else:
                exts.add(str(entry).lower())
        return exts
    return FALLBACK_EXTENSIONS


def _get_max_upload_bytes(db: Session) -> int:
    """Load max upload size from PlatformSettings."""
    row = db.query(PlatformSettings).filter(PlatformSettings.id == 1).first()
    if row and row.max_upload_bytes:
        return row.max_upload_bytes
    return 5 * 1024 * 1024 * 1024  # 5 GB default


def _check_file_extension(filename: str, db: Session) -> None:
    """Reject files whose extension is not in the allowlist."""
    allowed = _get_allowed_extensions(db)
    name_lower = filename.lower()
    for ext in COMPOUND_EXTENSIONS:
        if name_lower.endswith(ext):
            return
    parts = name_lower.rsplit(".", 1)
    if len(parts) < 2 or f".{parts[1]}" not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"File type not allowed. Accepted formats: {', '.join(sorted(allowed | COMPOUND_EXTENSIONS))}",
        )


@router.post("/initiate")
async def initiate(initiate: Initiate, request: Request, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_file_extension(initiate.name.split("/")[-1], db)

    if initiate.file_size is not None:
        max_bytes = _get_max_upload_bytes(db)
        if initiate.file_size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size ({max_bytes / (1024**3):.1f} GB)",
            )

    bucket_name = _resolve_bucket(user.id, initiate.basePath, db)

    is_admin = user.role_id in ADMIN_ROLE_IDS
    if not is_admin:
        parts = [p for p in initiate.name.split("/") if p]
        if len(parts) < 2:
            raise HTTPException(
                status_code=403,
                detail="Users cannot upload files at the bucket root level",
            )
        org = db.query(Org).filter(
            Org.bucket_name == bucket_name, Org.is_active == True
        ).first()
        if not org:
            raise HTTPException(
                status_code=403,
                detail="No onboarded organization found for this bucket",
            )

        file_prefix = "/".join(parts[:-1]) + "/" if len(parts) > 1 else ""
        check_prefix_access(user, org.id, file_prefix, db, require_write=True)

    uploadId: str = create_multipart_upload(initiate.name, initiate.author, bucket_name)

    org_id = None
    org_name = None
    if not (user.role_id in ADMIN_ROLE_IDS):
        org_id = org.id if org else None
        org_name = org.org_name if org else None
    else:
        found_org = db.query(Org).filter(Org.bucket_name == bucket_name, Org.is_active == True).first()
        org_id = found_org.id if found_org else None
        org_name = found_org.org_name if found_org else None

    audit_log(
        event_type="FILE_UPLOAD_INITIATED",
        target_key=initiate.name,
        org_id=org_id,
        org_name=org_name,
        details={
            "summary": f"{user.user_name or 'User'} started upload of '{initiate.name}'",
            "file_path": initiate.name,
            "bucket": bucket_name,
        },
        request=request,
        **audit_actor_fields(user),
    )

    return {"UploadId": uploadId}


@router.post("/chunks")
async def chunks(
    file: UploadFile = File(...),
    path: str = Form(...),
    count: int = Form(...),
    tag: str = Form(...),
    basePath: str = Form(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bucket_name = _resolve_bucket(user.id, basePath, db)
    etag = uploadPart(await file.read(), path, count, tag, bucket_name)
    return {"tag": etag}


@router.post("/finalised")
def finalised(
    finalised: Finalised,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bucket_name = _resolve_bucket(user.id, finalised.basePath, db)
    tag = complete_upload(
        finalised.file_key, finalised.uploadID, finalised.e_tag, bucket_name
    )
    org = db.query(Org).filter(Org.bucket_name == bucket_name, Org.is_active == True).first()
    audit_log(
        event_type="FILE_UPLOADED",
        target_key=finalised.file_key,
        org_id=org.id if org else None,
        org_name=org.org_name if org else None,
        details={
            "summary": f"{user.user_name or 'User'} completed upload of '{finalised.file_key}'",
            "file_path": finalised.file_key,
            "bucket": bucket_name,
            "upload_id": finalised.uploadID,
        },
        request=request,
        **audit_actor_fields(user),
    )
    return {"tag": tag}


@router.post("/upload/v2")
async def uploadFiles(
    request: Request,
    file: UploadFile = File(...),
    path: str = Form(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_file_extension(path.split("/")[-1], db)

    if file.size is not None:
        max_bytes = _get_max_upload_bytes(db)
        if file.size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size ({max_bytes / (1024**3):.1f} GB)",
            )

    is_admin = user.role_id in ADMIN_ROLE_IDS
    org = None
    if not is_admin:
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            raise HTTPException(
                status_code=403,
                detail="Users cannot upload files at the bucket root level",
            )
        org = db.query(Org).filter(
            Org.bucket_name == settings.BUCKET, Org.is_active == True
        ).first()
        if not org:
            raise HTTPException(
                status_code=403,
                detail="No onboarded organization found for this bucket",
            )

        file_prefix = "/".join(parts[:-1]) + "/" if len(parts) > 1 else ""
        check_prefix_access(user, org.id, file_prefix, db, require_write=True)

    await put_objects(file=file, path=path)

    file_key = f"{path}{file.filename}"
    org_id = org.id if org else None
    org_name = org.org_name if org else None
    if not org:
        found_org = db.query(Org).filter(Org.bucket_name == settings.BUCKET, Org.is_active == True).first()
        if found_org:
            org_id = found_org.id
            org_name = found_org.org_name
    audit_log(
        event_type="FILE_UPLOADED",
        target_key=file_key,
        org_id=org_id,
        org_name=org_name,
        details={
            "summary": f"{user.user_name or 'User'} uploaded '{file_key}'",
            "file_path": file_key,
            "filename": file.filename,
            "bucket": settings.BUCKET,
        },
        request=request,
        **audit_actor_fields(user),
    )


@router.post("/delete")
def delete_by_filename(deleteReq: DeleteReq, request: Request, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    from db.models import Org
    from core.config import settings

    bucket_name = _resolve_bucket(user.id, deleteReq.basePath, db)

    org = db.query(Org).filter(Org.bucket_name == bucket_name, Org.is_active == True).first()

    if org and user.role_id not in ADMIN_ROLE_IDS:
        file_parts = [p for p in deleteReq.file_key.split("/") if p]
        del_prefix = "/".join(file_parts[:-1]) + "/" if len(file_parts) > 1 else ""
        check_prefix_access(user, org.id, del_prefix, db, require_write=True)

    s3 = boto3.client("s3")

    # Verify the file actually exists before attempting copy
    try:
        head = s3.head_object(Bucket=bucket_name, Key=deleteReq.file_key)
        file_size = head["ContentLength"]
    except s3.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey"):
            return Response(status_code=404, content="File not found in storage")
        return Response(status_code=500, content="Unable to access file")
    except Exception:
        return Response(status_code=404, content="File not found or inaccessible")

    SINGLE_COPY_LIMIT = 5 * 1024 * 1024 * 1024  # 5 GB
    PART_SIZE = 100 * 1024 * 1024  # 100 MB

    try:
        if org:
            trash_key = f"trash/{org.id}/{user.id}/{deleteReq.file_key}"
            trash_metadata = {
                "path": deleteReq.file_key,
                "bucket": bucket_name,
                "org_id": str(org.id),
                "deleted_by": str(user.id),
            }
        else:
            trash_key = f"trash/{user.id}/{deleteReq.filename}"
            trash_metadata = None

        if file_size <= SINGLE_COPY_LIMIT:
            copy_args = {
                "CopySource": {"Bucket": bucket_name, "Key": deleteReq.file_key},
                "Bucket": settings.TRASH_BUCKET,
                "Key": trash_key,
            }
            if trash_metadata:
                copy_args["Metadata"] = trash_metadata
                copy_args["MetadataDirective"] = "REPLACE"
            else:
                copy_args["MetadataDirective"] = "COPY"
            s3.copy_object(**copy_args)
        else:
            # Multipart copy for files > 5GB
            mpu = s3.create_multipart_upload(
                Bucket=settings.TRASH_BUCKET,
                Key=trash_key,
                **({"Metadata": trash_metadata, "MetadataDirective": "REPLACE"} if trash_metadata else {}),
            )
            upload_id = mpu["UploadId"]
            try:
                parts = []
                offset = 0
                part_num = 1
                while offset < file_size:
                    end = min(offset + PART_SIZE, file_size) - 1
                    part = s3.upload_part_copy(
                        Bucket=settings.TRASH_BUCKET,
                        Key=trash_key,
                        UploadId=upload_id,
                        PartNumber=part_num,
                        CopySource={"Bucket": bucket_name, "Key": deleteReq.file_key},
                        CopySourceRange=f"bytes={offset}-{end}",
                    )
                    parts.append({"PartNumber": part_num, "ETag": part["CopyPartResult"]["ETag"]})
                    offset = end + 1
                    part_num += 1
                s3.complete_multipart_upload(
                    Bucket=settings.TRASH_BUCKET,
                    Key=trash_key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
            except Exception:
                s3.abort_multipart_upload(Bucket=settings.TRASH_BUCKET, Key=trash_key, UploadId=upload_id)
                return Response(status_code=500, content="Failed to move large file to trash. Please try again.")
    except Exception:
        return Response(status_code=500, content="Failed to move file to trash. Please try again.")

    try:
        resp = s3.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": [{"Key": deleteReq.file_key}]},
        )
        errors = resp.get("Errors", [])
        if errors:
            return Response(status_code=502, content="Moved to trash but failed to remove from source (IAM)")
    except Exception:
        return Response(status_code=502, content="Failed to remove from source")

    audit_log(
        event_type="FILE_TRASHED",
        target_key=deleteReq.file_key,
        org_id=org.id if org else None,
        org_name=org.org_name if org else None,
        details={
            "summary": f"{user.user_name or 'User'} moved '{deleteReq.file_key}' to trash",
            "source_path": deleteReq.file_key,
            "filename": deleteReq.filename,
            "bucket": bucket_name,
        },
        request=request,
        **audit_actor_fields(user),
    )

    return Response(status_code=200, content="Moved to trash")


@router.get("/meta")
def metadata(file_Key: str, tag: str, basePath: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    bucket_name = _resolve_bucket(user.id, basePath, db)
    metadata_response = get_metadata(file_Key, tag, bucket_name)
    return metadata_response


@router.get("/download")
def download(
    basePath: str,
    filename: str,
    file_key: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return Response(status_code=410, content="Download is disabled in this version")


@router.get("/restore")
async def restore_items(key: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user_record = db.query(Explorer).filter(Explorer.user_id == user.id).all()
    if user_record is not None:
        boto = TrashBOTO()
        content: list = boto.restore_item(key=key)
        return "OK"


@router.get("/recycle")
def get_recycle_bin(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user_record = db.query(Explorer).filter(Explorer.user_id == user.id).all()
    if user_record is not None:
        boto = TrashBOTO()
        content: list = boto.get_all_trash_items(key=str(user.id))
        response = dict()
        response["content"] = content
        response["key"] = ["Trash"]
        response["path"] = "Trash"
        return response


################## integration APIS (own token auth) ###################


@router.get("/v2/folders")
async def get_folders_v2_create(
    userid: str,
    folder_name: str,
    folder_path: str,
    relative_path: str,
    keyword: str,
    db: Session = Depends(get_db),
):
    if keyword == "Explorer":
        folder_access: Explorer = Explorer(
            user_id=str(userid),
            folder_name=folder_name,
            folder_path=folder_path,
            relative_path=relative_path,
        )
        db.add(folder_access)
        db.commit()
        return Response(status_code=status.HTTP_201_CREATED, content="Done")
    else:
        return Response(status_code=status.HTTP_403_FORBIDDEN, content="Forbidden")


@router.get("/v2/generate")
async def generate_token_endpoint(userid: str, keyword: str, db: Session = Depends(get_db)):
    if keyword == "Explorer":
        generated_token = generate_token(32)
        token: TokenRepository = TokenRepository(
            user_id=int(userid), token=generated_token, is_expired=False
        )
        db.add(token)
        db.commit()
        return Response(status_code=status.HTTP_200_OK, content=generated_token)
    return Response(status_code=status.HTTP_403_FORBIDDEN, content="Forbidden")


@router.get("/v2/token-folders")
async def get_folders_by_token(token: str, db: Session = Depends(get_db)):
    token_record = (
        db.query(TokenRepository)
        .filter(TokenRepository.token == token, TokenRepository.is_expired != True)
        .first()
    )
    if token_record:
        userid = token_record.user_id
        folders = db.query(Explorer).filter(Explorer.user_id == userid).all()
        response = list()
        for _idx in folders:
            response.append(
                {"folder_name": _idx.folder_name, "folder_path": _idx.relative_path}
            )
        return response
    else:
        return Response(status_code=status.HTTP_403_FORBIDDEN, content="Forbidden")


@router.post("/v2/upload")
async def upload_files_integration(
    token: str = Form(...),
    folderpath: str = Form(...),
    year: str = Form(...),
    month: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    token_record = (
        db.query(TokenRepository)
        .filter(TokenRepository.token == token, TokenRepository.is_expired != True)
        .first()
    )
    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    userid = token_record.user_id
    folder = (
        db.query(Explorer)
        .filter(Explorer.user_id == userid, Explorer.relative_path == folderpath)
        .first()
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder path not found for this user")

    _check_file_extension(file.filename, db)

    try:
        await put_objects(file=file, path=f"{folder.folder_path}/{year}/{month}")
    except Exception:
        return Response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content="Something went wrong",
        )
    return Response(status_code=status.HTTP_200_OK, content="Uploaded")
