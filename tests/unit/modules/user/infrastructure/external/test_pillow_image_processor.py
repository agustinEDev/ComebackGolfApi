"""
Tests para PillowImageProcessor (procesado real con Pillow, sin mocks).
"""

import io

import pytest
from PIL import Image, PngImagePlugin

from src.modules.user.domain.errors.user_errors import InvalidAvatarImageError
from src.modules.user.infrastructure.external.pillow_image_processor import (
    AVATAR_TARGET_SIZE,
    GALLERY_MAX_SIDE,
    PillowImageProcessor,
)
from tests.imagenes_de_prueba import (
    apng,
    apng_cortado,
    con_ruido,
    con_un_byte_cambiado,
    cortada,
    guardada,
)


def _make_test_image_bytes(width: int, height: int, fmt: str = "JPEG") -> bytes:
    image = Image.new("RGB", (width, height), color=(10, 200, 50))
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return buffer.getvalue()


class TestPillowImageProcessor:
    async def test_processes_landscape_image_to_square_jpeg(self):
        processor = PillowImageProcessor()
        raw_bytes = _make_test_image_bytes(800, 400)

        result = await processor.process_avatar_image(raw_bytes)

        output_image = Image.open(io.BytesIO(result))
        assert output_image.format == "JPEG"
        assert output_image.size == (AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE)

    async def test_processes_portrait_png_to_square_jpeg(self):
        processor = PillowImageProcessor()
        raw_bytes = _make_test_image_bytes(300, 600, fmt="PNG")

        result = await processor.process_avatar_image(raw_bytes)

        output_image = Image.open(io.BytesIO(result))
        assert output_image.format == "JPEG"
        assert output_image.size == (AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE)

    async def test_rejects_non_image_bytes(self):
        processor = PillowImageProcessor()

        with pytest.raises(InvalidAvatarImageError):
            await processor.process_avatar_image(b"this is definitely not an image")

    async def test_rejects_unsupported_format(self):
        processor = PillowImageProcessor()
        image = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        image.save(buffer, "BMP")

        with pytest.raises(InvalidAvatarImageError):
            await processor.process_avatar_image(buffer.getvalue())

    async def test_corrects_exif_orientation_before_cropping(self):
        """
        Una foto tomada en vertical con el móvil se guarda con los píxeles
        "en crudo" en una orientación y un tag EXIF que indica cómo rotarla
        para verse bien. Sin aplicar ese tag, el avatar saldría girado.
        """
        processor = PillowImageProcessor()
        image = Image.new("RGB", (400, 400))
        image.paste(Image.new("RGB", (400, 200), color=(255, 0, 0)), (0, 0))
        image.paste(Image.new("RGB", (400, 200), color=(0, 0, 255)), (0, 200))

        exif = image.getexif()
        exif[0x0112] = 3  # Orientation: rotar 180°

        buffer = io.BytesIO()
        image.save(buffer, "JPEG", exif=exif)

        result = await processor.process_avatar_image(buffer.getvalue())

        output_image = Image.open(io.BytesIO(result)).convert("RGB")
        top_left = output_image.getpixel((5, 5))
        # Tras corregir una orientación de 180°, lo que era la mitad "azul"
        # (almacenada abajo) pasa a quedar arriba.
        assert top_left[2] > top_left[0]

    async def test_rejects_image_exceeding_max_pixel_count(self, monkeypatch):
        """Protección contra 'decompression bombs': un archivo pequeño que
        declara dimensiones absurdas debe rechazarse antes de decodificarse."""
        import src.modules.user.infrastructure.external.pillow_image_processor as module

        monkeypatch.setattr(module, "MAX_JPEG_INPUT_PIXELS", 100)
        processor = PillowImageProcessor()
        raw_bytes = _make_test_image_bytes(50, 50)  # 2500 px > 100 px (límite fingido)

        with pytest.raises(InvalidAvatarImageError):
            await processor.process_avatar_image(raw_bytes)


class TestHeicFromAnIPhonePhotoLibrary:
    """
    Las fotos de la fototeca de un iPhone son HEIC (BE #232).

    Pillow no lo lee por su cuenta, así que la subida moría con «no es una
    imagen válida» y desde un iPhone solo se podía poner avatar haciendo una
    foto nueva: la cámara del navegador entrega JPEG y la fototeca entrega el
    HEIC original.
    """

    @staticmethod
    def _heic_bytes(width: int, height: int, exif: Image.Exif | None = None) -> bytes:
        image = Image.new("RGB", (width, height), color=(10, 200, 50))
        buffer = io.BytesIO()
        image.save(buffer, "HEIF", exif=exif.tobytes() if exif else None)
        return buffer.getvalue()

    async def test_processes_a_heic_photo_to_square_jpeg(self):
        """
        Given una foto HEIC como las que guarda un iPhone
        When se procesa como avatar
        Then sale el mismo JPEG cuadrado que con cualquier otro formato
        """
        processor = PillowImageProcessor()

        result = await processor.process_avatar_image(self._heic_bytes(800, 400))

        output_image = Image.open(io.BytesIO(result))
        assert output_image.format == "JPEG"
        assert output_image.size == (AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE)

    async def test_processes_a_heic_photo_for_the_gallery(self):
        """La subida de foto de perfil comparte la validación, así que también entra."""
        processor = PillowImageProcessor()

        result = await processor.process_gallery_image(self._heic_bytes(400, 300))

        assert Image.open(io.BytesIO(result)).format == "JPEG"

    async def test_pillow_identifies_heic_as_heif(self):
        """
        El nombre del formato es lo que decide si se acepta, y Pillow llama
        «HEIF» a un HEIC. Poner «HEIC» en la lista no habría servido de nada.
        """
        assert Image.open(io.BytesIO(self._heic_bytes(60, 60))).format == "HEIF"

    async def test_does_not_rotate_a_heic_twice(self):
        """
        pillow-heif ya entrega la imagen girada y con el tag EXIF a 1, así que
        `exif_transpose` no debe volver a girarla. Si alguna versión futura
        cambiara eso, las fotos verticales de iPhone saldrían tumbadas.
        """
        exif = Image.Exif()
        exif[274] = 6  # girar 90º
        raw = self._heic_bytes(400, 300, exif=exif)

        decoded = Image.open(io.BytesIO(raw))

        assert decoded.size == (300, 400), "pillow-heif debería entregarla ya girada"
        assert decoded.getexif().get(274) in (None, 1), "y con la orientación ya consumida"

    async def test_still_rejects_a_format_that_is_not_allowed(self):
        """Aceptar HEIC no abre la puerta a cualquier cosa."""
        processor = PillowImageProcessor()
        buffer = io.BytesIO()
        Image.new("RGB", (100, 100)).save(buffer, "BMP")

        with pytest.raises(InvalidAvatarImageError):
            await processor.process_avatar_image(buffer.getvalue())

    async def test_still_rejects_a_heic_over_the_pixel_limit(self, monkeypatch):
        """
        El tope de píxeles protege de una bomba de descompresión y tiene que
        seguir aplicando al formato nuevo, no solo a los de antes.
        """
        from src.modules.user.infrastructure.external import pillow_image_processor

        monkeypatch.setattr(pillow_image_processor, "MAX_INPUT_PIXELS", 100)
        processor = PillowImageProcessor()

        with pytest.raises(InvalidAvatarImageError, match="demasiado grande"):
            await processor.process_avatar_image(self._heic_bytes(200, 200))


class TestTopesDePixelesYDecodificacionReducida:
    """
    SB-01: un archivo pequeño puede declarar muchísimos píxeles y llevarse cientos
    de megas al decodificarse. El JPEG se decodifica ya reducido al tamaño de salida
    (`Image.draft`), así que su tope es de 50 MP; el resto de formatos se
    decodifica entero y tiene un tope más bajo.
    """

    @staticmethod
    def _png_de_un_bit(width: int, height: int) -> bytes:
        """Un PNG de 1 bit por píxel: muchos píxeles con poca memoria en el test."""
        buffer = io.BytesIO()
        Image.new("1", (width, height)).save(buffer, "PNG")
        return buffer.getvalue()

    @staticmethod
    def _jpeg_gris(width: int, height: int) -> bytes:
        buffer = io.BytesIO()
        Image.new("L", (width, height), 128).save(buffer, "JPEG")
        return buffer.getvalue()

    @staticmethod
    def _jpeg_que_declara(width: int, height: int) -> bytes:
        """
        Un JPEG pequeño con otras dimensiones en la cabecera (SOF0): Pillow solo lee la
        cabecera para saber el tamaño, así que se prueba el tope sin crear la imagen.
        """
        buffer = io.BytesIO()
        Image.new("L", (16, 16), 128).save(buffer, "JPEG")
        datos = bytearray(buffer.getvalue())
        sof = datos.index(b"\xff\xc0")
        datos[sof + 5 : sof + 9] = height.to_bytes(2, "big") + width.to_bytes(2, "big")
        return bytes(datos)

    async def test_una_foto_de_48_megapixeles_entra_en_jpeg(self):
        """
        Given un JPEG de 8064x6048 (una foto de 48 MP de iPhone: 48,8 MP)
        When se procesa
        Then entra: decodificado ya reducido, cabe bajo el tope del JPEG (50 MP)
        """
        processor = PillowImageProcessor()

        result = await processor.process_avatar_image(self._jpeg_gris(8064, 6048))

        assert Image.open(io.BytesIO(result)).size == (AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE)

    async def test_rechaza_un_jpeg_por_encima_de_50_megapixeles(self):
        """
        Given un JPEG que declara 8165x6124 (50,003 MP)
        When se procesa
        Then se rechaza por grande, sin decodificarlo
        """
        processor = PillowImageProcessor()

        with pytest.raises(InvalidAvatarImageError, match="demasiado grande"):
            await processor.process_gallery_image(self._jpeg_que_declara(8165, 6124))

    async def test_un_jpeg_justo_en_el_tope_no_se_rechaza_por_grande(self):
        """
        Given un JPEG que declara 10000x5000 (50 MP justos), con datos de 16x16
        When se procesa
        Then no se rechaza por grande (lo que salga de unos datos de 16x16 da igual aquí)
        """
        processor = PillowImageProcessor()

        try:
            await processor.process_gallery_image(self._jpeg_que_declara(10000, 5000))
        except InvalidAvatarImageError as error:
            assert "demasiado grande" not in str(error)

    async def test_rechaza_un_jpeg_panoramico_que_no_se_puede_reducir_para_el_avatar(self):
        """
        Given un JPEG de 50000x1000 (50 MP, dentro del tope) para el avatar
        When se procesa
        Then se rechaza por grande: con el lado corto por debajo de 1024, draft no
        reduce nada y se decodificaría entero (cientos de megas)
        """
        processor = PillowImageProcessor()

        with pytest.raises(InvalidAvatarImageError, match="demasiado grande"):
            await processor.process_avatar_image(self._jpeg_que_declara(50000, 1000))

    async def test_el_mismo_panoramico_en_la_galeria_si_se_reduce(self):
        """
        Given el mismo JPEG de 50000x1000 en la galería (manda el lado largo)
        When se procesa
        Then no se rechaza por grande: draft lo reduce a 1/8
        """
        processor = PillowImageProcessor()

        try:
            await processor.process_gallery_image(self._jpeg_que_declara(50000, 1000))
        except InvalidAvatarImageError as error:
            assert "demasiado grande" not in str(error)

    async def test_un_avatar_que_draft_reduce_bajo_el_tope_no_se_rechaza(self):
        """Given un JPEG de 12000x4000 (48 MP) / Then draft lo baja a 3 MP y no es «grande»."""
        processor = PillowImageProcessor()

        try:
            await processor.process_avatar_image(self._jpeg_que_declara(12000, 4000))
        except InvalidAvatarImageError as error:
            assert "demasiado grande" not in str(error)

    async def test_rechaza_un_png_por_encima_del_tope_de_los_demas_formatos(self):
        """
        Given un PNG de 5001x5000 (25,005 MP), que se decodificaría entero
        When se procesa
        Then se rechaza por grande, sin llegar a decodificarlo
        """
        processor = PillowImageProcessor()

        with pytest.raises(InvalidAvatarImageError, match="demasiado grande"):
            await processor.process_gallery_image(self._png_de_un_bit(5001, 5000))

    async def test_acepta_una_foto_de_24_megapixeles_de_camara(self):
        """
        Given una imagen de 5712x4284 (lo que guarda un iPhone de 24 MP: 24,47 MP reales)
        When se procesa en un formato que no es JPEG
        Then entra: el tope de los demás formatos no deja fuera las fotos de 24 MP
        """
        processor = PillowImageProcessor()

        result = await processor.process_avatar_image(self._png_de_un_bit(5712, 4284))

        assert Image.open(io.BytesIO(result)).size == (AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE)

    async def test_un_jpeg_por_encima_del_tope_de_los_demas_formatos_entra(self):
        """
        Given un JPEG de 30 MP (por encima del tope de PNG/HEIC/WEBP y por debajo del suyo)
        When se procesa
        Then entra, como hasta ahora
        """
        processor = PillowImageProcessor()

        result = await processor.process_gallery_image(self._jpeg_gris(6000, 5000))

        assert Image.open(io.BytesIO(result)).size == (GALLERY_MAX_SIDE, 900)

    @pytest.mark.parametrize(
        ("metodo", "ancho", "alto", "se_reduce", "minimo_corto", "minimo_largo"),
        [
            ("process_avatar_image", 4000, 3000, True, AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE),
            # Panorámica: el lado CORTO es el que da el cuadrado del avatar
            ("process_avatar_image", 6000, 1000, False, AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE),
            ("process_gallery_image", 4000, 3000, True, 0, GALLERY_MAX_SIDE),
        ],
    )
    async def test_el_jpeg_se_decodifica_ya_reducido_al_tamano_de_salida(
        self, monkeypatch, metodo, ancho, alto, se_reduce, minimo_corto, minimo_largo
    ):
        """
        Given un JPEG más grande que la salida
        When se procesa
        Then se pide a Pillow decodificarlo reducido (draft), y nunca por debajo de
        lo que necesita la salida
        """
        from PIL import JpegImagePlugin

        tamanos_decodificados: list[tuple[int, int]] = []
        draft_original = JpegImagePlugin.JpegImageFile.draft

        def draft_espiado(self, mode, size):
            resultado = draft_original(self, mode, size)
            tamanos_decodificados.append(self.size)
            return resultado

        monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", draft_espiado)
        processor = PillowImageProcessor()

        await getattr(processor, metodo)(_make_test_image_bytes(ancho, alto))

        assert tamanos_decodificados, "el JPEG se decodificó sin pedir el tamaño de salida"
        decodificado_ancho, decodificado_alto = tamanos_decodificados[-1]
        assert (decodificado_ancho * decodificado_alto < ancho * alto) == se_reduce
        assert min(decodificado_ancho, decodificado_alto) >= minimo_corto
        assert max(decodificado_ancho, decodificado_alto) >= minimo_largo


class TestJpegConMapaDeGananciaHdr:
    """
    Los JPEG del iPhone con mapa de ganancia HDR llevan dos imágenes: Pillow los abre
    como «MPO» (subclase de su JPEG). Se tratan como JPEG: admitidos, tope de 50 MP y
    decodificados ya reducidos. Sale la primera imagen, en JPEG, como siempre.
    """

    @staticmethod
    def _mpo(width: int, height: int, mode: str = "RGB") -> bytes:
        principal = Image.new(mode, (width, height), 200 if mode == "L" else (200, 30, 30))
        mapa = Image.new(mode, (max(1, width // 4), max(1, height // 4)))
        buffer = io.BytesIO()
        principal.save(buffer, "MPO", save_all=True, append_images=[mapa])
        return buffer.getvalue()

    def test_pillow_lo_abre_como_mpo(self):
        assert Image.open(io.BytesIO(self._mpo(64, 48))).format == "MPO"

    async def test_entra_y_sale_la_primera_imagen_en_jpeg(self):
        """Given un MPO de dos imágenes / When se procesa / Then JPEG con la primera."""
        processor = PillowImageProcessor()

        result = await processor.process_gallery_image(self._mpo(400, 300))

        salida = Image.open(io.BytesIO(result))
        assert salida.format == "JPEG"
        assert salida.size == (400, 300)
        assert salida.convert("RGB").getpixel((10, 10))[0] > 150

    async def test_tiene_el_tope_del_jpeg_y_no_el_de_los_demas(self):
        """Given un MPO de 30 MP (por encima de 25, por debajo de 50) / Then entra."""
        processor = PillowImageProcessor()

        result = await processor.process_avatar_image(self._mpo(6000, 5000, mode="L"))

        assert Image.open(io.BytesIO(result)).size == (AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE)

    async def test_se_decodifica_ya_reducido(self, monkeypatch):
        """Given un MPO de 4000x3000 / When se procesa / Then se pide reducido (draft)."""
        from PIL import JpegImagePlugin

        tamanos: list[tuple[int, int]] = []
        draft_original = JpegImagePlugin.JpegImageFile.draft

        def draft_espiado(self, mode, size):
            resultado = draft_original(self, mode, size)
            tamanos.append(self.size)
            return resultado

        monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", draft_espiado)

        await PillowImageProcessor().process_avatar_image(self._mpo(4000, 3000))

        assert tamanos and tamanos[-1][0] * tamanos[-1][1] < 4000 * 3000


PROCESOS = ["process_avatar_image", "process_gallery_image"]


class TestImagenCortadaODanada:
    """
    Un archivo cortado (una subida que se quedó a medias) o con un chunk dañado no es
    una imagen válida: 400, nunca 500.

    Un JPEG o un HEIC cortados tienen la cabecera bien, se abren y pasan `verify()`, y
    solo fallan al decodificar los píxeles (`load()`). Un PNG con un chunk dañado lo
    para `verify()` con un `SyntaxError`. Ninguno estaba dentro del control de errores.
    """

    @pytest.mark.parametrize("fraccion", [0.33, 0.8])
    @pytest.mark.parametrize("proceso", PROCESOS)
    async def test_procesar_jpeg_cortado_es_imagen_no_valida(self, proceso, fraccion):
        """
        AV1.
        Given un JPEG cortado al 33 % o al 80 %
        When se procesa como avatar o como foto de galería
        Then se rechaza como imagen no válida (400), no revienta (500)
        """
        procesar = getattr(PillowImageProcessor(), proceso)

        with pytest.raises(InvalidAvatarImageError, match="no es una imagen válida"):
            await procesar(cortada("JPEG", fraccion))

    @pytest.mark.parametrize("fraccion", [0.33, 0.8])
    @pytest.mark.parametrize("proceso", PROCESOS)
    async def test_procesar_heic_cortado_es_imagen_no_valida(self, proceso, fraccion):
        """
        AV2.
        Given un HEIC cortado al 33 % o al 80 % (pillow-heif falla al decodificarlo)
        When se procesa como avatar o como foto de galería
        Then se rechaza con el mismo «no es una imagen válida»
        """
        procesar = getattr(PillowImageProcessor(), proceso)

        with pytest.raises(InvalidAvatarImageError, match="no es una imagen válida"):
            await procesar(cortada("HEIF", fraccion))

    @pytest.mark.parametrize(
        "danado",
        [
            pytest.param(
                lambda: con_un_byte_cambiado(guardada(con_ruido(200, 150), "PNG"), b"IDAT"),
                id="png-idat",
            ),
            pytest.param(
                lambda: con_un_byte_cambiado(apng(), b"fcTL", aparicion=2), id="apng-fctl"
            ),
        ],
    )
    @pytest.mark.parametrize("proceso", PROCESOS)
    async def test_procesar_png_con_chunk_danado_es_imagen_no_valida(self, proceso, danado):
        """
        AV2.
        Given un PNG con un byte cambiado en IDAT, o un APNG con uno cambiado en fcTL
        When se procesa como avatar o como foto de galería
        Then se rechaza con el mismo «no es una imagen válida» (`verify()` lanza SyntaxError)
        """
        procesar = getattr(PillowImageProcessor(), proceso)

        with pytest.raises(InvalidAvatarImageError, match="no es una imagen válida"):
            await procesar(danado())


def _roja_arriba_azul_abajo() -> Image.Image:
    """80x60, roja arriba y azul abajo: girada se vería otro color arriba u otro tamaño."""
    imagen = Image.new("RGB", (80, 60), (0, 0, 255))
    imagen.paste(Image.new("RGB", (80, 30), (255, 0, 0)), (0, 0))
    return imagen


def _con_exif_en_texto(texto: str) -> bytes:
    """Un PNG que trae el EXIF como texto, como lo escriben ImageMagick y otros."""
    info = PngImagePlugin.PngInfo()
    info.add_text("Raw profile type exif", texto)
    return guardada(_roja_arriba_azul_abajo(), "PNG", pnginfo=info)


ARCHIVOS_CON_EXIF_ILEGIBLE = [
    pytest.param(
        lambda formato=formato, exif=exif: guardada(_roja_arriba_azul_abajo(), formato, exif=exif),
        id=f"{formato}-{nombre}",
    )
    for formato in ("PNG", "WEBP")
    for nombre, exif in (("no-es-tiff", b"no es TIFF"), ("tiff-cortado", b"II*\x00"))
] + [
    pytest.param(lambda: _con_exif_en_texto("\nexif\n1\nzz\n"), id="PNG-texto-no-hexadecimal"),
]


class TestImagenConExifIlegible:
    """
    Un EXIF que no se puede leer se ignora y la foto entra sin girar, como hacen los
    navegadores (decisión de Agustín, 24 nov 2026). Solo el EXIF: un fallo al
    decodificar los píxeles sigue siendo «no es una imagen válida».

    Pillow lo lee al girar la foto (`exif_transpose`) y, si no es un bloque TIFF, lanza
    `SyntaxError`; si es un TIFF cortado, `struct.error`; si un PNG lo trae como texto
    («Raw profile type exif») que no es hexadecimal, `ValueError` (CodeRabbit).
    """

    @pytest.mark.parametrize("archivo", ARCHIVOS_CON_EXIF_ILEGIBLE)
    async def test_procesar_galeria_con_exif_ilegible_la_acepta_sin_girar(self, archivo):
        """
        AV2 (EXIF ilegible).
        Given un PNG o un WEBP de 80x60 cuyo EXIF no se puede leer (no es TIFF, es un
              TIFF cortado o es un texto que no es hexadecimal)
        When se procesa como foto de galería
        Then sale un JPEG de 80x60, sin girar (rojo arriba) y sin ningún EXIF
        """
        resultado = await PillowImageProcessor().process_gallery_image(archivo())

        salida = Image.open(io.BytesIO(resultado))
        assert salida.format == "JPEG"
        assert salida.size == (80, 60)
        assert "exif" not in salida.info
        assert len(salida.getexif()) == 0
        rojo, _, azul = salida.convert("RGB").getpixel((40, 5))
        assert rojo > 200 and azul < 60

    @pytest.mark.parametrize("archivo", ARCHIVOS_CON_EXIF_ILEGIBLE)
    async def test_procesar_avatar_con_exif_ilegible_lo_acepta_sin_girar(self, archivo):
        """
        AV2 (EXIF ilegible).
        Given un PNG o un WEBP cuyo EXIF no se puede leer (no es TIFF, es un TIFF
              cortado o es un texto que no es hexadecimal)
        When se procesa como avatar
        Then sale el JPEG cuadrado de siempre, sin girar (rojo arriba, azul abajo) y sin EXIF
        """
        resultado = await PillowImageProcessor().process_avatar_image(archivo())

        salida = Image.open(io.BytesIO(resultado))
        assert salida.format == "JPEG"
        assert salida.size == (AVATAR_TARGET_SIZE, AVATAR_TARGET_SIZE)
        assert "exif" not in salida.info
        assert len(salida.getexif()) == 0
        pixeles = salida.convert("RGB")
        arriba = pixeles.getpixel((AVATAR_TARGET_SIZE // 2, 20))
        abajo = pixeles.getpixel((AVATAR_TARGET_SIZE // 2, AVATAR_TARGET_SIZE - 20))
        assert arriba[0] > 200 and arriba[2] < 60
        assert abajo[2] > 200 and abajo[0] < 60


class TestGuardasDeArchivosCortadosQueYaSeRechazaban:
    """
    Guardas, no pruebas del arreglo: un PNG, APNG o WEBP cortados ya se rechazaban antes
    (los para `Image.open()` o `verify()`, dentro de su `try`). Están para que siga así.
    """

    @pytest.mark.parametrize(
        "cortado",
        [
            pytest.param(lambda f: cortada("PNG", f), id="png"),
            pytest.param(lambda f: cortada("WEBP", f), id="webp"),
            pytest.param(apng_cortado, id="apng"),
        ],
    )
    @pytest.mark.parametrize("fraccion", [0.33, 0.8])
    @pytest.mark.parametrize("proceso", PROCESOS)
    async def test_procesar_png_apng_o_webp_cortado_sigue_siendo_imagen_no_valida(
        self, proceso, fraccion, cortado
    ):
        """
        AV2 (guarda).
        Given un PNG, APNG o WEBP cortado al 33 % o al 80 %
        When se procesa como avatar o como foto de galería
        Then se sigue rechazando con «no es una imagen válida»
        """
        procesar = getattr(PillowImageProcessor(), proceso)

        with pytest.raises(InvalidAvatarImageError, match="no es una imagen válida"):
            await procesar(cortado(fraccion))
