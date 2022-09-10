from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Union,
    cast,
)

from pydantic import validator
from pydantic_openapi_schema.v3_1_0 import (
    Components,
    SecurityRequirement,
    SecurityScheme,
)
from starlite.exceptions import NotAuthorizedException
from starlite.middleware import ExceptionHandlerMiddleware
from starlite.middleware.authentication import (
    AbstractAuthenticationMiddleware,
    AuthenticationResult,
)
from starlite.middleware.base import DefineMiddleware, MiddlewareProtocol
from starlite.middleware.session import SessionCookieConfig, SessionMiddleware
from starlite.types import Empty, SyncOrAsyncUnion
from starlite.utils import AsyncCallable

if TYPE_CHECKING:  # pragma: no cover
    from starlette.requests import HTTPConnection
    from starlite.app import Starlite
    from starlite.types import ASGIApp, Receive, Scope, Send


RetrieveUserHandler = Callable[[Dict[str, Any]], SyncOrAsyncUnion[Any]]


class SessionAuth(SessionCookieConfig):
    retrieve_user_handler: RetrieveUserHandler
    """
    Callable that receives the session dictionary after it has been decoded and returns a 'user' value.

    Notes:
    - User can be any arbitrary value,
    - The callable can be sync or async.
    """
    exclude: Optional[Union[str, List[str]]] = None
    """
    A pattern or list of patterns to skip in the authentication middleware.
    """
    openapi_security_scheme_name: str = "sessionCookie"
    """
    The value to use for the OpenAPI security scheme and security requirements
    """

    @validator("retrieve_user_handler")
    def validate_retrieve_user_handler(  # pylint: disable=no-self-argument
        cls, value: RetrieveUserHandler
    ) -> Callable[[Dict[str, Any]], Awaitable[Any]]:
        """This validator ensures that the passed in value does not get bound.

        Args:
            value: A callable fulfilling the RetrieveUserHandler type.

        Returns:
            An instance of AsyncCallable wrapping the callable.
        """
        return AsyncCallable(value)

    @property
    def middleware(self) -> DefineMiddleware:
        """Use this property to insert the config into a middleware list on one
        of the application layers.

        Examples:

            ```python
            from typing import Any
            from os import urandom

            from starlite import Starlite, Request, get
            from starlite_session import SessionAuth


            async def retrieve_user_from_session(session: dict[str, Any]) -> Any:
                # implement logic here to retrieve a 'user' datum given the session dictionary
                ...


            session_auth_config = SessionAuth(
                secret=urandom(16), retrieve_user_handler=retrieve_user_from_session
            )


            @get("/")
            def my_handler(request: Request) -> None:
                ...


            app = Starlite(route_handlers=[my_handler], middleware=[session_auth_config.middleware])
            ```

        Returns:
            An instance of DefineMiddleware including 'self' as the config kwarg value.
        """
        return DefineMiddleware(MiddlewareWrapper, config=self)

    @property
    def openapi_components(self) -> Components:
        """Creates OpenAPI documentation for the Session Authentication schema
        used.

        Returns:
            An [Components][pydantic_schema_pydantic.v3_1_0.components.Components] instance.
        """
        return Components(
            securitySchemes={
                self.openapi_security_scheme_name: SecurityScheme(
                    type="apiKey",
                    name="Set-Cookie",
                    security_scheme_in="cookie",  # pyright: ignore
                    description="Session cookie authentication.",
                )
            }
        )

    @property
    def security_requirement(self) -> SecurityRequirement:
        """
        Returns:
            An OpenAPI 3.1 [SecurityRequirement][pydantic_schema_pydantic.v3_1_0.security_requirement.SecurityRequirement] dictionary.
        """
        return {self.openapi_security_scheme_name: []}


class MiddlewareWrapper(MiddlewareProtocol):
    def __init__(self, app: "ASGIApp", config: SessionAuth):
        """This class creates a small stack of middlewares: It wraps the
        SessionAuthMiddleware inside ExceptionHandlerMiddleware, and it wraps
        this inside SessionMiddleware. This allows the auth middleware to raise
        exceptions and still have the response handled, while having the
        session cleared.

        Args:
            app: An ASGIApp, this value is the next ASGI handler to call in the middleware stack.
            config: An instance of SessionAuth
        """
        super().__init__(app)
        self.app = app
        self.has_wrapped_middleware = False
        self.config = config

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        """This is the entry point to the middleware. If
        'self.had_wrapped_middleware' is False, the wrapper will update the
        value of 'self.app' to be the middleware stack described in the
        __init__ method. Otherwise, it will call the next ASGI handler.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive function.
            send: The ASGI send function.

        Returns:
            None
        """
        if not self.has_wrapped_middleware:
            starlite_app = cast("Starlite", scope["app"])
            auth_middleware = SessionAuthMiddleware(
                app=self.app,
                exclude=self.config.exclude,
                retrieve_user_handler=cast("Callable[[Dict[str, Any]], Awaitable[Any]]", self.config.retrieve_user_handler),  # type: ignore
            )
            exception_middleware = ExceptionHandlerMiddleware(
                app=auth_middleware,
                exception_handlers=starlite_app.exception_handlers or {},
                debug=starlite_app.debug,
            )
            self.app = SessionMiddleware(app=exception_middleware, config=self.config)
            self.has_wrapped_middleware = True
        await self.app(scope, receive, send)


class SessionAuthMiddleware(AbstractAuthenticationMiddleware):
    def __init__(
        self,
        app: "ASGIApp",
        exclude: Optional[Union[str, List[str]]],
        retrieve_user_handler: Callable[[Dict[str, Any]], Awaitable[Any]],
    ):
        """A Starlite Authentication Middleware that uses session cookies.

        Args:
            app: An ASGIApp, this value is the next ASGI handler to call in the middleware stack.
            exclude: A pattern or list of patterns to skip in the authentication middleware.
            retrieve_user_handler: A callable that receives the session dictionary after it has been decoded and returns
                a 'user' value.
        """
        super().__init__(app=app, exclude=exclude)
        self.retrieve_user_handler = retrieve_user_handler

    async def authenticate_request(self, connection: "HTTPConnection") -> AuthenticationResult:
        """Implementation of the authentication method specified by Starlite's.

        [AbstractAuthenticationMiddleware][starlite.middleware.authentication.AbstractAuthenticationMiddleware].

        Args:
            connection: A Starlette 'HTTPConnection' instance.

        Raises:
            [NotAuthorizedException][starlite.exceptions.NotAuthorizedException]: if session data is empty or user
                is not found.

        Returns:
            [AuthenticationResult][starlite.middleware.authentication.AuthenticationResult]
        """
        if not connection.session or connection.session is Empty:  # type: ignore
            # the assignment of 'Empty' forces the session middleware to clear session data.
            connection.scope["session"] = Empty
            raise NotAuthorizedException("no session data found")

        user = await self.retrieve_user_handler(connection.session)

        if not user:
            connection.scope["session"] = Empty
            raise NotAuthorizedException("no user correlating to session found")

        return AuthenticationResult(user=user, auth=connection.session)
