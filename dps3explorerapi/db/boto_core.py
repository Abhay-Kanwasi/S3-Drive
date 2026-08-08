import boto3
from boto3.s3.transfer import TransferConfig
import json
import secrets
from core.config import settings

client = boto3.client("s3")
BUCKET_NAME = settings.BUCKET


def convert_to_unit(number):
    """
    Converts a number to MB or GB depending on its size.

    Args:
        number: The number to convert.

    Returns:
        A string representation of the number in MB or GB.
    """
    if number < 1024:
        return f"{number} B"
    elif number < 1048576:
        return f"{number / 1024:.2f} KB"
    elif number < 1073741824:
        return f"{number / 1048576:.2f} MB"
    else:
        return f"{number / 1073741824:.2f} GB"


class BOTO:
    session = None
    s3 = None
    client = None

    def __init__(self) -> None:
        self.s3 = boto3.client("s3")

    def get_resource(self):
        self.s3 = self.session.client("s3")

    def get_all_folders_from_permitted_root(self, key) -> list:
        if self.s3 is None:
            raise Exception("Something")
        folders = self.s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=key, Delimiter="/")
        return folders["CommonPrefixes"]

    def create_folder(self, bucket_name, key):
        if self.s3 is None:
            raise Exception("Something")
        if not self.check_if_folder_exists(bucket_name, key):
            response = self.s3.put_object(Bucket=bucket_name, Key=key)
            return response
        else:
            return {}

    def check_if_folder_exists(self, bucket_name, key):
        folders = self.s3.list_objects_v2(Bucket=bucket_name, Prefix=key, Delimiter="/")
        if "CommonPrefixes" in list(folders.keys()):
            for i in folders["CommonPrefixes"]:
                if i["Prefix"].split("/")[-2] == key.split("/")[-1]:
                    return True
        return False

    def get_all_content_from_path(self, bucket_name, key) -> list:
        content: dict = self.s3.list_objects_v2(
            Bucket=bucket_name, Prefix=key, Delimiter="/"
        )
        content_list = list()
        try:
            for idx in content["CommonPrefixes"]:
                content_list.append(
                    {
                        "name": idx["Prefix"].split("/")[-2],
                        "type": "folder",
                        "size": 0,
                        "key": idx["Prefix"],
                        "last_modified": "",
                    }
                )
        except KeyError:
            pass
        try:
            for idx in content["Contents"]:
                name = idx["Key"].split("/")
                if name[-1] == "":
                    continue
                content_list.append(
                    {
                        "name": name[-1],
                        "key": idx["Key"],
                        "type": "file",
                        "size": convert_to_unit(idx["Size"]),
                        "last_modified": idx["LastModified"].strftime("%B %d, %Y"),
                    }
                )
        except KeyError:
            pass
        return content_list


def create_multipart_upload(file_key, author, bucket_name) -> str:
    metadata = {"author": author, "path": file_key, "bucket": bucket_name}

    uploadID = client.create_multipart_upload(
        Bucket=bucket_name, Key=file_key, Metadata=metadata
    )["UploadId"]
    return uploadID


def get_metadata(file_Key, tag, bucket_name):
    response = dict()
    try:
        if tag == "trash":
            metadata = client.get_object(Bucket="explorer-trash", Key=file_Key)
        elif tag == "explorer":
            metadata = client.get_object(Bucket=bucket_name, Key=file_Key)
        response["author"] = metadata["Metadata"]["author"].title()
    except Exception as e:
        response["author"] = "NA"

    return response


def uploadPart(chunk, file_key, part_number, uploadID, bucket_name) -> str:
    ### file will be the final name along with path in s3
    response = client.upload_part(
        Body=chunk,
        Bucket=bucket_name,
        Key=file_key,
        PartNumber=part_number,
        UploadId=uploadID,
    )
    return json.loads(response["ETag"])


def complete_upload(file_key, uploadID, e_tag, bucket_name):
    response = client.complete_multipart_upload(
        Bucket=bucket_name,
        Key=file_key,
        UploadId=uploadID,
        MultipartUpload={"Parts": e_tag},
    )
    return response


async def put_objects(file, path):
    client.put_object(
        Body=await file.read(), Bucket=BUCKET_NAME, Key=f"{path}{file.filename}"
    )


def generate_token(nBytes) -> str:
    return secrets.token_urlsafe(nBytes)


class TrashBOTO:
    trash_session = None
    trash_s3 = None
    trash_client = None
    TRASH_BUCKET = "explorer-trash"

    def __init__(self) -> None:
        self.trash_s3 = boto3.client("s3")

    def get_resource(self):
        self.trash_s3 = self.trash_session.client("s3")

    def restore_item(self, key):
        _metadata_object = self.trash_s3.get_object(Bucket=self.TRASH_BUCKET, Key=key)
        total_size = _metadata_object["ContentLength"]

        transfer_config = TransferConfig(
            multipart_threshold=total_size,
            multipart_chunksize=10 * 1024 * 1024,
            max_concurrency=5,
        )

        copy_source = {"Bucket": self.TRASH_BUCKET, "Key": key}
        path_from_metadata = _metadata_object["ResponseMetadata"]["HTTPHeaders"][
            "x-amz-meta-path"
        ]
        bucket_name = _metadata_object["ResponseMetadata"]["HTTPHeaders"][
            "x-amz-meta-bucket"
        ]
        self.trash_s3.copy_object(
            CopySource=copy_source,
            Bucket=bucket_name,
            Key=path_from_metadata,
            MetadataDirective="COPY",
        )
        response = self.trash_s3.delete_object(Bucket=self.TRASH_BUCKET, Key=f"{key}")
        confirmation = response["ResponseMetadata"]["HTTPStatusCode"]
        return confirmation

    def get_all_trash_items(self, key) -> list:
        key = f"trash/{key}/"
        content: dict = self.trash_s3.list_objects_v2(
            Bucket=self.TRASH_BUCKET, Prefix=key, Delimiter="/"
        )
        content_list = list()
        try:
            for idx in content["Contents"]:
                name = idx["Key"].split("/")
                if name[-1] == "":
                    continue
                content_list.append(
                    {
                        "name": name[-1],
                        "key": idx["Key"],
                        "type": "file",
                        "size": convert_to_unit(idx["Size"]),
                        "last_modified": idx["LastModified"].strftime("%B %d, %Y"),
                    }
                )
        except KeyError:
            pass
        return content_list
