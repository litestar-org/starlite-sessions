# Starlite Sessions

<!-- markdownlint-disable -->
<img alt="Starlite logo" src="./starlite-banner.svg" width="100%" height="auto">
<!-- markdownlint-restore -->

<div align="center">

[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=starlite-api_starlite-sessions&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=starlite-api_starlite-sessions)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=starlite-api_starlite-sessions&metric=coverage)](https://sonarcloud.io/summary/new_code?id=starlite-api_starlite-sessions)

[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=starlite-api_starlite-sessions&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=starlite-api_starlite-sessions)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=starlite-api_starlite-sessions&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=starlite-api_starlite-sessions)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=starlite-api_starlite-sessions&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=starlite-api_starlite-sessions)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=starlite-api_starlite-sessions&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=starlite-api_starlite-sessions)

[![Discord](https://img.shields.io/discord/919193495116337154?color=blue&label=chat%20on%20discord&logo=discord)](https://discord.gg/X3FJqy8d2j)
[![Matrix](https://img.shields.io/badge/%5Bm%5D%20chat%20on%20Matrix-bridged-blue)](https://matrix.to/#/#starlitespace:matrix.org)

</div>

This library offers simple session based authentication for [Starlite](https://github.com/starlite-api/starlite).

Checkout [the docs📚](https://starlite-api.github.io/starlite-sessions/).

## Installation

```shell
pip install starlite-sessions
```

## Example

```python
import os
from typing import Any, Optional, Literal

from pydantic import BaseModel, EmailStr, SecretStr
from starlite import OpenAPIConfig, Request, Starlite, get, post

from starlite_sessions import SessionAuth


# Let's assume we have a User model that is a pydantic model.
# This though is not required - we need some sort of user class -
# but it can be any arbitrary value, e.g. an SQLAlchemy model,
# a representation of a MongoDB  etc.
class User(BaseModel):
    id: str
    name: str
    email: EmailStr


# we also have pydantic types for two different
# kinds of POST request bodies: one for creating
# a user, e.g. "sign-up", and the other for logging
# an existing user in.
class UserCreatePayload(BaseModel):
    name: str
    email: EmailStr
    password: SecretStr


class UserLoginPayload(BaseModel):
    email: EmailStr
    password: SecretStr


# The SessionAuth class requires a handler callable
# that takes the session dictionary, and returns the
# 'User' instance correlating to it.
#
# The session dictionary itself is a value the user decides
# upon. So for example, it might be a simple dictionary
# that holds a user id, for example: { "user_id": "abcd123" }
#
# Note: The callable can be either sync or async - both will work.
async def retrieve_user_handler(session: dict[str, Any]) -> Optional[User]:
    # insert logic here to retrieve the user instance based on the session data.
    ...


# The minimal configuration required by the library is the
# callable for the 'retrieve_user_handler', and a bytes value for
# the secret used to encrypt the session cookie.
#
# Important: secrets should never be hardcoded, and its considered
# best practice to inject secrets via env.
#
# Important: the secret should be a 16, 24 or 32
# characters long byte string (128/192/256 bit).
#
# Tip: It's also a good idea to use the pydantic settings
# management functionality.
session_auth = SessionAuth(
    retrieve_user_handler=retrieve_user_handler,
    secret=os.environ.get("JWT_SECRET", os.urandom(16)),
    # exclude any URLs that should not have authentication.
    # We exclude the documentation URLs, signup and login.
    exclude=["/login", "/signup", "/schema"],
)


@post("/login")
async def login(data: UserLoginPayload, request: Request) -> User:
    # we received log-in data via post.
    # out login handler should retrieve from persistence (a db etc.)
    # the user data and verify that the login details
    # are correct. If we are using passwords, we should check that
    # the password hashes match etc. We will simply assume that we
    # have done all of that we now have a user value:
    user: User = ...

    # once verified we can create a session.
    # to do this we simply need to call the Starlite
    # 'Request.set_session' method, which accepts either dictionaries
    # or pydantic models. In our case, we can simply record a
    # simple dictionary with the user ID value:
    request.set_session({"user_id": user.id})

    # you can do whatever we want here. In this case, we will simply return the user data:
    return user


@post("/signup")
async def signup(data: UserCreatePayload, request: Request) -> User:
    # this is similar to the login handler, except here we should
    # insert into persistence - after doing whatever extra
    # validation we might require. We will assume that this is done,
    # and we now have a user instance with an assigned ID value:
    user: User = ...

    # we are creating a session the same as we do in the
    # 'login_handler' above:
    request.set_session({"user_id": user.id})

    # and again, you can add whatever logic is required here, we
    # will simply return the user:
    return user


# the endpoint below requires the user to be already authenticated
# to be able to access it.
@get("/user")
def get_user(request: Request[User, dict[Literal["user_id"], str]]) -> Any:
    # because this route requires authentication, we can access
    # `request.user`, which is the authenticated user returned
    # by the 'retrieve_user_handler' function we passed to SessionAuth.
    return request.user


# We add the session security schema to the OpenAPI config.
openapi_config = OpenAPIConfig(
    title="My API",
    version="1.0.0",
    components=[session_auth.openapi_components],
    security=[session_auth.security_requirement],
)

# We initialize the app instance, passing to it the
# 'jwt_auth.middleware' and the 'openapi_config'.
app = Starlite(
    route_handlers=[login, signup, get_user],
    middleware=[session_auth.middleware],
    openapi_config=openapi_config,
)
```

## Contributing

Starlite and all its official libraries are open to contributions big and small.

You can always [join our discord](https://discord.gg/X3FJqy8d2j) server
or [join our Matrix](https://matrix.to/#/#starlitespace:matrix.org) space to discuss contributions and project
maintenance. For guidelines on how to contribute to this library, please see `CONTRIBUTING.md` in the repository's root.
