from typing import Optional
from pydantic import BaseModel


class Folder(BaseModel):
    user_id: int
    name: str
    basePath: str


class Initiate(BaseModel):
    userid: int
    name: str
    author: str
    basePath: str
    file_size: Optional[int] = None
