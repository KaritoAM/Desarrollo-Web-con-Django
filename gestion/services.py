"""Lógica de negocio: única vía para mover dinero entre cuentas."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Cuenta, Transaccion


@transaction.atomic
def registrar_transaccion(
    *, tipo, monto, cuenta_origen=None, cuenta_destino=None, descripcion=""
):
    """Valida, actualiza saldos y guarda la transacción de forma atómica.

    Las cuentas se bloquean (``select_for_update``) en orden de id para evitar
    condiciones de carrera y deadlocks con operaciones simultáneas.
    Lanza ``ValidationError`` si algo no cumple las reglas.
    """
    monto = Decimal(monto)
    ids = sorted({c.pk for c in (cuenta_origen, cuenta_destino) if c is not None})
    bloqueadas = {
        c.pk: c for c in Cuenta.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    }
    origen = bloqueadas.get(cuenta_origen.pk) if cuenta_origen else None
    destino = bloqueadas.get(cuenta_destino.pk) if cuenta_destino else None

    trx = Transaccion(
        tipo=tipo,
        cuenta_origen=origen,
        cuenta_destino=destino,
        monto=monto,
        descripcion=descripcion,
    )
    trx.full_clean()

    for cuenta in (origen, destino):
        if cuenta is not None and not cuenta.activa:
            raise ValidationError(f"La cuenta {cuenta.numero} está inactiva.")
    if origen is not None and origen.saldo < monto:
        raise ValidationError("Saldo insuficiente en la cuenta de origen.")

    if origen is not None:
        origen.saldo -= monto
        origen.save(update_fields=["saldo"])
    if destino is not None:
        destino.saldo += monto
        destino.save(update_fields=["saldo"])
    trx.save()
    return trx
