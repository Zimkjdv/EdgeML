from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.dependencies import get_web_session_service, get_api_token_service, has_web_session
from app.services.web_session_service import WebSessionService

router = APIRouter(prefix='/api/auth/session', tags=['Web login'])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


def check_browser_request(request: Request, service: WebSessionService):
    origin = request.headers.get('origin')
    allowed = [str(request.base_url).rstrip('/'), *service.settings.web_allowed_origins]
    if request.headers.get('x-edgeml-login') != '1' or (origin and origin not in allowed):
        raise HTTPException(403, 'Untrusted browser request.')


@router.get('')
def session_status(response: Response, request: Request, service: WebSessionService = Depends(get_web_session_service)):
    response.headers['Cache-Control'] = 'no-store'
    session = service.authenticate(request.cookies.get('edgeml_session', ''))
    required = bool(service.settings.web_password or service.settings.api_token or get_api_token_service().has_active_tokens())
    return {'required': required, 'configured': bool(service.settings.web_password), 'authenticated': bool(session),
            'csrf_token': session['csrf'] if session else None,
            'username': service.settings.web_username if session else None}


@router.post('')
def login(body: LoginRequest, request: Request, response: Response, service: WebSessionService = Depends(get_web_session_service)):
    check_browser_request(request, service)
    try:
        token, csrf = service.login(body.username, body.password, request.client.host if request.client else 'unknown')
    except TimeoutError as exc:
        raise HTTPException(429, str(exc), headers={'Retry-After': '300'}) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    service.logout(request.cookies.get('edgeml_session', ''))
    response.set_cookie('edgeml_session', token, max_age=service.settings.web_session_seconds,
                        httponly=True, secure=service.settings.web_cookie_secure, samesite='strict', path='/api')
    response.headers['Cache-Control'] = 'no-store'
    return {'csrf_token': csrf, 'username': service.settings.web_username}


@router.delete('')
def logout(request: Request, response: Response, service: WebSessionService = Depends(get_web_session_service)):
    check_browser_request(request, service)
    has_web_session(request)  # Enforce CSRF when a live session exists.
    service.logout(request.cookies.get('edgeml_session', ''))
    response.delete_cookie('edgeml_session', path='/api', httponly=True,
                           secure=service.settings.web_cookie_secure, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok': True}
