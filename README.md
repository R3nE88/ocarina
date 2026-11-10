# Partituras de Ocarina

Generador de hojas de música con los botones de la ocarina de *Ocarina of Time* (N64, 3DS y el remake de Switch 2).
Todo corre en el navegador: no hay backend.

El **modo ritmo** muestra la canción con notas que caen hasta una línea, para tocarla en tu consola con el tiempo correcto y sin mover la hoja. La página no se conecta con la consola: es solo una guía visual.

## Estructura

```
site/                 ← lo que se publica (Cloudflare Pages)
  index.html          la app completa (HTML + CSS + JS)
  fonts/              fuente Almendra (títulos), servida desde el propio sitio
  vendor/             JSZip, se carga solo al importar archivos .mxl
  favicon.svg, apple-touch-icon.png, og.png
  _headers            caché y cabeceras de seguridad para Cloudflare Pages
  robots.txt, sitemap.xml
tools/                ← no se publica
  extract_clef.py     saca el trazo de la clave de sol de Noto Music
  og.html, icon.html  plantillas de la imagen para redes y del ícono
  build-images.ps1    genera og.png y apple-touch-icon.png con Edge headless
```

## Probar en local

```bash
python -m http.server 8765 --directory site
```

Abrir http://localhost:8765

## Publicar en Cloudflare Pages

**Opción A — subir la carpeta (lo más simple)**

1. Entra a https://dash.cloudflare.com → **Workers & Pages** → **Create** → pestaña **Pages** → **Upload assets**.
2. Nombre del proyecto: `ocarina-sheets` (quedará en `https://ocarina-sheets.pages.dev`).
3. Arrastra la carpeta `site` y pulsa **Deploy**.
4. Para actualizar: en el proyecto → **Create deployment** → vuelve a arrastrar `site`.

**Opción B — desde la terminal**

```bash
npx wrangler login
npx wrangler pages deploy site --project-name ocarina-sheets
```

**Opción C — conectado a GitHub (deploy automático en cada push)**

Sube el proyecto a un repositorio y en Pages elige **Connect to Git**:
framework preset **None**, build command vacío, output directory `site`.

### Dominio: https://ocarina.forja-digital.com

1. En el proyecto de Pages → **Custom domains** → **Set up a custom domain** → `ocarina.forja-digital.com`.
2. Si el DNS de `forja-digital.com` está en Cloudflare, el registro se crea solo.
   Si no, crea en tu proveedor de DNS un **CNAME** `ocarina` → `ocarina-sheets.pages.dev`.
3. Espera a que el dominio aparezca como **Active** (el certificado HTTPS es automático).

Si algún día cambia el dominio, reemplázalo en:
`site/index.html` (canonical, og:url, og:image), `site/robots.txt` y `site/sitemap.xml`.

## Métricas de visitas

En el proyecto de Pages → **Metrics** → **Web Analytics** → **Enable**.
Cloudflare inyecta el script solo; no hay que tocar el código. No usa cookies, así que no requiere banner de consentimiento.

## Regenerar las imágenes

```bash
powershell -ExecutionPolicy Bypass -File tools/build-images.ps1
```
