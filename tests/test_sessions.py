from os import urandom
from typing import Any, Dict, Optional, Union
from uuid import uuid4

import pytest
from pydantic import BaseModel, SecretBytes
from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_401_UNAUTHORIZED,
)
from starlite import OpenAPIConfig, Request, Starlite, delete, get, post
from starlite.middleware.session.memory_backend import MemoryBackendConfig
from starlite.testing import create_test_client

from starlite_sessions import SessionAuth, SessionAuthConfig


class User(BaseModel):
    id: str
    name: str
    email: str


user_instance = User(id=str(uuid4()), name="Moishe Zuchmir", email="moishe@zuchmir.com")


def retrieve_user_handler(session_data: Dict[str, Any]) -> Optional[User]:
    if session_data["id"] == user_instance.id:
        return user_instance
    return None


@pytest.mark.parametrize(
    "session_auth",
    [
        SessionAuth(secret=SecretBytes(urandom(16)), exclude=["login"], retrieve_user_handler=retrieve_user_handler),
        SessionAuthConfig(
            retrieve_user_handler=retrieve_user_handler, exclude=["login"], backend_config=MemoryBackendConfig()
        ),
    ],
)
def test_authentication(session_auth: Union[SessionAuth, SessionAuthConfig]) -> None:
    @post("/login")
    def login_handler(request: Request[Any, Any], data: Dict[str, Any]) -> None:
        request.set_session(data)

    @delete("/user/{user_id:str}")
    def delete_user_handler(request: Request[User, Any]) -> None:
        request.clear_session()

    @get("/user/{user_id:str}")
    def get_user_handler(request: Request[User, Any]) -> User:
        return request.user

    with create_test_client(
        route_handlers=[login_handler, delete_user_handler, get_user_handler],
        middleware=[session_auth.middleware],
    ) as client:
        response = client.get(f"user/{user_instance.id}")
        assert response.status_code == HTTP_401_UNAUTHORIZED

        response = client.post("/login", json=user_instance.dict())
        assert response.status_code == HTTP_201_CREATED

        response = client.get(f"user/{user_instance.id}")
        assert response.status_code == HTTP_200_OK
        assert response.json() == user_instance.dict()

        response = client.delete(f"user/{user_instance.id}")
        assert response.status_code == HTTP_204_NO_CONTENT

        response = client.get(f"user/{user_instance.id}")
        assert response.status_code == HTTP_401_UNAUTHORIZED

        response = client.post(
            "/login", json=User(id=str(uuid4()), name="Sigfried Lamago", email="llamago@zigi.com").dict()
        )
        assert response.status_code == HTTP_201_CREATED

        response = client.get(f"user/{user_instance.id}")
        assert response.status_code == HTTP_401_UNAUTHORIZED


def test_openapi() -> None:
    def retrieve_user_handler(session_data: Dict[str, Any]) -> Optional[User]:
        return None

    session_auth = SessionAuth(secret=SecretBytes(urandom(16)), retrieve_user_handler=retrieve_user_handler)
    openapi_config = OpenAPIConfig(
        title="My API",
        version="1.0.0",
        components=[session_auth.openapi_components],
        security=[session_auth.security_requirement],
    )

    app = Starlite(route_handlers=[], openapi_config=openapi_config)
    assert app.openapi_schema.dict(exclude_none=True) == {  # type: ignore
        "openapi": "3.1.0",
        "info": {"title": "My API", "version": "1.0.0"},
        "servers": [{"url": "/"}],
        "paths": {},
        "components": {
            "securitySchemes": {
                "sessionCookie": {
                    "type": "apiKey",
                    "description": "Session cookie authentication.",
                    "name": "Set-Cookie",
                    "security_scheme_in": "cookie",
                }
            }
        },
        "security": [{"sessionCookie": []}],
    }
