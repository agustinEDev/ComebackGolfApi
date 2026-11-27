"""
Subir a la galería una foto cortada da 400, no 500 (AV1).

La foto de galería (módulo social) pasa por el mismo procesador que el avatar: un
JPEG que se quedó a medias tiene la cabecera bien y solo falla al decodificar sus
píxeles, que ocurría fuera del control de errores.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import create_authenticated_user, set_auth_cookies
from tests.imagenes_de_prueba import cortada


@pytest.mark.asyncio
async def test_subir_foto_de_galeria_jpeg_cortado_da_400(client: AsyncClient):
    """
    AV1.
    Given un JPEG cortado al 33 % (una subida que se quedó a medias)
    When se sube a la galería del perfil
    Then 400 «no es una imagen válida», no 500, y la galería sigue vacía
    """
    user = await create_authenticated_user(
        client, "galeria_cortada@test.com", "P@ssw0rd123!", "Galeria", "Cortada"
    )
    set_auth_cookies(client, user["cookies"])

    response = await client.post(
        "/api/v1/users/me/photos",
        files={"file": ("foto.jpg", cortada("JPEG", 0.33), "image/jpeg")},
    )

    assert response.status_code == 400
    assert "no es una imagen válida" in response.text
    galeria = await client.get(f"/api/v1/users/{user['user']['id']}/photos")
    assert galeria.status_code == 200
    assert galeria.json()["photos"] == []
