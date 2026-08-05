"""Excepción de dominio para fallos de la API REST de Superset. Aislada en su
propio módulo para que database.py/dashboard.py puedan lanzarla sin importar client.py."""


class SupersetError(Exception):
    pass
