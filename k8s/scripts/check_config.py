#!/usr/bin/env python3
"""
Script de Verificación de Configuración Multi-Entorno

Verifica que las variables de entorno estén correctamente configuradas
para el entorno actual (Local, Kubernetes, Producción).

Uso:
    python k8s/scripts/check_config.py
    # O desde el directorio k8s:
    python scripts/check_config.py
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

# Agregar el directorio raíz al PYTHONPATH
# Script ubicado en: k8s/scripts/check_config.py
# Necesitamos subir 2 niveles: k8s/scripts/ → k8s/ → raíz
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.config.settings import settings


def print_header(text: str) -> None:
    """Imprime un encabezado decorado."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_check(label: str, value: str, status: str = "✅") -> None:
    """Imprime un check con formato."""
    print(f"{status} {label:<30} {value}")


def print_error(label: str, message: str) -> None:
    """Imprime un error."""
    print(f"❌ {label:<30} {message}")


def detect_environment() -> str:
    """
    Detecta el entorno actual basándose en FRONTEND_URL.

    Returns:
        str: "local", "kubernetes", "production", o "unknown"

    Security:
        Uses urlparse() to extract and validate exact hostname (CodeQL CWE-20).
        Prevents URL injection attacks like: http://evil.com?redirect=comebackgolf.com
        Rejects subdomain attacks like: https://comebackgolf.com.evil.com
    """
    try:
        # Puede ser una lista separada por comas (ADR-055): cuenta la principal
        parsed = urlparse(settings.FRONTEND_URL.split(",")[0].strip())
        hostname = parsed.hostname  # Extrae solo el hostname (sin puerto, path, query)

        if hostname is None:
            return "unknown"

        # Validación estricta: hostname exacto (no substrings)
        if hostname == "localhost" and parsed.port == 5173:
            return "local"
        if hostname == "localhost" and parsed.port == 8080:
            return "kubernetes"
        if hostname in ("www.comebackgolf.com", "comebackgolf.com"):
            return "production"

        return "unknown"
    except (ValueError, AttributeError):
        return "unknown"


def check_required_vars() -> tuple[int, int]:
    """
    Verifica que las variables críticas estén configuradas.

    Returns:
        tuple: (total_checks, passed_checks)
    """
    checks = {
        "FRONTEND_URL": settings.FRONTEND_URL,
        "MAILGUN_DOMAIN": settings.MAILGUN_DOMAIN,
        "MAILGUN_FROM_EMAIL": settings.MAILGUN_FROM_EMAIL,
        "MAILGUN_API_URL": settings.MAILGUN_API_URL,
        "SECRET_KEY": settings.SECRET_KEY,
        "DATABASE_URL": (
            settings.DATABASE_URL[:30] + "..."
            if len(settings.DATABASE_URL) > 30
            else settings.DATABASE_URL
        ),
    }

    total = len(checks)
    passed = 0

    print_header("🔍 Variables de Entorno Críticas")

    for label, value in checks.items():
        if value and value != "your-secret-key-change-in-production":
            print_check(label, value, "✅")
            passed += 1
        else:
            print_error(label, "NO CONFIGURADA o usando default inseguro")

    # Check especial para MAILGUN_API_KEY
    if settings.MAILGUN_API_KEY:
        print_check("MAILGUN_API_KEY", f"{'*' * 20}... (configurada)", "✅")
        passed += 1
    else:
        print_error("MAILGUN_API_KEY", "NO CONFIGURADA")

    total += 1  # Por MAILGUN_API_KEY

    return total, passed


def check_frontend_url() -> bool:
    """
    Verifica que FRONTEND_URL sea consistente con el entorno.

    Returns:
        bool: True si es consistente, False en caso contrario
    """
    print_header("🌐 Verificación de FRONTEND_URL")

    frontend_url = settings.FRONTEND_URL
    env = detect_environment()

    print(f"📌 URL configurada: {frontend_url}")
    print(f"📌 Entorno detectado: {env.upper()}")

    env_recommendations = {
        "local": "http://localhost:5173",
        "kubernetes": "http://localhost:8080",
        "production": "https://www.comebackgolf.com",
    }

    if env == "unknown":
        print_error(
            "ADVERTENCIA",
            f"No se pudo detectar el entorno basándose en: {frontend_url}",
        )
        print("\n🔧 URLs esperadas:")
        for env_name, url in env_recommendations.items():
            print(f"   - {env_name.capitalize()}: {url}")
        return False

    recommended = env_recommendations[env]
    if frontend_url == recommended:
        print_check("Consistencia", f"OK - Coincide con entorno {env}", "✅")
        return True
    print_error("INCONSISTENCIA", f"Se esperaba '{recommended}' para entorno {env}")
    return False


def check_email_service() -> bool:
    """
    Verifica que el servicio de email esté configurado.

    Returns:
        bool: True si está configurado, False en caso contrario
    """
    print_header("📧 Servicio de Email (Mailgun)")

    if not settings.MAILGUN_API_KEY:
        print_error("MAILGUN_API_KEY", "NO CONFIGURADA - Los emails NO se enviarán")
        return False

    checks = {
        "API Key": bool(settings.MAILGUN_API_KEY),
        "Domain": bool(settings.MAILGUN_DOMAIN),
        "From Email": bool(settings.MAILGUN_FROM_EMAIL),
        "API URL": bool(settings.MAILGUN_API_URL),
    }

    all_ok = all(checks.values())

    for label, ok in checks.items():
        status = "✅" if ok else "❌"
        value = "Configurado" if ok else "NO configurado"
        print(f"{status} {label:<20} {value}")

    if all_ok:
        print("\n✅ Servicio de email correctamente configurado")
    else:
        print("\n❌ Configuración de email INCOMPLETA")

    return all_ok


def check_jwt() -> bool:
    """
    Verifica la configuración de JWT.

    Returns:
        bool: True si está configurado, False en caso contrario
    """
    print_header("🔐 JWT Configuration")

    checks = {
        "SECRET_KEY": settings.SECRET_KEY != "your-secret-key-change-in-production",
        "ALGORITHM": settings.ALGORITHM == "HS256",
        "EXPIRE_MINUTES": settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0,
    }

    all_ok = all(checks.values())

    for label, ok in checks.items():
        status = "✅" if ok else "❌"
        if label == "SECRET_KEY":
            value = "Configurado" if ok else "Usando default INSEGURO"
        elif label == "ALGORITHM":
            value = f"{settings.ALGORITHM}"
        else:
            value = f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutos"

        print(f"{status} {label:<20} {value}")

    if not checks["SECRET_KEY"]:
        print("\n⚠️  ADVERTENCIA: Estás usando la SECRET_KEY por defecto.")
        print("   Esto es INSEGURO en producción. Genera una nueva con:")
        print("   python -c 'import secrets; print(secrets.token_urlsafe(32))'")

    return all_ok


def print_recommendations() -> None:
    """Imprime recomendaciones basadas en el entorno detectado."""
    print_header("💡 Recomendaciones")

    env = detect_environment()

    if env == "local":
        print("📝 Estás en modo LOCAL (desarrollo directo)")
        print("   1. Asegúrate de tener el .env configurado")
        print("   2. Ejecuta: uvicorn main:app --reload --port 8000")
        print("   3. Frontend debe correr en: http://localhost:5173")
        print("   4. Los enlaces de email apuntarán a: http://localhost:5173/verify-email")

    elif env == "kubernetes":
        print("📝 Estás en modo KUBERNETES (Kind local)")
        print("   1. Asegúrate de tener el ConfigMap aplicado:")
        print("      kubectl apply -f k8s/api-configmap.yaml")
        print("   2. Port-forward del frontend:")
        print("      kubectl port-forward svc/comebackgolf-web-service 8080:80 -n comebackgolf")
        print("   3. Accede al frontend en: http://localhost:8080")
        print("   4. Los enlaces de email apuntarán a: http://localhost:8080/verify-email")

    elif env == "production":
        print("📝 Estás en modo PRODUCCIÓN")
        print("   1. Verifica las variables en Render Dashboard")
        print("   2. URL del frontend: https://www.comebackgolf.com")
        print("   3. Los enlaces de email apuntarán a: https://www.comebackgolf.com/verify-email")
        print("   4. Monitorea los logs en: https://dashboard.render.com")

    else:
        print("⚠️  No se pudo determinar el entorno")
        print("   Revisa la variable FRONTEND_URL en tu configuración")


def main() -> None:
    """Función principal del script."""
    print("\n" + "🔧" * 30)
    print("  VERIFICADOR DE CONFIGURACIÓN MULTI-ENTORNO")
    print("  Comeback Golf API")
    print("🔧" * 30)

    # Ejecutar verificaciones
    total_vars, passed_vars = check_required_vars()
    frontend_ok = check_frontend_url()
    email_ok = check_email_service()
    jwt_ok = check_jwt()

    # Recomendaciones
    print_recommendations()

    # Resumen final
    print_header("📊 Resumen de Verificación")

    total_checks = 4
    passed_checks = sum([frontend_ok, email_ok, jwt_ok, passed_vars == total_vars])

    print(f"\n✅ Checks pasados: {passed_checks}/{total_checks}")
    print(f"📌 Variables configuradas: {passed_vars}/{total_vars}")

    if passed_checks == total_checks and passed_vars == total_vars:
        print("\n🎉 ¡CONFIGURACIÓN CORRECTA! Todo está listo para funcionar.")
        sys.exit(0)
    else:
        print("\n⚠️  CONFIGURACIÓN INCOMPLETA. Revisa los errores arriba.")
        print("   Consulta: docs/MULTI_ENVIRONMENT_SETUP.md")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Verificación cancelada por el usuario.")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ ERROR INESPERADO: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
