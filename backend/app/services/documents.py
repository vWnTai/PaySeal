from __future__ import annotations

import io
from datetime import datetime

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from minio import Minio


def render_payment_pdf(
    *,
    organization: str,
    invoice: str,
    amount_minor: int,
    currency: str,
    beneficiary: str,
    bank_code: str,
    account_masked: str,
    request_id: str,
    verification_url: str,
    issued_at: datetime,
) -> bytes:
    output = io.BytesIO()
    qr_buffer = io.BytesIO()
    qrcode.make(verification_url).save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="PaySeal Payment Certificate",
        author="PaySeal",
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("PAYSEAL", styles["Title"]),
        Paragraph("Digitally verifiable payment request", styles["Heading2"]),
        Spacer(1, 8 * mm),
    ]
    rows = [
        ["Organization", organization],
        ["Invoice", invoice],
        ["Amount", f"{amount_minor:,} {currency}"],
        ["Beneficiary", beneficiary],
        ["Bank", bank_code],
        ["Account", account_masked],
        ["Request ID", request_id],
        ["Issued at", issued_at.isoformat()],
    ]
    table = Table(rows, colWidths=[40 * mm, 115 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8EEF8")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAB7CC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            table,
            Spacer(1, 10 * mm),
            Image(qr_buffer, width=42 * mm, height=42 * mm),
            Spacer(1, 3 * mm),
            Paragraph(verification_url, styles["BodyText"]),
            Paragraph(
                "Verify the QR before acting. PaySeal does not transfer funds.",
                styles["Italic"],
            ),
        ]
    )
    document.build(story)
    return output.getvalue()


class MinioStorage:
    def __init__(self) -> None:
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(settings.minio_bucket):
            self.client.make_bucket(settings.minio_bucket)

    def put_pdf(self, object_key: str, data: bytes) -> None:
        self.ensure_bucket()
        self.client.put_object(
            settings.minio_bucket,
            object_key,
            io.BytesIO(data),
            len(data),
            content_type="application/pdf",
        )

    def get_pdf(self, object_key: str) -> bytes:
        response = self.client.get_object(settings.minio_bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
