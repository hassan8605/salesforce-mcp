from typing import Optional
from pydantic import BaseModel


class SalesforceHealthResponse(BaseModel):
    connected: bool
    username: Optional[str] = None
    org_id: Optional[str] = None
    display_name: Optional[str] = None
