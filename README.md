# Partituras de Ocarina

Generador de hojas de música con los botones de la ocarina de *Ocarina of Time* (N64, 3DS y el remake de Switch 2), con una comunidad para compartirlas.
La interfaz está en español e inglés.

La hoja se arma en páginas tamaño carta: así se ve, se imprime y se exporta. Si tiene varias páginas, PNG y SVG se descargan juntos en un `.zip`.

El **modo ritmo** muestra la canción con notas que caen hasta una línea, para tocarla en tu consola con el tiempo correcto y sin mover la hoja. La página no se conecta con la consola: es solo una guía visual.

## Comunidad

- **Compartir**: el botón *Compartir* del editor publica la partitura y da un enlace `/s/<id>`. Quien lo abra la ve en el editor, con reproducción, modo ritmo y exportación. Puede salir en la galería o quedar solo con enlace.
- **Galería** (`/comunidad`): tendencias (más *me gusta* en los últimos 7 días), más votadas, recientes, búsqueda por título y filtro por juego.
- **Me gusta y comentarios** en cada partitura compartida.
- **Sin cuentas**: cada navegador recibe un código secreto de dispositivo la primera vez que comparte, vota, comenta o reporta. En *Mis partituras* (`/comunidad?u=me`) se cambia el nombre y se copia ese código para usar la misma identidad en otro navegador. Si se borran los datos del navegador sin haber copiado el código, se pierde la propiedad de esas partituras.
- **Moderación**: cualquiera puede reportar una partitura o un comentario. Con 3 reportes de dispositivos distintos se oculta hasta que un admin lo revise en `/comunidad?admin` (restaurar, eliminar o bloquear al autor).

## Estructura

```
site/                 ← páginas y recursos estáticos (los sirve el backend)
  index.html          el editor completo (HTML + CSS + JS)
  comunidad.html      galería, perfiles y moderación
  i18n.js             textos en español e inglés
  api.js              cliente de la API y código de dispositivo
  fonts/              fuente Almendra (títulos), servida desde el propio sitio
  vendor/             JSZip, se carga solo al importar archivos .mxl
  favicon.svg, apple-touch-icon.png, og.png, robots.txt, sitemap.xml
  _headers            cabeceras para Cloudflare Pages (solo si publicas el editor sin backend)
server/               ← backend (FastAPI + PostgreSQL)
  main.py             API y servidor de site/
  schema.sql          tablas; se aplica sola al arrancar
  test_api.py         prueba de toda la API contra un Postgres real
Dockerfile, docker-compose.yml, .env.example
tools/                ← no se publica
  extract_clef.py     saca el trazo de la clave de sol de Noto Music
  og.html, icon.html  plantillas de la imagen para redes y del ícono
  build-images.ps1    genera og.png y apple-touch-icon.png con Edge headless
```

## Probar en local

**Todo (editor + comunidad) con Docker**

```bash
cp .env.example .env
```

Cambia las contraseñas en `.env` y luego:

```bash
docker compose up --build
```

Abrir http://localhost:8000 (o el puerto de `WEB_PORT`).

**Sin Docker**: necesitas Python 3.12+ y un PostgreSQL con una base vacía en UTF-8.

```bash
pip install -r server/requirements.txt
```

```bash
cd server && DATABASE_URL=postgresql://usuario:clave@localhost:5432/ocarina ADMIN_TOKEN=algo uvicorn main:app --port 8000
```

**Solo el editor**, sin comunidad (compartir, galería y comentarios mostrarán un error de conexión):

```bash
python -m http.server 8765 --directory site
```

### Pruebas de la API

Usa una base de datos **vacía y de prueba**: la prueba borra las tablas al empezar.

```bash
pip install pytest httpx
```

```bash
cd server && DATABASE_URL=postgresql://usuario:clave@localhost:5432/ocarina_test pytest test_api.py
```

## Desplegar en Dokploy

El `docker-compose.yml` levanta dos servicios: `web` (FastAPI, sirve la API y el sitio en el puerto 8000) y `db` (PostgreSQL 17 con el volumen `pgdata`).

1. En Dokploy: **Projects** → tu proyecto → **Create Service** → **Compose**.
2. **Provider**: GitHub, repositorio `R3nE88/ocarina`, la rama que quieras publicar, **Compose Path** `./docker-compose.yml`.
3. **Environment**: define al menos
   ```
   POSTGRES_PASSWORD=una-clave-larga
   ADMIN_TOKEN=otra-clave-larga
   ```
   `REPORT_THRESHOLD` (reportes para ocultar, por defecto 3) y `WEB_PORT` son opcionales.
4. **Domains** → **Add Domain**: host `ocarina.forja-digital.com`, service `web`, container port `8000`, HTTPS activado con Let's Encrypt.
5. **Deploy**. Las tablas se crean solas en el primer arranque.
6. DNS: apunta `ocarina` (registro A) a la IP del servidor de Dokploy. Si el DNS está en Cloudflare con el proxy naranja, pon SSL/TLS en **Full**. Después borra el dominio del proyecto de Cloudflare Pages para que no compitan.

Notas:

- `web` también publica `127.0.0.1:8000` en el servidor, solo para pruebas locales. Si ese puerto ya está ocupado en tu servidor, cambia `WEB_PORT`.
- Los límites de frecuencia (cuántas partituras, comentarios o reportes por hora) viven en memoria del proceso: corre **una sola réplica** de `web`.
- **Respaldos**: en Dokploy, **Volume Backups** del volumen `pgdata`, o a mano:
  ```bash
  docker compose exec db pg_dump -U ocarina ocarina > respaldo.sql
  ```
- **Moderación**: entra a `https://ocarina.forja-digital.com/comunidad?admin` con el `ADMIN_TOKEN`. Si lo dejas vacío, la moderación queda desactivada (los reportes igual ocultan contenido).
- **Métricas**: Cloudflare Web Analytics ya no se inyecta solo fuera de Pages. Si lo quieres, en Cloudflare → **Web Analytics** → **Add a site** te da un `<script>` para pegar antes de `</body>` en `site/index.html` y `site/comunidad.html`.

Si algún día cambia el dominio, reemplázalo en:
`site/index.html` (canonical, og:url, og:image), `site/comunidad.html` (og:image), `site/robots.txt` y `site/sitemap.xml`.

## Regenerar las imágenes

```bash
powershell -ExecutionPolicy Bypass -File tools/build-images.ps1
```
