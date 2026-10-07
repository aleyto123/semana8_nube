# TechStore

Aplicación web para gestionar inventario de productos tecnológicos por tienda, con autenticación multifactor y permisos por rol. Desarrollada para el Laboratorio 08 de Desarrollo de Soluciones en la Nube.

## Tecnologías

- **Frontend:** HTML, CSS y JavaScript modular.
- **Servidor:** Python 3.10 o superior, usando su biblioteca estándar.
- **Persistencia:** SQLite.
- **Autenticación:** contraseñas derivadas con scrypt, JWT firmado y MFA con TOTP.

No requiere instalar paquetes ni compilar el frontend. La tipografía Manrope se carga desde Google Fonts; si no hay conexión, se utiliza una fuente del sistema.

## Inicio rápido

Clona el repositorio y ejecuta el servidor desde la carpeta del proyecto:

```powershell
git clone https://github.com/aleyto123/semana8_nube.git
cd semana8_nube
python app.py
```

Abre [TechStore](http://localhost:8000). Para detener el servidor, presiona `Ctrl+C` en la terminal.

### Explorar sin crear una cuenta

Accede al [dashboard de demostración](http://localhost:8000/dashboard?demo=1). El selector superior permite explorar los cuatro roles.

La demo incluye productos, tiendas, usuarios, movimientos y auditoría ficticios. Permite crear y editar productos, ajustar stock, aplicar filtros y exportar reportes CSV. Sus cambios se guardan en la sesión de la pestaña y no modifican la base de datos real. Se pueden restablecer desde **Configuración** en el rol administrador.

### Crear una cuenta real

1. Abre [Crear cuenta](http://localhost:8000/register).
2. Registra nombre, email, tienda y una contraseña de al menos ocho caracteres, con una mayúscula, un número y un carácter especial.
3. Inicia sesión y agrega la clave mostrada a Google Authenticator u otra aplicación compatible con TOTP.
4. Ingresa el código de seis dígitos para completar el acceso.

El registro público crea empleados. No existe una cuenta de administrador predeterminada.

### Crear el administrador

Antes de iniciar el servidor, establece un correo y una contraseña propios en la misma terminal:

```powershell
$env:ADMIN_EMAIL = 'tu-correo@empresa.com'
$env:ADMIN_PASSWORD = 'ReemplazaEstaClave1!'
python app.py
```

La contraseña del ejemplo debe reemplazarse por una propia que cumpla los requisitos. Estas variables crean el administrador si su email aún no existe; no cambian la contraseña ni el rol de una cuenta existente. El primer acceso también requiere configurar MFA.

## Funcionalidades

### Acceso conectado al servidor

- Registro con email único y validación de contraseña.
- Bloqueo de cuenta durante 15 minutos después de cinco intentos fallidos.
- MFA TOTP: códigos de seis dígitos cada 30 segundos, desafío de cinco minutos y máximo tres intentos incorrectos.
- JWT con duración de una hora, emitido después de verificar MFA y conservado en memoria del navegador.
- Inicio de sesión con Google y GitHub, cuando se configuran las credenciales OAuth.
- Consulta, creación, edición y eliminación de productos según permisos.
- Actualización de stock y exportación CSV.
- Asignación de roles y tiendas por el administrador.

### Experiencia visual y demostración

- Landing con vista del producto, funcionalidades, seguridad y perfiles interactivos.
- Pantallas de login, registro y MFA con validación y mensajes de estado.
- Dashboard, catálogo con búsqueda, filtros y paginación, detalle de producto y modales de edición.
- Inventario, tiendas, usuarios, reportes, movimientos, auditoría, perfil y configuración.
- Navegación móvil, tablas adaptadas a tarjetas y soporte para movimiento reducido.

El historial de movimientos y accesos, la auditoría, los campos descriptivos adicionales del producto y el cambio de contraseña se muestran como demostración o como funciones pendientes cuando no existe un servicio en el servidor. El acceso real no sustituye datos faltantes por datos ficticios.

## Roles

| Rol | Permisos |
| --- | --- |
| Administrador | Gestiona usuarios, roles y productos de todas las tiendas; consulta y exporta reportes. |
| Gerente de tienda | Gestiona productos, stock y reportes de su tienda. |
| Empleado de ventas | Consulta productos y actualiza stock de su tienda; no modifica precios ni elimina productos. |
| Auditor | Consulta información y exporta reportes; no modifica datos. |

Los permisos del acceso real se validan en el servidor. Las tiendas disponibles en este modo son **Lima** y **Arequipa**. La demo usa cuatro ubicaciones ficticias independientes.

## Google y GitHub

Registra una aplicación OAuth en cada proveedor y configura sus URLs de retorno:

| Proveedor | URL de retorno local |
| --- | --- |
| Google | `http://localhost:8000/auth/google/callback` |
| GitHub | `http://localhost:8000/auth/github/callback` |

Establece las variables antes de ejecutar `python app.py`:

```powershell
$env:GOOGLE_CLIENT_ID = 'tu-client-id'
$env:GOOGLE_CLIENT_SECRET = 'tu-client-secret'
$env:GITHUB_CLIENT_ID = 'tu-client-id'
$env:GITHUB_CLIENT_SECRET = 'tu-client-secret'
```

Sin estas credenciales, la interfaz informa que falta configuración. El inicio social requiere conexión a Internet, email verificado y MFA local. Las cuentas nuevas se crean como empleados asignados a Lima.

El servidor lee variables de entorno; **no carga archivos `.env` automáticamente**. `PORT` permite cambiar el puerto y `BASE_URL` la URL utilizada para los retornos OAuth. Si se modifica el puerto, ambas configuraciones deben coincidir.

## Estructura

```text
semana8_nube/
├── app.py          # Servidor, API, autenticación y persistencia
├── index.html      # Entrada del frontend
├── app.js          # Landing, identidad visual y utilidades
├── screens.js      # Autenticación y vistas operativas
├── data.js         # Datos ficticios de demostración
├── styles.css      # Componentes y estilos responsive
├── favicon.svg     # Isotipo de TechStore
├── test_app.py     # Pruebas de autenticación y permisos
├── .gitignore      # Exclusiones para Git
└── README.md
```

Al ejecutarse se generan `techstore.db` y `.jwt-secret`. Contienen datos locales y una clave de firma, respectivamente; ambos están excluidos de Git.

## Verificación

Ejecuta las pruebas desde la carpeta del proyecto:

```powershell
python -m unittest -v test_app.py
```

Las cinco pruebas verifican registro, bloqueo tras intentos fallidos, MFA y permisos por rol y tienda. La revisión del frontend cubrió 48 combinaciones de rutas y tamaños entre 360 y 1920 píxeles sin desbordamiento horizontal, además de creación/búsqueda de productos, ajustes de stock y pegado del código MFA demo.

## Subir los archivos a GitHub

Si trabajas con una carpeta descargada que todavía no es un repositorio, ejecuta desde la carpeta que contiene `app.py`:

```powershell
git init
git branch -M main
git remote add origin https://github.com/aleyto123/semana8_nube.git
```

Si la carpeta ya fue clonada, omite esos pasos. Antes de subir, revisa los archivos incluidos:

```powershell
git status --short
git add .
git diff --cached --stat
git commit -m "Agrega TechStore con frontend, inventario y MFA"
git push -u origin main
```

El `.gitignore` excluye credenciales, bases de datos, entornos virtuales, cachés y archivos temporales. Git no deja de rastrear archivos que ya estaban en un commit solo por añadirlos al `.gitignore`; si se publicaron credenciales previamente, deben retirarse del seguimiento y reemplazarse.

## Alcance

Proyecto académico para ejecución local. El servidor escucha en `127.0.0.1`. Un despliegue público requiere adaptar el servidor y la gestión de secretos, usar HTTPS y completar los servicios que actualmente están disponibles solo en demostración.

## Conclusiones

1. La autenticación y los permisos cumplen funciones distintas dentro del sistema. Su aplicación conjunta permite controlar tanto el acceso como las operaciones de cada usuario.
2. La autenticación multifactor añade protección frente al uso indebido de una contraseña. El segundo código reduce la posibilidad de que una cuenta comprometida permita acceder al inventario.
3. El límite de intentos fallidos ayuda a frenar los accesos repetidos con credenciales incorrectas. Los mensajes claros permiten comprender el bloqueo y saber cuándo volver a intentar.
4. La organización del inventario por tienda facilita el seguimiento de los productos disponibles. Los filtros y las alertas de stock ayudan a identificar las necesidades de reposición.
5. Una interfaz ordenada facilita las consultas y las actualizaciones del inventario. La adaptación a distintos tamaños de pantalla permite mantener esa facilidad de uso desde el celular.
