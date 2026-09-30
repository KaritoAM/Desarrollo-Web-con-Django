## Estructura del proyecto

alke_wallet_project/
├── manage.py
├── alke_wallet/              # Proyecto: configuración
│   ├── settings.py           # BD (SQLite/PostgreSQL), apps, estáticos, login
│   ├── urls.py               # /admin, /login, /logout y rutas de gestion
│   └── formats/es/           # Formato numérico chileno (1.234,56)
├── gestion/                  # App principal
│   ├── models.py             # Cliente, Cuenta, Transaccion
│   ├── services.py           # Lógica de negocio: registrar_transaccion()
│   ├── consultas.py          # filter/exclude/annotate, raw() y cursores
│   ├── forms.py              # Formularios (ModelForm) con validaciones
│   ├── views.py              # Vistas basadas en clases (CRUD)
│   ├── urls.py               # Rutas dinámicas (<int:pk>)
│   ├── admin.py              # Registro en django.contrib.admin
│   ├── tests.py              # 40 pruebas automáticas
│   ├── migrations/           # Historial versionado del esquema
│   └── management/commands/cargar_datos_demo.py
├── templates/                # base.html, registration/, gestion/
├── static/css/alke.css       # Estilos (django.contrib.staticfiles)
├── requirements.txt          # Desarrollo
└── requirements-prod.txt     # Producción (agrega psycopg2)


## Instalación y ejecución local

Requisitos: Python 3.10+ y Visual Studio Code.

```bash
# 1. Entorno virtual (desde la terminal integrada de VS Code)
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Dependencias
pip install -r requirements.txt

# 3. Base de datos
python manage.py migrate

# 4. Datos de ejemplo (solo desarrollo) y/o superusuario propio
python manage.py cargar_datos_demo
python manage.py createsuperuser  # opcional

# 5. Servidor
python manage.py runserver
```

Abre <http://127.0.0.1:8000/>. Con `cargar_datos_demo` quedan estos usuarios (**solo para desarrollo**):

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin` | `admin1234` | Superusuario / staff |
| `ana`, `luis`, `marta` | `demo1234` | Clientes |


## Base de datos

```bash
pip install -r requirements-prod.txt      # incluye psycopg2-binary

export DB_ENGINE=postgres
export DB_NAME=alke_wallet
export DB_USER=alke
export DB_PASSWORD='tu-clave'
export DB_HOST=localhost
export DB_PORT=5432

python manage.py migrate
```

## Migraciones

```bash
python manage.py makemigrations gestion   # genera gestion/migrations/0001_initial.py
python manage.py migrate                  # aplica al esquema
python manage.py showmigrations           # historial
python manage.py sqlmigrate gestion 0001  # ver el SQL generado
```

## Consultas personalizadas y CRUD en la shell

`python manage.py shell`

```python
from decimal import Decimal
from gestion.models import Cliente, Cuenta, Transaccion
from gestion.services import registrar_transaccion

# --- Crear
ana = Cliente.objects.create(nombre="Ana García", email="ana@example.com", telefono="123456789")
luis = Cliente.objects.create(nombre="Luis Pérez", email="luis@example.com")
c_ana = Cuenta.objects.create(cliente=ana, tipo="AHORRO")
c_luis = Cuenta.objects.create(cliente=luis)

# --- Leer
Cliente.objects.all()
Cliente.objects.filter(nombre__istartswith="A")
Cliente.objects.exclude(telefono__isnull=True)

# --- Actualizar
luis.telefono = "987654321"
luis.save()

# --- Mover dinero (siempre con el servicio, nunca editando saldo)
registrar_transaccion(tipo="DEPOSITO", monto=Decimal("100000"), cuenta_destino=c_ana)
registrar_transaccion(tipo="TRANSFERENCIA", monto=Decimal("25000"),
                      cuenta_origen=c_ana, cuenta_destino=c_luis, descripcion="Almuerzo")

# --- Eliminar (un cliente sin cuentas)
Cliente.objects.create(nombre="Temporal", email="t@example.com").delete()
```

```python
from gestion import consultas

consultas.clientes_con_resumen()        # annotate: Count de cuentas + Sum de saldo
consultas.cuentas_mas_activas(5)        # annotate: entradas + salidas
consultas.clientes_sin_movimientos()    # exclude con relaciones inversas
consultas.filtrar_transacciones(Transaccion.objects.all(), tipo="RETIRO", monto_minimo=1000)
consultas.ranking_clientes_raw(5)       # SQL con Manager.raw() y parámetros (%s)
consultas.resumen_por_tipo_sql()        # SQL con connection.cursor()
```

Ejemplo directo con `raw()` y cursor:

```python
Cliente.objects.raw("SELECT * FROM gestion_cliente WHERE telefono IS NOT NULL")

from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) FROM gestion_cliente")
    print("Total de clientes:", cursor.fetchone()[0])
```

> Los valores variables siempre van como parámetros (`%s`), nunca concatenados en el SQL, para evitar inyección SQL.

## Vistas y rutas

Todas son vistas basadas en clases (`ListView`, `DetailView`, `CreateView`, `UpdateView`, `DeleteView`, `TemplateView`, `FormView`).

| Ruta | Vista | Acceso |
|---|---|---|
| `/` | Resumen: saldo, cuentas, últimos movimientos | Autenticado |
| `/login/`, `/logout/`, `/registro/` | Sesión y alta de usuario (crea también el `Cliente`) | Público / autenticado |
| `/clientes/`, `/clientes/<pk>/`, `/clientes/<pk>/editar/` | Listado (con búsqueda), detalle, edición | Cada usuario ve lo suyo; staff todo |
| `/clientes/nuevo/`, `/clientes/<pk>/eliminar/` | Crear y eliminar cliente | Solo staff |
| `/cuentas/`, `/cuentas/nueva/`, `/cuentas/<pk>/`, `/editar/`, `/eliminar/` | CRUD de cuentas | Dueño o staff |
| `/transacciones/`, `/transacciones/nueva/`, `/transacciones/<pk>/` | Historial con filtros, alta y detalle | Involucrados o staff |
| `/reportes/` | Reportes con `raw()`, cursor, `annotate` y `exclude` | Solo staff |
| `/admin/` | Administración | Staff |


## Seguridad

* Todos los formularios `POST` incluyen `{% csrf_token %}` y `CsrfViewMiddleware` está activo (hay una prueba que confirma el 403 sin token).
* Las vistas exigen sesión; los querysets se filtran por usuario, así que acceder a un `pk` ajeno devuelve 404.
* Contraseñas con los validadores de Django; SQL crudo parametrizado; secretos por variables de entorno.
* Cierre de sesión por `POST`.


## Flujo de trabajo con Git

```bash
git init
git add . && git commit -m "feat: proyecto base"
git checkout -b feature/modelos      # modelos, migraciones y consultas
git checkout -b feature/crud         # vistas, formularios y templates
git remote add origin https://github.com/<tu-usuario>/alke-wallet.git
git push -u origin main --all
```

