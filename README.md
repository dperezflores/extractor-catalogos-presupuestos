# Extractor inteligente de catálogos

Aplicación multiusuario en Streamlit para leer visualmente presupuestos escaneados mediante OpenAI, generar un catálogo estructurado y, opcionalmente, buscar los conceptos de un archivo Excel.

## Funcionalidades incluidas

- Autenticación con Google mediante OpenID Connect.
- Lista privada de correos autorizados.
- API key individual, almacenada únicamente durante la sesión.
- PDF obligatorio y Excel de búsqueda opcional.
- Extracción visual con `gpt-5.6-luna` y detalle alto.
- División del PDF en bloques con traslape configurable.
- Checkpoints por usuario, PDF y bloque.
- Reanudación sin reprocesar bloques terminados.
- Validaciones deterministas sin consumo adicional de API.
- Vista previa del catálogo y del cruce opcional.
- Descarga del catálogo completo y del Excel con precios.
- SQLite para desarrollo y PostgreSQL para despliegue persistente.
- Interfaz institucional con los colores `#FF5E12`, `#FF7D42`, `#362D32` y `#00304F`.

## Arquitectura

```text
app.py                          Punto de entrada único
src/
├── application.py             Composición y navegación de Streamlit
├── config.py                  Configuración central
├── domain/
│   └── models.py              Entidades y esquemas Pydantic
├── repositories/
│   └── checkpoint_repository.py  Persistencia de trabajos y bloques
├── services/
│   ├── auth_service.py        Identidad y autorización
│   ├── excel_service.py       Generación y modificación de Excel
│   ├── matching_service.py    Coincidencia de conceptos
│   ├── openai_extractor.py    Lectura visual mediante OpenAI
│   ├── pdf_service.py         División del PDF
│   ├── processing_service.py  Orquestación del caso de uso
│   └── validation_service.py  Validaciones gratuitas
├── ui/
│   ├── components.py          Componentes visuales
│   └── style_loader.py        Cargador de estilos
assets/
└── styles.css                 Diseño institucional independiente
```

El diseño utiliza orientación a objetos y separación de responsabilidades. `app.py` solamente inicia `CatalogApplication`.

## Instalación local

Requiere Python 3.11 o posterior.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS o Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración local

1. Copia `.streamlit/secrets.example.toml` como `.streamlit/secrets.toml`.
2. Completa las credenciales de Google.
3. Agrega los correos autorizados.
4. Para probar sin Google, establece temporalmente:

```toml
[application]
auth_required = false
```

El archivo `secrets.toml` está excluido de Git y nunca debe publicarse.

## Configuración de Google

En Google Cloud crea un cliente OAuth de tipo **Web application** y registra:

```text
http://localhost:8501/oauth2callback
```

Para Streamlit Community Cloud registra también:

```text
https://TU-APLICACION.streamlit.app/oauth2callback
```

El alcance utilizado por Streamlit es `openid profile email`; la aplicación no solicita acceso a Gmail ni Google Drive.

## Base de datos

Para desarrollo:

```toml
[database]
url = "sqlite:///data/checkpoints.db"
```

Para producción debe usarse una base persistente:

```toml
[database]
url = "postgresql+psycopg://USUARIO:PASSWORD@HOST:5432/BASE"
```

La base de datos guarda usuario, huella del PDF, avance, resultados estructurados y consumo. No almacena la API key ni el PDF.

## Ejecución

```bash
streamlit run app.py
```

## Despliegue desde GitHub

1. Publica el repositorio sin `.streamlit/secrets.toml`.
2. Crea la aplicación en Streamlit Community Cloud.
3. Selecciona `app.py` como archivo principal.
4. Copia los secretos en **App settings → Secrets**.
5. Configura una base PostgreSQL externa para conservar checkpoints después de reinicios.
6. Actualiza `redirect_uri` tanto en Streamlit como en Google Cloud.

## Flujo de reanudación

Cada PDF recibe una huella SHA-256. Cada bloque terminado se guarda antes de avanzar. Si ocurre un error, el usuario vuelve a ingresar, carga el mismo PDF y el sistema recupera los bloques completados. Solamente el primer bloque pendiente vuelve a enviarse a la API.

La clave del caché incluye:

```text
usuario + hash PDF + modelo + detalle + versión del esquema + configuración de bloques
```

Cambiar el modelo, el detalle, el esquema o la configuración de bloques crea un
procesamiento nuevo para evitar reutilizar resultados incompatibles.

El repositorio incluye una acción de GitHub que ejecuta automáticamente las pruebas y
el análisis estático en cada `push` y `pull_request`.

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest -q
ruff check .
```

Las pruebas no hacen llamadas reales a OpenAI.

## Seguridad

- La API key se crea directamente dentro de la sesión del usuario.
- Nunca se asigna a `os.environ` porque el proceso de Streamlit es compartido.
- Nunca se incluye como argumento de una función cacheada.
- Los mensajes de error ocultan patrones con formato de API key.
- Los trabajos se consultan obligatoriamente por el identificador Google del usuario.
- Los secretos de OAuth y la URL de base de datos se administran mediante los secretos del despliegue.

## Fuentes técnicas

- [Entradas de archivos PDF en OpenAI](https://developers.openai.com/api/docs/guides/file-inputs)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [Autenticación de Google en Streamlit](https://docs.streamlit.io/develop/tutorials/authentication/google)
