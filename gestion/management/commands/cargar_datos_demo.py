from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from gestion.models import Cliente, Cuenta, Transaccion
from gestion.services import registrar_transaccion

User = get_user_model()


class Command(BaseCommand):
    help = "Carga datos de ejemplo para desarrollo (usuarios, clientes, cuentas y movimientos)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Solo se puede ejecutar con DEBUG=True (entorno de desarrollo).")

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@alke.test", "admin1234")

        personas = [
            ("ana", "Ana García", "ana@example.com", "123456789"),
            ("luis", "Luis Pérez", "luis@example.com", None),
            ("marta", "Marta Soto", "marta@example.com", "+56 9 8765 4321"),
        ]
        cuentas = {}
        for username, nombre, email, telefono in personas:
            user, creado = User.objects.get_or_create(
                username=username, defaults={"email": email, "first_name": nombre}
            )
            if creado:
                user.set_password("demo1234")
                user.save()
            cliente, _ = Cliente.objects.get_or_create(
                email=email, defaults={"nombre": nombre, "telefono": telefono, "usuario": user}
            )
            cuenta = Cuenta.objects.filter(cliente=cliente).first() or Cuenta.objects.create(
                cliente=cliente, tipo=Cuenta.Tipo.VISTA
            )
            cuentas[username] = cuenta

        if not Transaccion.objects.exists():
            T = Transaccion.Tipo
            registrar_transaccion(tipo=T.DEPOSITO, monto=Decimal("500000"),
                                  cuenta_destino=cuentas["ana"], descripcion="Sueldo")
            registrar_transaccion(tipo=T.DEPOSITO, monto=Decimal("120000"),
                                  cuenta_destino=cuentas["luis"], descripcion="Carga inicial")
            registrar_transaccion(tipo=T.TRANSFERENCIA, monto=Decimal("45000"),
                                  cuenta_origen=cuentas["ana"], cuenta_destino=cuentas["luis"],
                                  descripcion="Arriendo compartido")
            registrar_transaccion(tipo=T.RETIRO, monto=Decimal("20000"),
                                  cuenta_origen=cuentas["ana"], descripcion="Cajero")

        self.stdout.write(self.style.SUCCESS(
            "Datos de demo listos. Usuarios: admin/admin1234 (staff), ana/demo1234, luis/demo1234, marta/demo1234"
        ))
