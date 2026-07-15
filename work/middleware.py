# -*- coding: utf-8 -*-
"""
Detecta cuando el usuario abandona el flujo de asignacion (los 3 pasos en
work/asignar/*) hacia cualquier otra pantalla del sistema, para que al
volver a entrar al flujo el grupo de personas/maquinas que haya quedado de
una sesion anterior se limpie automaticamente.

No reemplaza la limpieza en si: eso lo sigue decidiendo cada vista de paso
(ver _clear_assignment_session en work/views.py), leyendo la bandera
'assignment_in_flow'. Este middleware solo mantiene esa bandera al dia,
apagandola apenas el usuario visita una URL fuera del flujo. Mientras se
quede dentro de cualquiera de los 3 pasos (o de los endpoints auxiliares
que esos pasos llaman via fetch/XHR, como escanear QR o quitar del grupo),
la bandera se mantiene encendida y el grupo no se toca.
"""
from django.urls import resolve, Resolver404

ASSIGNMENT_FLOW_URL_NAMES = {
    'work:assignment_new',
    'work:assignment_scan',
    'work:assignment_confirm',
    'work:scan_qr',
    'work:remove_from_group',
    'work:search_resources',
    'work:assignment_preload',
}


class AssignmentFlowGuardMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        session = getattr(request, 'session', None)
        if session is not None and 'assignment_in_flow' in session:
            try:
                match = resolve(request.path_info)
                url_name = f'{match.namespace}:{match.url_name}' if match.namespace else match.url_name
            except Resolver404:
                url_name = None

            if url_name not in ASSIGNMENT_FLOW_URL_NAMES:
                session['assignment_in_flow'] = False

        return response
