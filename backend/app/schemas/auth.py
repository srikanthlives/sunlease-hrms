from pydantic import BaseModel, EmailStr, field_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    role: str
    employee_id: int | None = None
    is_active: bool
    permissions: list[str] = []

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    email: EmailStr | None = None
    password: str
    full_name: str | None = None
    role_id: int
    employee_id: int | None = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    full_name: str | None = None
    role_id: int | None = None


class PasswordResetRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class SetActiveRequest(BaseModel):
    is_active: bool


class RoleOut(BaseModel):
    id: int
    name: str
    description: str | None = None

    class Config:
        from_attributes = True
