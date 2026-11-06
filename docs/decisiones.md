# Decisiones de arquitectura — Backend (bria API)

Registro de las decisiones técnicas tomadas durante la implementación. Cada entrada
documenta el contexto, la decisión y la razón, para que sea defendible en la tesis.

## ADR-001 — SQLAlchemy 2.0 con sesiones síncronas

**Contexto.** El backend es un monolito modular hexagonal. Su carga real es CRUD ligero
y orquestación; la única operación pesada (forecasting) se delega a un servicio externo
(FTGM Engine) por HTTP. La escala objetivo son MYPEs de Lima (baja concurrencia).

**Decisión.** Usar **SQLAlchemy 2.0** (estilo `Mapped`/`mapped_column`) con **sesiones
síncronas** y driver `psycopg` v3. Las migraciones se gestionan con **Alembic**. El modelo
ORM se mantiene **separado** de la entidad de dominio mediante mappers.

**Razones.**
- SQLAlchemy + Alembic es el estándar maduro con mejor soporte de migraciones.
- Separar ORM de dominio respeta la regla hexagonal (el dominio no depende de la
  persistencia), que es el argumento arquitectónico central de la tesis. Por eso se
  descartó SQLModel, que fusiona Pydantic + ORM en una sola clase.
- El modo síncrono es más simple, mejor documentado y con menos trampas (greenlet, libs
  async-compatibles, Alembic async, tests async). FastAPI ejecuta los endpoints síncronos
  en un threadpool, así que no se pierde concurrencia para esta escala.

## ADR-002 — Forecasting como trabajo en segundo plano (no async global)

**Contexto.** La llamada al FTGM Engine es la única operación lenta y de I/O potencialmente
largo. Resolverla dentro del request bloquearía la petición.

**Decisión.** El forecasting se ejecuta como **trabajo en segundo plano con polling de
estado**, no convirtiendo el backend a async. El patrón es: el endpoint de ejecución crea
el `ForecastRun`, responde **202** de inmediato, un worker procesa en background y el
cliente consulta el estado por `/forecast-runs/{run_id}/status`. Los endpoints
`execute`, `status`, `cancel`, `retry` y `logs` ya existen para soportarlo.

**Razones.**
- Aísla la única operación lenta sin imponer el coste de async a las 288 rutas.
- En la primera fase el worker será `BackgroundTasks` de FastAPI; a futuro se sustituye por
  una cola real (Celery/RQ/Arq) detrás del `QueuePort` ya definido en
  `app/shared/infrastructure/ports.py`. La frontera (el puerto) no cambia.

## ADR-003 — Multi-tenancy por `company_id`

**Decisión.** Las entidades de negocio cuelgan de una empresa vía `CompanyOwnedMixin`
(`company_id` indexado). El acceso se valida en la capa de presentación con
`require_company_access`, que compara el `company_id` de la ruta contra el de los claims
del JWT del usuario autenticado.

## ADR-004 — Sesión transaccional por request (commit en `get_db`)

**Contexto.** Algunos casos de uso escriben varias entidades (p. ej. `RegisterAccount`
crea Company + User OWNER) y deben ser atómicos. Los casos de uso dependen solo de los
puertos de repositorio (testeables con fakes), así que no pueden hacer `commit`.

**Decisión.** `get_db` abre una sesión, hace `yield`, y al terminar el handler con éxito
hace `commit` una sola vez; ante cualquier excepción hace `rollback`. Los repositorios solo
hacen `flush()` (nunca `commit`). Como todos los providers dependen del mismo `get_db`,
FastAPI cachea la sesión dentro del request: varias escrituras comparten una transacción.

## ADR-005 — Hashing con `bcrypt` directo (sin passlib)

**Contexto.** `passlib` está prácticamente sin mantenimiento y su backend bcrypt es
incompatible con `bcrypt >= 4.x` (falla al inicializar). Los tests lo destaparon.

**Decisión.** `app/shared/infrastructure/security/hashing.py` usa la librería `bcrypt`
directamente. Se trunca la contraseña a 72 bytes (límite de bcrypt) de forma explícita y
consistente en hash y verify. Se quitó `passlib[bcrypt]` de las dependencias.

## ADR-006 — Patrón de capas en Bloque 2 (referencia canónica)

**Decisión.** Patrón que replican los demás módulos:
- `infrastructure/persistence/`: modelo ORM separado de la entidad + mappers explícitos +
  repositorio SQLAlchemy que implementa el puerto del dominio.
- `application/`: casos de uso (una clase con `execute()`, puertos inyectados por
  constructor) que reciben parámetros tipados como entrada y devuelven **DTOs Pydantic**
  de salida (`dtos.py`). El dominio sigue puro; Pydantic solo se permite desde `application`
  hacia afuera.
- `presentation/`: schemas de request, `dependencies.py` con los providers DI, y router que
  cablea cada endpoint a su caso de uso. La autorización multi-tenant se aplica con
  `require_company_access` / `require_role`.
- Email de usuario **único global** (lo exige el login por email).

## ADR-007 — Alcance del Bloque 2 (persistencia + casos de uso)

**Implementados** (8 módulos con dominio del Bloque 1): auth, companies, products, sales,
inventory, ingestion, data_preparation, forecasting, kpis, recommendations.

**Diferidos**: los módulos sin capa de dominio (notifications, files, reports, audit,
dashboard, admin, billing, validation) NO se implementan en Bloque 2 porque primero
necesitan su modelado de dominio (un "Bloque 1.5"). Sus routers siguen como placeholder.

**Lógica de negocio cross-módulo diferida**: el cálculo automático de KPIs, la generación
automática de recomendaciones, la detección automática de stockouts y el pipeline de
preparación desde un archivo ingestado son orquestaciones entre módulos que se implementan
en un bloque de integración posterior; sus endpoints quedan como placeholder documentado.
La persistencia y el CRUD de todas esas entidades sí están implementados.

## ADR-008 — Forecasting en background con adapter FTGM

`POST /forecast-runs/{run_id}/execute` responde 202 y agenda `run_forecast_job` vía
`BackgroundTasks`, que abre su propia sesión, ejecuta `ExecuteForecastRun` (start → llamar
al `FtgmHttpAdapter` → persistir resultados/métricas → complete) y hace commit. Cualquier
fallo marca el run como `failed` con su mensaje. El motor se consume por el puerto
`ForecastEnginePort`; el adapter HTTP vive en `infrastructure/adapters`.

## ADR-009 — Pipeline de preparación de datos (Bloque 3)

**Contexto.** El motor FTGM no limpia datos: recibe series ya limpias y devuelve
pronósticos. La limpieza es responsabilidad de `data_preparation`.

**Decisión.** `POST /companies/{id}/data-preparation/prepare` (caso de uso
`PrepareDatasetFromBatch`) toma un `IngestionBatch`, lee el archivo vía `StoragePort`,
lo parsea (CSV; Excel pendiente, sin dependencia de pandas/openpyxl), resuelve SKU→producto
vía `ProductRepository` (SKUs desconocidos se omiten) y construye las series limpias.

La limpieza vive en un **servicio de dominio puro** (`domain/services.py`,
`prepare_demand_series`): agrega la demanda por fecha, rellena huecos del calendario con
días de demanda cero, winsoriza outliers de la cola superior con la regla IQR
(Q3 + 1.5·IQR), y marca *stockout flags* (días con flag explícito o, opcionalmente, días
de demanda cero). El resultado se persiste como `PreparedDataset` en estado READY, listo
para que forecasting lo consuma. El parsing de formato es infraestructura
(`infrastructure/file_parser.py`); la resolución de SKU es aplicación; la limpieza es
dominio puro y testeable sin DB.

## ADR-010 — Inteligencia DSS (Bloque 5): fórmulas y orquestación

**Contexto.** La capa de inteligencia (KPIs y recomendaciones) es el aporte analítico del
DSS y debe ser defendible y reproducible. No depende de cómo se generó el pronóstico, solo
de los `ForecastResult` almacenados, por lo que se implementa sin necesidad del motor FTGM.

**Decisión.** Las fórmulas viven en **servicios de dominio puros** (sin I/O), testeados:
- `kpis/domain/services.py`: cobertura (stock / demanda diaria media), riesgo de quiebre
  (déficit sobre lead time vs stock + safety, 0–100), rotación (demanda / stock), riesgo de
  sobrestock (exceso sobre el objetivo de lead time, 0–100).
- `recommendations/domain/services.py`: política *order-up-to* (objetivo = demanda en
  lead time + periodo de revisión + safety; cantidad = ⌈objetivo − stock⌉) con prioridad por
  urgencia.
- `inventory`: detección automática de stockouts cuando el stock derivado ≤ 0.

La **orquestación cross-módulo** vive en la capa de aplicación de cada módulo: los casos de
uso (`ComputeCompanyKpis`, `GenerateRecommendations`, `DetectStockouts`) reciben por
constructor los puertos de otros módulos (products, forecasting, inventory) y combinan los
tres insumos (pronóstico + stock derivado + parámetros del producto). Endpoints:
`POST .../kpis/calculate`, `POST .../recommendations/generate`,
`POST .../inventory/stockouts/detect`. Requieren un ForecastRun en estado `success`.

Parámetros fijos por ahora (k=1.5 IQR, periodo de revisión 7 días); se parametrizarán y
justificarán cuando se formalice la metodología de la tesis.
