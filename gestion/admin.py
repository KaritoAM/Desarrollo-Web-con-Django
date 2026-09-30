from django.contrib import admin

from .models import Cliente, Cuenta, Transaccion


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "email", "telefono", "usuario", "fecha_registro")
    search_fields = ("nombre", "email")
    filter_horizontal = ("favoritos",)


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "tipo", "moneda", "saldo", "activa")
    list_filter = ("tipo", "moneda", "activa")
    search_fields = ("numero", "cliente__nombre", "cliente__email")
    readonly_fields = ("numero", "saldo", "creada")
    autocomplete_fields = ("cliente",)


@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    """Libro contable de solo lectura: los movimientos se crean desde la app
    (services.registrar_transaccion) para que los saldos siempre cuadren."""

    list_display = ("id", "tipo", "cuenta_origen", "cuenta_destino", "monto", "fecha")
    list_filter = ("tipo", "fecha")
    search_fields = ("cuenta_origen__numero", "cuenta_destino__numero", "descripcion")
    date_hierarchy = "fecha"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
