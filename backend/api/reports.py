"""Reports center endpoints."""

import io
import zipfile
from typing import Any, Optional
from uuid import UUID
import html

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.report import ReportRecord
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.reports import ReportCreate, ReportItem, ReportPage, ReportTemplateItem
from backend.services.reports import ReportService

router = APIRouter(
    prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _report_dict(record: ReportRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "category": record.category,
        "format": record.format,
        "status": record.status,
        "sections": record.sections,
        "scope": record.scope,
        "content": record.content,
        "error_message": record.error_message,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.get("/templates", response_model=list[ReportTemplateItem], responses={**_UNAUTHORIZED})
async def list_templates(session: AsyncSession = Depends(get_rls_db)) -> list[dict[str, Any]]:
    return ReportService(session).templates()


@router.post("", status_code=201, response_model=ReportItem, responses={**_UNAUTHORIZED})
async def create_report(
    body: ReportCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict[str, Any]:
    record = await ReportService(session).create(user_id=user.id, actor=actor, **body.model_dump())
    return _report_dict(record)


@router.get("", response_model=ReportPage, responses={**_UNAUTHORIZED})
async def list_reports(
    pagination: PageParams = Depends(page_params),
    category: Optional[str] = Query(
        default=None, pattern="^(executive|technical|compliance|incident)$"
    ),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = await ReportService(session).list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        category=category,
    )
    return {
        "items": [_report_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/{report_id}",
    response_model=ReportItem,
    responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED},
)
async def get_report(
    report_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _report_dict(await ReportService(session).get(report_id, user_id=user.id))


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _render_pdf_bytes(text: str) -> bytes:
    lines = [_pdf_escape(line[:100]) for line in text.splitlines()[:42]]
    stream_lines = ["BT", "/F1 11 Tf", "50 792 Td", "14 TL"]
    for line in lines:
        stream_lines.append(f"({line}) Tj")
        stream_lines.append("T*")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", "replace")
    page = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
    )
    content = (
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        page,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        content,
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n".encode("ascii"))
        out.write(obj)
        out.write(b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.write(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return out.getvalue()


def _render_docx_bytes(text: str) -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{html.escape(line) or ' '}</w:t></w:r></w:p>"
        for line in text.splitlines()
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}<w:sectPr><w:pgSz w:w=\"12240\" w:h=\"15840\"/></w:sectPr></w:body>"
        "</w:document>"
    )
    buf = io.BytesIO()
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types_xml)
        docx.writestr("_rels/.rels", rels_xml)
        docx.writestr("word/document.xml", document_xml)
    return buf.getvalue()


@router.get("/{report_id}/download", responses={404: {"model": ErrorResponse}, **_UNAUTHORIZED})
async def download_report(
    report_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    record = await ReportService(session).get(report_id, user_id=user.id)
    if record.format == "csv":
        body = record.content.encode("utf-8")
        media_type = "text/csv; charset=utf-8"
        extension = "csv"
    elif record.format == "pdf":
        body = _render_pdf_bytes(record.content)
        media_type = "application/pdf"
        extension = "pdf"
    elif record.format == "docx":
        body = _render_docx_bytes(record.content)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = "docx"
    else:
        body = record.content.encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    return Response(
        body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{record.title}.{extension}"'},
    )
