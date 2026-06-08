# -*- coding: utf-8 -*-
"""
Vista para descarga masiva de QRs en PDF.
Genera un PDF con grilla 3x3 (9 QRs por hoja carta).
Cada celda incluye QR + nombre + cargo + RUT/codigo.
"""
import io
import qrcode
from qrcode.image.pure import PyPNGImage

from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from companies.models import SiteMembership
from resources.models import Resource, ResourceSiteAssignment
from core.permissions import user_has_permission


def get_active_site(request):
    try:
        return request.user.preference.last_site
    except Exception:
        return None


@login_required
@require_POST
def download_qr_pdf(request):
    """
    Genera un PDF con QRs de los recursos seleccionados.
    Recibe una lista de resource_ids via POST.
    Layout: 3 columnas x 3 filas por hoja carta.
    """
    site = get_active_site(request)
    if not site:
        return JsonResponse({'error': 'Sin obra activa.'}, status=400)

    if not user_has_permission(request.user, 'resources.view_qr', site):
        return JsonResponse({'error': 'Sin permiso.'}, status=403)

    # Obtener IDs seleccionados
    resource_ids = request.POST.getlist('resource_ids[]')
    if not resource_ids:
        resource_ids = request.POST.getlist('resource_ids')

    if not resource_ids:
        return JsonResponse({'error': 'No seleccionaste ningún trabajador.'}, status=400)

    # Filtrar recursos activos asignados a esta obra
    resources = Resource.objects.filter(
        id__in=resource_ids,
        company=site.company,
        status='ACTIVE',
        site_assignments__site=site,
        site_assignments__status='ACTIVE',
    ).select_related('job_title', 'resource_category').distinct()

    if not resources:
        return JsonResponse({'error': 'No se encontraron recursos válidos.'}, status=400)

    # Generar PDF
    pdf_buffer = _generate_qr_pdf(resources, site, request)

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="QRs_{site.code}.pdf"'
    return response


def _generate_qr_image(url):
    """Genera imagen QR como bytes PNG."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def _generate_qr_pdf(resources, site, request):
    """
    Genera PDF con grilla 3x3 de QRs en hoja carta.

    Dimensiones carta: 21.59 x 27.94 cm
    Margen: 1 cm por lado
    Area util: 19.59 x 25.94 cm
    Celda: 6.53 x 8.64 cm (3 columnas, 3 filas)
    QR dentro de celda: 5 cm x 5 cm centrado
    """
    buf = io.BytesIO()

    page_w, page_h = letter  # 612 x 792 puntos

    c = canvas.Canvas(buf, pagesize=letter)

    # ── Dimensiones de la grilla ──────────────────────────────────────────
    COLS        = 3
    ROWS        = 3
    CELLS_PAGE  = COLS * ROWS  # 9 por hoja

    margin_x    = 1.2 * cm
    margin_y    = 1.2 * cm
    cell_w      = (page_w - 2 * margin_x) / COLS
    cell_h      = (page_h - 2 * margin_y) / ROWS

    qr_size     = min(cell_w, cell_h) * 0.58  # QR ocupa ~58% de la celda
    text_area_h = cell_h - qr_size - 0.4 * cm

    resources_list = list(resources)
    total          = len(resources_list)

    for i, resource in enumerate(resources_list):
        page_pos = i % CELLS_PAGE

        if page_pos == 0 and i > 0:
            c.showPage()

        col = page_pos % COLS
        row = page_pos // COLS

        # Origen de la celda (esquina inferior izquierda en ReportLab)
        cell_x = margin_x + col * cell_w
        cell_y = page_h - margin_y - (row + 1) * cell_h

        # ── Borde de celda ────────────────────────────────────────────────
        c.setStrokeColorRGB(0.88, 0.88, 0.88)
        c.setLineWidth(0.5)
        c.rect(cell_x, cell_y, cell_w, cell_h)

        # ── QR ────────────────────────────────────────────────────────────
        qr_url = request.build_absolute_uri(f'/r/{resource.resource_uid}/')
        qr_buf = _generate_qr_image(qr_url)
        qr_img = ImageReader(qr_buf)

        qr_x = cell_x + (cell_w - qr_size) / 2
        qr_y = cell_y + text_area_h + 0.15 * cm

        c.drawImage(qr_img, qr_x, qr_y, qr_size, qr_size, preserveAspectRatio=True)

        # ── Nombre del trabajador ─────────────────────────────────────────
        name = resource.display_name
        # Truncar si es muy largo
        if len(name) > 24:
            name = name[:22] + '…'

        c.setFont('Helvetica-Bold', 7.5)
        c.setFillColorRGB(0.07, 0.11, 0.28)  # --ni-dark
        name_y = qr_y - 0.45 * cm
        c.drawCentredString(cell_x + cell_w / 2, name_y, name)

        # ── Cargo ─────────────────────────────────────────────────────────
        cargo = resource.job_title.name if resource.job_title else ''
        if len(cargo) > 26:
            cargo = cargo[:24] + '…'

        c.setFont('Helvetica', 6.5)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        cargo_y = name_y - 0.35 * cm
        c.drawCentredString(cell_x + cell_w / 2, cargo_y, cargo)

        # ── RUT o código interno ──────────────────────────────────────────
        identifier = resource.person_rut or resource.internal_code or ''
        if identifier:
            c.setFont('Courier', 6)
            c.setFillColorRGB(0.55, 0.55, 0.55)
            id_y = cargo_y - 0.3 * cm
            c.drawCentredString(cell_x + cell_w / 2, id_y, identifier)

    c.save()
    buf.seek(0)
    return buf
