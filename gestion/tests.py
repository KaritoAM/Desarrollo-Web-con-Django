from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from . import consultas
from .models import Cliente, Cuenta, Transaccion
from .services import registrar_transaccion

User = get_user_model()
T = Transaccion.Tipo


def crear_cliente(username, staff=False):
    user = User.objects.create_user(username, f"{username}@t.cl", "clave-segura-123", is_staff=staff)
    cliente = Cliente.objects.create(usuario=user, nombre=username.title(), email=user.email)
    return user, cliente


def crear_cuenta(cliente, saldo="0", **kw):
    cuenta = Cuenta.objects.create(cliente=cliente, **kw)
    if Decimal(saldo):
        Cuenta.objects.filter(pk=cuenta.pk).update(saldo=Decimal(saldo))
        cuenta.refresh_from_db()
    return cuenta


class ModelosTests(TestCase):
    def setUp(self):
        _, self.ana = crear_cliente("ana")

    def test_numero_de_cuenta_se_genera_y_es_unico(self):
        a, b = crear_cuenta(self.ana), crear_cuenta(self.ana)
        self.assertTrue(a.numero.startswith("AW"))
        self.assertNotEqual(a.numero, b.numero)

    def test_email_de_cliente_es_unico(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cliente.objects.create(nombre="Otra", email="ana@t.cl")

    def test_relacion_uno_a_uno_usuario_cliente(self):
        self.assertEqual(self.ana.usuario.cliente, self.ana)

    def test_favoritos_muchos_a_muchos(self):
        _, luis = crear_cliente("luis")
        self.ana.favoritos.add(luis)
        self.assertIn(luis, self.ana.favoritos.all())
        self.assertIn(self.ana, luis.favorito_de.all())

    def test_saldo_negativo_rechazado_por_la_base_de_datos(self):
        cuenta = crear_cuenta(self.ana)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cuenta.objects.filter(pk=cuenta.pk).update(saldo=Decimal("-1"))

    def test_telefono_invalido(self):
        c = Cliente(nombre="X", email="x@t.cl", telefono="abc")
        with self.assertRaises(ValidationError):
            c.full_clean()


class ServicioTransaccionesTests(TestCase):
    def setUp(self):
        _, self.ana = crear_cliente("ana")
        _, self.luis = crear_cliente("luis")
        self.c_ana = crear_cuenta(self.ana, "1000")
        self.c_luis = crear_cuenta(self.luis, "0")

    def test_deposito(self):
        registrar_transaccion(tipo=T.DEPOSITO, monto="250.50", cuenta_destino=self.c_luis)
        self.c_luis.refresh_from_db()
        self.assertEqual(self.c_luis.saldo, Decimal("250.50"))

    def test_retiro(self):
        registrar_transaccion(tipo=T.RETIRO, monto="300", cuenta_origen=self.c_ana)
        self.c_ana.refresh_from_db()
        self.assertEqual(self.c_ana.saldo, Decimal("700"))

    def test_transferencia_mueve_saldos(self):
        registrar_transaccion(tipo=T.TRANSFERENCIA, monto="400", cuenta_origen=self.c_ana, cuenta_destino=self.c_luis)
        self.c_ana.refresh_from_db(); self.c_luis.refresh_from_db()
        self.assertEqual((self.c_ana.saldo, self.c_luis.saldo), (Decimal("600"), Decimal("400")))

    def test_saldo_insuficiente_no_cambia_nada(self):
        with self.assertRaises(ValidationError):
            registrar_transaccion(tipo=T.TRANSFERENCIA, monto="5000", cuenta_origen=self.c_ana, cuenta_destino=self.c_luis)
        self.c_ana.refresh_from_db()
        self.assertEqual(self.c_ana.saldo, Decimal("1000"))
        self.assertEqual(Transaccion.objects.count(), 0)

    def test_monto_debe_ser_positivo(self):
        for monto in ("0", "-5"):
            with self.assertRaises(ValidationError):
                registrar_transaccion(tipo=T.DEPOSITO, monto=monto, cuenta_destino=self.c_ana)

    def test_transferencia_a_la_misma_cuenta(self):
        with self.assertRaises(ValidationError):
            registrar_transaccion(tipo=T.TRANSFERENCIA, monto="1", cuenta_origen=self.c_ana, cuenta_destino=self.c_ana)

    def test_tipo_y_cuentas_deben_ser_coherentes(self):
        with self.assertRaises(ValidationError):
            registrar_transaccion(tipo=T.DEPOSITO, monto="1", cuenta_origen=self.c_ana)
        with self.assertRaises(ValidationError):
            registrar_transaccion(tipo=T.RETIRO, monto="1")

    def test_monedas_distintas_rechazadas(self):
        usd = crear_cuenta(self.luis, "0", moneda=Cuenta.Moneda.USD)
        with self.assertRaises(ValidationError):
            registrar_transaccion(tipo=T.TRANSFERENCIA, monto="1", cuenta_origen=self.c_ana, cuenta_destino=usd)

    def test_cuenta_inactiva_rechazada(self):
        Cuenta.objects.filter(pk=self.c_luis.pk).update(activa=False)
        self.c_luis.refresh_from_db()
        with self.assertRaises(ValidationError):
            registrar_transaccion(tipo=T.DEPOSITO, monto="10", cuenta_destino=self.c_luis)

    def test_no_se_puede_eliminar_cuenta_con_movimientos(self):
        registrar_transaccion(tipo=T.DEPOSITO, monto="10", cuenta_destino=self.c_luis)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.c_luis.delete()


class ConsultasTests(TestCase):
    def setUp(self):
        _, self.ana = crear_cliente("ana")
        _, self.luis = crear_cliente("luis")
        _, self.marta = crear_cliente("marta")
        self.a1 = crear_cuenta(self.ana, "1000")
        self.a2 = crear_cuenta(self.ana, "500")
        self.l1 = crear_cuenta(self.luis, "200")
        crear_cuenta(self.marta)
        registrar_transaccion(tipo=T.TRANSFERENCIA, monto="100", cuenta_origen=self.a1, cuenta_destino=self.l1)
        registrar_transaccion(tipo=T.DEPOSITO, monto="50", cuenta_destino=self.l1)

    def test_clientes_con_resumen(self):
        datos = {c.nombre: c for c in consultas.clientes_con_resumen()}
        self.assertEqual(datos["Ana"].num_cuentas, 2)
        self.assertEqual(datos["Ana"].saldo_total, Decimal("1400"))  # 900 + 500
        self.assertEqual(datos["Marta"].saldo_total, Decimal("0"))

    def test_clientes_sin_movimientos(self):
        self.assertEqual(list(consultas.clientes_sin_movimientos()), [self.marta])

    def test_cuentas_mas_activas(self):
        top = list(consultas.cuentas_mas_activas())
        self.assertEqual(top[0], self.l1)
        self.assertEqual(top[0].total_movimientos, 2)

    def test_filtrar_transacciones(self):
        qs = Transaccion.objects.all()
        self.assertEqual(consultas.filtrar_transacciones(qs, tipo=T.DEPOSITO).count(), 1)
        self.assertEqual(consultas.filtrar_transacciones(qs, monto_minimo=Decimal("75")).count(), 1)

    def test_ranking_raw(self):
        ranking = consultas.ranking_clientes_raw(2)
        self.assertEqual([c.nombre for c in ranking], ["Ana", "Luis"])
        self.assertEqual(Decimal(str(ranking[0].saldo_total)), Decimal("1400"))

    def test_resumen_por_tipo_con_cursor(self):
        resumen = {r["tipo"]: r for r in consultas.resumen_por_tipo_sql()}
        self.assertEqual(resumen["Depósito"]["cantidad"], 1)
        self.assertEqual(resumen["Transferencia"]["monto"], Decimal("100"))

    def test_visibilidad_por_usuario(self):
        self.assertEqual(consultas.cuentas_visibles(self.luis.usuario).count(), 1)
        self.assertEqual(consultas.transacciones_visibles(self.marta.usuario).count(), 0)
        staff = User.objects.create_user("jefe", is_staff=True)
        self.assertEqual(consultas.cuentas_visibles(staff).count(), 4)


class VistasTests(TestCase):
    def setUp(self):
        self.u_ana, self.ana = crear_cliente("ana")
        self.u_luis, self.luis = crear_cliente("luis")
        self.staff, _ = crear_cliente("jefe", staff=True)
        self.c_ana = crear_cuenta(self.ana, "1000")
        self.c_luis = crear_cuenta(self.luis, "0")

    def test_login_requerido(self):
        for nombre in ("inicio", "cliente_lista", "cuenta_lista", "transaccion_lista"):
            r = self.client.get(reverse(f"gestion:{nombre}"))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/login/", r.url)

    def test_login_y_logout(self):
        self.assertTrue(self.client.login(username="ana", password="clave-segura-123"))
        self.assertEqual(self.client.get(reverse("gestion:inicio")).status_code, 200)
        r = self.client.post(reverse("logout"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get(reverse("gestion:inicio")).status_code, 302)

    def test_registro_crea_usuario_y_cliente(self):
        r = self.client.post(reverse("gestion:registro"), {
            "username": "nuevo", "nombre": "Nuevo Usuario", "email": "nuevo@t.cl",
            "password1": "una-clave-larga-987", "password2": "una-clave-larga-987",
        })
        self.assertRedirects(r, reverse("gestion:inicio"))
        self.assertEqual(Cliente.objects.get(email="nuevo@t.cl").usuario.username, "nuevo")

    def test_csrf_se_exige_en_formularios(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.login(username="ana", password="clave-segura-123")
        r = c.post(reverse("gestion:cuenta_crear"), {"tipo": "VISTA", "moneda": "CLP"})
        self.assertEqual(r.status_code, 403)

    def test_formularios_incluyen_token_csrf(self):
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.get(reverse("gestion:cuenta_crear"))
        self.assertContains(r, "csrfmiddlewaretoken")

    def test_crud_cuentas(self):
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.post(reverse("gestion:cuenta_crear"), {"tipo": "AHORRO", "moneda": "CLP", "activa": "on"})
        cuenta = Cuenta.objects.get(cliente=self.ana, tipo="AHORRO")
        self.assertRedirects(r, cuenta.get_absolute_url())
        self.assertEqual(self.client.get(cuenta.get_absolute_url()).status_code, 200)
        self.client.post(reverse("gestion:cuenta_editar", args=[cuenta.pk]), {"tipo": "CORRIENTE"})
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.tipo, "CORRIENTE")
        self.assertFalse(cuenta.activa)  # checkbox sin marcar
        self.client.post(reverse("gestion:cuenta_eliminar", args=[cuenta.pk]))
        self.assertFalse(Cuenta.objects.filter(pk=cuenta.pk).exists())

    def test_no_elimina_cuenta_con_saldo(self):
        self.client.login(username="ana", password="clave-segura-123")
        self.client.post(reverse("gestion:cuenta_eliminar", args=[self.c_ana.pk]))
        self.assertTrue(Cuenta.objects.filter(pk=self.c_ana.pk).exists())

    def test_usuario_no_ve_datos_ajenos(self):
        self.client.login(username="ana", password="clave-segura-123")
        self.assertEqual(self.client.get(self.c_luis.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(self.luis.get_absolute_url()).status_code, 404)
        r = self.client.post(reverse("gestion:cuenta_eliminar", args=[self.c_luis.pk]))
        self.assertEqual(r.status_code, 404)

    def test_solo_staff_crea_clientes_y_ve_reportes(self):
        self.client.login(username="ana", password="clave-segura-123")
        self.assertEqual(self.client.get(reverse("gestion:cliente_crear")).status_code, 403)
        self.assertEqual(self.client.get(reverse("gestion:reportes")).status_code, 403)
        self.client.login(username="jefe", password="clave-segura-123")
        self.assertEqual(self.client.get(reverse("gestion:reportes")).status_code, 200)
        r = self.client.post(reverse("gestion:cliente_crear"), {"nombre": "Nueva", "email": "nueva@t.cl"})
        self.assertEqual(Cliente.objects.get(email="nueva@t.cl").telefono, None)
        self.assertEqual(r.status_code, 302)

    def test_crud_clientes_staff(self):
        self.client.login(username="jefe", password="clave-segura-123")
        cliente = Cliente.objects.create(nombre="Temporal", email="temp@t.cl")
        self.client.post(reverse("gestion:cliente_editar", args=[cliente.pk]), {"nombre": "Editado", "email": "temp@t.cl"})
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre, "Editado")
        self.client.post(reverse("gestion:cliente_eliminar", args=[cliente.pk]))
        self.assertFalse(Cliente.objects.filter(pk=cliente.pk).exists())

    def test_cliente_con_cuentas_no_se_elimina(self):
        self.client.login(username="jefe", password="clave-segura-123")
        self.client.post(reverse("gestion:cliente_eliminar", args=[self.ana.pk]))
        self.assertTrue(Cliente.objects.filter(pk=self.ana.pk).exists())

    def test_crear_transaccion_via_formulario(self):
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.post(reverse("gestion:transaccion_crear"), {
            "tipo": "TRANSFERENCIA", "cuenta_origen": self.c_ana.pk,
            "cuenta_destino": self.c_luis.pk, "monto": "250.00", "descripcion": "Prueba",
        })
        trx = Transaccion.objects.get()
        self.assertRedirects(r, trx.get_absolute_url())
        self.c_luis.refresh_from_db()
        self.assertEqual(self.c_luis.saldo, Decimal("250"))

    def test_formulario_muestra_error_por_saldo_insuficiente(self):
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.post(reverse("gestion:transaccion_crear"), {
            "tipo": "RETIRO", "cuenta_origen": self.c_ana.pk, "monto": "9999",
        })
        self.assertContains(r, "Saldo insuficiente")
        self.assertEqual(Transaccion.objects.count(), 0)

    def test_no_puede_usar_cuenta_origen_ajena(self):
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.post(reverse("gestion:transaccion_crear"), {
            "tipo": "RETIRO", "cuenta_origen": self.c_luis.pk, "monto": "1",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Transaccion.objects.count(), 0)

    def test_no_puede_depositar_en_cuenta_ajena(self):
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.post(reverse("gestion:transaccion_crear"), {
            "tipo": "DEPOSITO", "cuenta_destino": self.c_luis.pk, "monto": "10",
        })
        self.assertContains(r, "Solo puedes depositar")

    def test_filtros_del_listado(self):
        registrar_transaccion(tipo=T.DEPOSITO, monto="10", cuenta_destino=self.c_ana)
        registrar_transaccion(tipo=T.RETIRO, monto="5", cuenta_origen=self.c_ana)
        self.client.login(username="ana", password="clave-segura-123")
        r = self.client.get(reverse("gestion:transaccion_lista"), {"tipo": "RETIRO"})
        self.assertEqual(len(r.context["transacciones"]), 1)

    def test_admin_accesible_solo_para_superusuario(self):
        User.objects.create_superuser("root", "r@t.cl", "clave-segura-123")
        self.client.login(username="root", password="clave-segura-123")
        for modelo in ("cliente", "cuenta", "transaccion"):
            self.assertEqual(self.client.get(f"/admin/gestion/{modelo}/").status_code, 200)
        self.client.login(username="ana", password="clave-segura-123")
        self.assertEqual(self.client.get("/admin/").status_code, 302)
