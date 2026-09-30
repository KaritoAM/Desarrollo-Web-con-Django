"""Consultas personalizadas: filtros, anotaciones, SQL crudo (raw) y cursores."""
from decimal import Decimal

from django.db import connection
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from .models import Cliente, Cuenta, Transaccion

CERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))


# --- Alcance por usuario: cada persona ve solo lo suyo; el staff ve todo ------
def clientes_visibles(user):
    qs = Cliente.objects.all()
    return qs if user.is_staff else qs.filter(usuario=user)


def cuentas_visibles(user):
    qs = Cuenta.objects.select_related("cliente")
    return qs if user.is_staff else qs.filter(cliente__usuario=user)


def transacciones_visibles(user):
    qs = Transaccion.objects.select_related(
        "cuenta_origen__cliente", "cuenta_destino__cliente"
    )
    if user.is_staff:
        return qs
    return qs.filter(
        Q(cuenta_origen__cliente__usuario=user)
        | Q(cuenta_destino__cliente__usuario=user)
    )


# --- ORM: filtros y anotaciones ---------------------------------------------
def clientes_con_resumen(qs=None):
    """Clientes con cantidad de cuentas y saldo total (annotate + Sum/Count)."""
    qs = Cliente.objects.all() if qs is None else qs
    return qs.annotate(
        num_cuentas=Count("cuentas", distinct=True),
        saldo_total=Coalesce(Sum("cuentas__saldo"), CERO),
    )


def cuentas_mas_activas(limite=5):
    """Cuentas ordenadas por número de movimientos (entradas + salidas)."""
    return (
        Cuenta.objects.select_related("cliente")
        .annotate(
            num_entradas=Count("entradas", distinct=True),
            num_salidas=Count("salidas", distinct=True),
        )
        .annotate(total_movimientos=F("num_entradas") + F("num_salidas"))
        .filter(total_movimientos__gt=0)
        .order_by("-total_movimientos", "numero")[:limite]
    )


def clientes_sin_movimientos():
    """Clientes cuyas cuentas nunca han tenido movimientos (exclude)."""
    return Cliente.objects.exclude(
        Q(cuentas__salidas__isnull=False) | Q(cuentas__entradas__isnull=False)
    )


def filtrar_transacciones(qs, *, tipo=None, desde=None, hasta=None, monto_minimo=None):
    """Aplica filtros opcionales encadenados sobre un queryset de transacciones."""
    if tipo:
        qs = qs.filter(tipo=tipo)
    if desde:
        qs = qs.filter(fecha__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha__date__lte=hasta)
    if monto_minimo is not None:
        qs = qs.filter(monto__gte=monto_minimo)
    return qs


# --- SQL personalizado ------------------------------------------------------
def ranking_clientes_raw(limite=5):
    """Ranking de clientes por saldo total usando ``raw()``.

    Los valores se pasan como parámetros (%s) para evitar inyección SQL.
    """
    sql = f"""
        SELECT c.id, c.nombre, c.email,
               COALESCE(SUM(cu.saldo), 0) AS saldo_total
        FROM {Cliente._meta.db_table} c
        LEFT JOIN {Cuenta._meta.db_table} cu ON cu.cliente_id = c.id
        GROUP BY c.id, c.nombre, c.email
        ORDER BY saldo_total DESC, c.nombre
        LIMIT %s
    """
    return list(Cliente.objects.raw(sql, [limite]))


def resumen_por_tipo_sql():
    """Total y monto acumulado por tipo de transacción usando un cursor."""
    tabla = Transaccion._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT tipo, COUNT(*), COALESCE(SUM(monto), 0) "
            f"FROM {tabla} GROUP BY tipo ORDER BY tipo"
        )
        etiquetas = dict(Transaccion.Tipo.choices)
        return [
            {"tipo": etiquetas.get(t, t), "cantidad": n, "monto": Decimal(str(m))}
            for t, n, m in cursor.fetchall()
        ]
