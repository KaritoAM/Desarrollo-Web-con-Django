import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse

validador_telefono = RegexValidator(
    r"^\+?[0-9 ]{7,20}$",
    "Ingresa un teléfono válido: solo dígitos y espacios, con + opcional al inicio.",
)


class Cliente(models.Model):
    """Persona titular de una o más cuentas.

    Relaciones:
      * Uno a Uno   -> ``usuario``: el usuario de django.contrib.auth que inicia sesión.
      * Muchos a Muchos -> ``favoritos``: otros clientes a quienes transfiere seguido.
    """

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cliente",
    )
    nombre = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    telefono = models.CharField(
        max_length=20, blank=True, null=True, validators=[validador_telefono]
    )
    favoritos = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="favorito_de"
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse("gestion:cliente_detalle", args=[self.pk])


def _generar_numero_cuenta():
    return f"AW{uuid.uuid4().int % 10**10:010d}"


class Cuenta(models.Model):
    """Cuenta digital de un cliente (Muchos a Uno con Cliente)."""

    class Tipo(models.TextChoices):
        AHORRO = "AHORRO", "Ahorro"
        CORRIENTE = "CORRIENTE", "Corriente"
        VISTA = "VISTA", "Vista"

    class Moneda(models.TextChoices):
        CLP = "CLP", "Peso chileno (CLP)"
        USD = "USD", "Dólar (USD)"

    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="cuentas"
    )
    numero = models.CharField(max_length=20, unique=True, editable=False)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.VISTA)
    moneda = models.CharField(
        max_length=3, choices=Moneda.choices, default=Moneda.CLP
    )
    saldo = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,  # solo cambia mediante transacciones (ver services.py)
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["cliente__nombre", "numero"]
        constraints = [
            models.CheckConstraint(
                condition=Q(saldo__gte=0), name="cuenta_saldo_no_negativo"
            )
        ]

    def __str__(self):
        return f"{self.numero} ({self.cliente})"

    def save(self, *args, **kwargs):
        if not self.numero:
            numero = _generar_numero_cuenta()
            while Cuenta.objects.filter(numero=numero).exists():
                numero = _generar_numero_cuenta()
            self.numero = numero
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("gestion:cuenta_detalle", args=[self.pk])

    def movimientos(self):
        """Todas las transacciones donde la cuenta entra o sale dinero."""
        return Transaccion.objects.filter(
            Q(cuenta_origen=self) | Q(cuenta_destino=self)
        ).select_related(
            "cuenta_origen__cliente", "cuenta_destino__cliente"
        )


class Transaccion(models.Model):
    """Movimiento de dinero. Origen y destino son Muchos a Uno hacia Cuenta."""

    class Tipo(models.TextChoices):
        DEPOSITO = "DEPOSITO", "Depósito"
        RETIRO = "RETIRO", "Retiro"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"

    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    cuenta_origen = models.ForeignKey(
        Cuenta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="salidas",
    )
    cuenta_destino = models.ForeignKey(
        Cuenta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entradas",
    )
    monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    descripcion = models.CharField(max_length=200, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "transacción"
        verbose_name_plural = "transacciones"
        constraints = [
            models.CheckConstraint(
                condition=Q(monto__gt=0), name="transaccion_monto_positivo"
            )
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.monto}"

    def get_absolute_url(self):
        return reverse("gestion:transaccion_detalle", args=[self.pk])

    def clean(self):
        """Reglas de coherencia entre el tipo y las cuentas involucradas."""
        errores = {}
        T = self.Tipo
        if self.tipo == T.DEPOSITO:
            if not self.cuenta_destino_id:
                errores["cuenta_destino"] = "Un depósito necesita cuenta de destino."
            if self.cuenta_origen_id:
                errores["cuenta_origen"] = "Un depósito no tiene cuenta de origen."
        elif self.tipo == T.RETIRO:
            if not self.cuenta_origen_id:
                errores["cuenta_origen"] = "Un retiro necesita cuenta de origen."
            if self.cuenta_destino_id:
                errores["cuenta_destino"] = "Un retiro no tiene cuenta de destino."
        elif self.tipo == T.TRANSFERENCIA:
            if not self.cuenta_origen_id:
                errores["cuenta_origen"] = "Indica la cuenta de origen."
            if not self.cuenta_destino_id:
                errores["cuenta_destino"] = "Indica la cuenta de destino."
            if self.cuenta_origen_id and self.cuenta_origen_id == self.cuenta_destino_id:
                errores["cuenta_destino"] = "El destino debe ser distinto del origen."
            elif (
                self.cuenta_origen_id
                and self.cuenta_destino_id
                and self.cuenta_origen.moneda != self.cuenta_destino.moneda
            ):
                errores["cuenta_destino"] = (
                    "Las cuentas deben estar en la misma moneda."
                )
        if errores:
            raise ValidationError(errores)
