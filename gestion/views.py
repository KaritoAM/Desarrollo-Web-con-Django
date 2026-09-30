from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError, Q, Sum
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from . import consultas, services
from .forms import (
    ClienteForm,
    CuentaForm,
    FiltroTransaccionForm,
    RegistroForm,
    TransaccionForm,
)
from .models import Cliente, Cuenta, Transaccion

FORM_TEMPLATE = "gestion/form.html"
DELETE_TEMPLATE = "gestion/confirmar_eliminar.html"


class StaffRequiredMixin(UserPassesTestMixin):
    """Restringe la vista al personal (is_staff). Usar después de LoginRequiredMixin."""

    def test_func(self):
        return self.request.user.is_staff


class FormContextMixin:
    titulo = ""
    boton = "Guardar"
    volver = reverse_lazy("gestion:inicio")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(titulo=self.titulo, boton=self.boton, volver=self.volver)
        return ctx


class EliminarProtegidoMixin:
    """Muestra un mensaje claro si el registro tiene datos relacionados protegidos."""

    def form_valid(self, form):
        try:
            respuesta = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                "No se puede eliminar: tiene cuentas o transacciones asociadas.",
            )
            return redirect(self.get_object().get_absolute_url())
        messages.success(self.request, "Registro eliminado.")
        return respuesta


# --- Registro y portada -----------------------------------------------------
class RegistroView(FormView):
    template_name = "registration/registro.html"
    form_class = RegistroForm
    success_url = reverse_lazy("gestion:inicio")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("gestion:inicio")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, "Tu cuenta de usuario está lista.")
        return super().form_valid(form)


class InicioView(LoginRequiredMixin, TemplateView):
    template_name = "gestion/inicio.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        cuentas = consultas.cuentas_visibles(user)
        ctx["cuentas"] = cuentas.filter(activa=True)[:6]
        ctx["totales"] = (
            cuentas.filter(activa=True)
            .values("moneda")
            .annotate(total=Sum("saldo"))
            .order_by("moneda")
        )
        ctx["recientes"] = consultas.transacciones_visibles(user)[:6]
        ctx["tiene_cliente"] = user.is_staff or hasattr(user, "cliente")
        return ctx


# --- Clientes: CRUD ---------------------------------------------------------
class ClienteListView(LoginRequiredMixin, ListView):
    template_name = "gestion/cliente_list.html"
    context_object_name = "clientes"
    paginate_by = 10

    def get_queryset(self):
        qs = consultas.clientes_con_resumen(consultas.clientes_visibles(self.request.user))
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(email__icontains=q))
        return qs.order_by("nombre")


class ClienteDetailView(LoginRequiredMixin, DetailView):
    template_name = "gestion/cliente_detail.html"
    context_object_name = "cliente"

    def get_queryset(self):
        return consultas.clientes_visibles(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cuentas"] = self.object.cuentas.all()
        ctx["favoritos"] = self.object.favoritos.all()
        return ctx


class ClienteCreateView(
    LoginRequiredMixin, StaffRequiredMixin, SuccessMessageMixin, FormContextMixin, CreateView
):
    model = Cliente
    form_class = ClienteForm
    template_name = FORM_TEMPLATE
    success_message = "Cliente creado."
    titulo = "Nuevo cliente"
    boton = "Crear cliente"
    volver = reverse_lazy("gestion:cliente_lista")


class ClienteUpdateView(LoginRequiredMixin, SuccessMessageMixin, FormContextMixin, UpdateView):
    form_class = ClienteForm
    template_name = FORM_TEMPLATE
    success_message = "Datos actualizados."
    titulo = "Editar cliente"
    boton = "Guardar cambios"

    def get_queryset(self):
        return consultas.clientes_visibles(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["volver"] = self.object.get_absolute_url()
        return ctx


class ClienteDeleteView(LoginRequiredMixin, StaffRequiredMixin, EliminarProtegidoMixin, DeleteView):
    model = Cliente
    template_name = DELETE_TEMPLATE
    success_url = reverse_lazy("gestion:cliente_lista")


# --- Cuentas: CRUD ----------------------------------------------------------
class CuentaListView(LoginRequiredMixin, ListView):
    template_name = "gestion/cuenta_list.html"
    context_object_name = "cuentas"
    paginate_by = 10

    def get_queryset(self):
        return consultas.cuentas_visibles(self.request.user)


class CuentaDetailView(LoginRequiredMixin, DetailView):
    template_name = "gestion/cuenta_detail.html"
    context_object_name = "cuenta"

    def get_queryset(self):
        return consultas.cuentas_visibles(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["movimientos"] = self.object.movimientos()[:20]
        return ctx


class CuentaFormMixin(FormContextMixin):
    form_class = CuentaForm
    template_name = FORM_TEMPLATE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class CuentaCreateView(LoginRequiredMixin, SuccessMessageMixin, CuentaFormMixin, CreateView):
    model = Cuenta
    success_message = "Cuenta creada."
    titulo = "Nueva cuenta"
    boton = "Crear cuenta"
    volver = reverse_lazy("gestion:cuenta_lista")

    def form_valid(self, form):
        if not self.request.user.is_staff:
            cliente = getattr(self.request.user, "cliente", None)
            if cliente is None:
                messages.error(self.request, "Tu usuario no tiene un cliente asociado.")
                return redirect("gestion:cuenta_lista")
            form.instance.cliente = cliente
        return super().form_valid(form)


class CuentaUpdateView(LoginRequiredMixin, SuccessMessageMixin, CuentaFormMixin, UpdateView):
    success_message = "Cuenta actualizada."
    titulo = "Editar cuenta"
    boton = "Guardar cambios"

    def get_queryset(self):
        return consultas.cuentas_visibles(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["volver"] = self.object.get_absolute_url()
        return ctx


class CuentaDeleteView(LoginRequiredMixin, EliminarProtegidoMixin, DeleteView):
    template_name = DELETE_TEMPLATE
    success_url = reverse_lazy("gestion:cuenta_lista")

    def get_queryset(self):
        return consultas.cuentas_visibles(self.request.user)

    def form_valid(self, form):
        if self.get_object().saldo != 0:
            messages.error(self.request, "No se puede eliminar una cuenta con saldo.")
            return redirect(self.get_object().get_absolute_url())
        return super().form_valid(form)


# --- Transacciones ----------------------------------------------------------
# Las transacciones se crean y consultan, pero no se editan ni eliminan:
# es un libro contable y alterarlo rompería los saldos.
class TransaccionListView(LoginRequiredMixin, ListView):
    template_name = "gestion/transaccion_list.html"
    context_object_name = "transacciones"
    paginate_by = 15

    def get_queryset(self):
        self.filtro = FiltroTransaccionForm(self.request.GET or None)
        qs = consultas.transacciones_visibles(self.request.user)
        if self.filtro.is_valid():
            qs = consultas.filtrar_transacciones(qs, **self.filtro.cleaned_data)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filtro"] = self.filtro
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["query"] = params.urlencode()
        return ctx


class TransaccionDetailView(LoginRequiredMixin, DetailView):
    template_name = "gestion/transaccion_detail.html"
    context_object_name = "transaccion"

    def get_queryset(self):
        return consultas.transacciones_visibles(self.request.user)


class TransaccionCreateView(LoginRequiredMixin, FormContextMixin, CreateView):
    model = Transaccion
    form_class = TransaccionForm
    template_name = FORM_TEMPLATE
    titulo = "Nueva transacción"
    boton = "Confirmar transacción"
    volver = reverse_lazy("gestion:transaccion_lista")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        datos = form.cleaned_data
        try:
            self.object = services.registrar_transaccion(
                tipo=datos["tipo"],
                monto=datos["monto"],
                cuenta_origen=datos.get("cuenta_origen"),
                cuenta_destino=datos.get("cuenta_destino"),
                descripcion=datos.get("descripcion", ""),
            )
        except ValidationError as error:
            for mensaje in error.messages:
                form.add_error(None, mensaje)
            return self.form_invalid(form)
        messages.success(self.request, "Transacción realizada.")
        return redirect(self.object.get_absolute_url())


# --- Reportes (solo personal) ------------------------------------------------
class ReportesView(LoginRequiredMixin, StaffRequiredMixin, TemplateView):
    template_name = "gestion/reportes.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["ranking"] = consultas.ranking_clientes_raw(5)  # SQL con raw()
        ctx["resumen_tipos"] = consultas.resumen_por_tipo_sql()  # SQL con cursor
        ctx["sin_movimientos"] = consultas.clientes_sin_movimientos()  # exclude()
        ctx["cuentas_activas"] = consultas.cuentas_mas_activas(5)  # annotate()
        ctx["resumen_clientes"] = consultas.clientes_con_resumen().order_by("-saldo_total")
        return ctx
