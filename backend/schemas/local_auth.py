"""Response shape for the Docker-local-only demo-session endpoint."""
from pydantic import BaseModel, Field


class LocalSessionUser(BaseModel):
    id: str = Field(description="The local demo user's UUID.")
    email: str = Field(description="The local demo user's fixed email.")
    created_at: str = Field(description="ISO-8601 UTC creation timestamp.")


class LocalSessionResponse(BaseModel):
    access_token: str = Field(description="Backend-verifiable HS256 access token.")
    expires_at: int = Field(description="Unix timestamp (seconds) the token expires at.")
    user: LocalSessionUser
