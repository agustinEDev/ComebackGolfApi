#!/bin/bash

# ==========================================
# Script de Eliminación - Comeback Golf
# ==========================================
# Este script elimina el cluster de Kubernetes completamente
#
# ⚠️  IMPORTANTE: Ejecutar con ./destroy-cluster.sh
#    NO uses: source destroy-cluster.sh
#
# Uso: ./scripts/destroy-cluster.sh
# ==========================================

# Detectar si fue ejecutado con 'source'
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Ejecutado correctamente con ./
    :
else
    echo "❌ ERROR: No ejecutes este script con 'source'"
    echo "✅ Usa: ./k8s/scripts/destroy-cluster.sh"
    return 1 2>/dev/null || exit 1
fi

set -e  # Salir si algún comando falla

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función para imprimir mensajes con colores
print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_step() {
    echo -e "${BLUE}==>${NC} ${GREEN}$1${NC}"
}

# Manejo de interrupciones (Ctrl+C) - DESPUÉS de definir funciones
trap 'echo ""; print_warning "Script interrumpido por el usuario"; exit 130' INT TERM

# Banner
echo ""
echo "🗑️  =============================================="
echo "   Comeback Golf - Cluster Cleanup"
echo "   =============================================="
echo ""

CLUSTER_NAME="comebackgolf-cluster"

# ==========================================
# Verificar si el cluster existe
# ==========================================
if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    print_warning "El cluster '${CLUSTER_NAME}' no existe"
    exit 0
fi

# ==========================================
# Confirmación
# ==========================================
print_warning "⚠️  ADVERTENCIA: Esta acción eliminará:"
echo "   • Todos los pods"
echo "   • Todos los datos de PostgreSQL"
echo "   • Todas las configuraciones"
echo "   • El cluster completo"
echo ""

read -p "¿Estás seguro de que quieres eliminar el cluster? (y/N): " -n 1 -r
echo
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Operación cancelada"
    exit 0
fi

# ==========================================
# Eliminar cluster
# ==========================================
print_step "Eliminando cluster '${CLUSTER_NAME}'..."

kind delete cluster --name ${CLUSTER_NAME}

print_success "Cluster eliminado exitosamente"
echo ""

# ==========================================
# Limpiar imágenes (opcional)
# ==========================================
read -p "¿Quieres eliminar también las imágenes Docker de Kind? (y/N): " -n 1 -r
echo
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Eliminando imágenes Docker de Kind..."

    # Buscar y eliminar imágenes kindest/node
    IMAGES=$(docker images | grep kindest/node | awk '{print $3}')

    if [ -z "$IMAGES" ]; then
        print_warning "No se encontraron imágenes de Kind"
    else
        # Compatibilidad macOS: xargs sin -r (GNU)
        # En macOS, si IMAGES está vacío, xargs no ejecutará el comando
        for img in $IMAGES; do
            docker rmi -f "$img" 2>/dev/null || true
        done
        print_success "Imágenes de Kind eliminadas"
    fi
fi

echo ""
print_success "🎉 ¡Cleanup completado!"
echo ""
echo "📋 Para volver a crear el cluster:"
echo -e "   ${GREEN}./scripts/deploy-cluster.sh${NC}"
echo ""
