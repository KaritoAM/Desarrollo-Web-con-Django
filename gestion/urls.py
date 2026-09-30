from django.urls import path

from . import views

app_name = "gestion"

urlpatterns = [
    path("", views.InicioView.as_view(), name="inicio"),
    path("registro/", views.RegistroView.as_view(), name="registro"),
    # Clientes
    path("clientes/", views.ClienteListView.as_view(), name="cliente_lista"),
    path("clientes/nuevo/", views.ClienteCreateView.as_view(), name="cliente_crear"),
    path("clientes/<int:pk>/", views.ClienteDetailView.as_view(), name="cliente_detalle"),
    path("clientes/<int:pk>/editar/", views.ClienteUpdateView.as_view(), name="cliente_editar"),
    path("clientes/<int:pk>/eliminar/", views.ClienteDeleteView.as_view(), name="cliente_eliminar"),
    # Cuentas
    path("cuentas/", views.CuentaListView.as_view(), name="cuenta_lista"),
    path("cuentas/nueva/", views.CuentaCreateView.as_view(), name="cuenta_crear"),
    path("cuentas/<int:pk>/", views.CuentaDetailView.as_view(), name="cuenta_detalle"),
    path("cuentas/<int:pk>/editar/", views.CuentaUpdateView.as_view(), name="cuenta_editar"),
    path("cuentas/<int:pk>/eliminar/", views.CuentaDeleteView.as_view(), name="cuenta_eliminar"),
    # Transacciones
    path("transacciones/", views.TransaccionListView.as_view(), name="transaccion_lista"),
    path("transacciones/nueva/", views.TransaccionCreateView.as_view(), name="transaccion_crear"),
    path("transacciones/<int:pk>/", views.TransaccionDetailView.as_view(), name="transaccion_detalle"),
    # Reportes
    path("reportes/", views.ReportesView.as_view(), name="reportes"),
]
