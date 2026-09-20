"""HTTP and Web abstraction module for Khaira framework."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Cookie,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    Security,
    status,
)

# First-class alias for APIRouter
Router = APIRouter

__all__ = [
    # Router
    "Router",
    "APIRouter",
    # Dependencies & Security
    "Depends",
    "Security",
    "BackgroundTasks",
    # Status & Exceptions
    "status",
    "HTTPException",
    # Request & Response
    "Request",
    "Response",
    # Route parameters & bodies
    "Query",
    "Path",
    "Body",
    "Header",
    "Cookie",
    "File",
    "Form",
]
