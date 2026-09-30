from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .consultas import cuentas_visibles
from .models import Cliente, Cuenta, Transaccion

User = get_user_model()


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "email", "telefono", "favoritos"]
        widgets = {"favoritos": forms.CheckboxSelectMultiple}
        help_texts = {"favoritos": "Clientes a quienes transfieres con frecuencia."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["favoritos"].queryset = Cliente.objects.exclude(pk=self.instance.pk)

    def clean_telefono(self):
        # Guardamos NULL en lugar de cadena vacía para mantener la columna consistente.
        return self.cleaned_data.get("telefono") or None


class CuentaForm(forms.ModelForm):
    class Meta:
        model = Cuenta
        fields = ["cliente", "tipo", "moneda", "activa"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if not user.is_staff:
            del self.fields["cliente"]  # se asigna al cliente del usuario en la vista
        if self.instance.pk:
            # La moneda no puede cambiar si la cuenta ya tiene saldo/movimientos.
            self.fields["moneda"].disabled = True
            if "cliente" in self.fields:
                self.fields["cliente"].disabled = True


class TransaccionForm(forms.ModelForm):
    class Meta:
        model = Transaccion
        fields = ["tipo", "cuenta_origen", "cuenta_destino", "monto", "descripcion"]
        help_texts = {
            "cuenta_origen": "Retiros y transferencias: de dónde sale el dinero.",
            "cuenta_destino": "Depósitos y transferencias: a dónde llega el dinero.",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        propias = cuentas_visibles(user).filter(activa=True)
        self.fields["cuenta_origen"].queryset = propias
        # Se puede transferir a cualquier cuenta activa; los depósitos, solo a cuentas propias.
        self.fields["cuenta_destino"].queryset = Cuenta.objects.filter(
            activa=True
        ).select_related("cliente")
        self.fields["monto"].widget.attrs.update({"min": "0.01", "step": "0.01"})

    def clean(self):
        cleaned = super().clean()
        destino = cleaned.get("cuenta_destino")
        if (
            cleaned.get("tipo") == Transaccion.Tipo.DEPOSITO
            and destino
            and not self.user.is_staff
            and destino.cliente.usuario_id != self.user.pk
        ):
            self.add_error("cuenta_destino", "Solo puedes depositar en tus propias cuentas.")
        return cleaned


class FiltroTransaccionForm(forms.Form):
    tipo = forms.ChoiceField(
        required=False, choices=[("", "Todos los tipos"), *Transaccion.Tipo.choices]
    )
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    monto_minimo = forms.DecimalField(required=False, min_value=0, decimal_places=2)


class RegistroForm(UserCreationForm):
    """Crea el usuario (django.contrib.auth) y su Cliente en una sola operación."""

    nombre = forms.CharField(max_length=100, label="Nombre completo")
    email = forms.EmailField(label="Correo electrónico")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "nombre", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Cliente.objects.filter(email__iexact=email).exists() or User.objects.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["nombre"]
        user.save()
        Cliente.objects.create(
            usuario=user, nombre=self.cleaned_data["nombre"], email=user.email
        )
        return user
