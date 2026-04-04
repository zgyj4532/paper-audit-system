from pydantic import BaseModel
from typing import Optional


class TaskCreate(BaseModel):
    file_path: str


class TaskOut(BaseModel):
    id: int
    file_path: str
    status: str
    progress: int
    result_path: Optional[str]
