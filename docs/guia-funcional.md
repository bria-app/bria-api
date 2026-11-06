# Guía funcional — bria API

Recorrido por las **entidades** y **funcionalidades** importantes del backend. Sirve como
mapa del sistema y como material de referencia para la tesis. Las decisiones de diseño
están en [`decisiones.md`](decisiones.md).

## Cómo está organizado todo

Monolito modular con **arquitectura hexagonal**. Cada módulo (`app/modules/<m>/`) tiene
cuatro capas:

- **domain/** — el corazón puro: entidades, value objects, enums, excepciones, servicios de
  dominio (fórmulas) e interfaces de repositorio (puertos). No depende de ningún framework.
- **application/** — casos de uso (una clase con `execute()`) y DTOs de salida. Orquesta el
  dominio; recibe los puertos por constructor.
- **infrastructure/** — modelos ORM (SQLAlchemy), mappers entidad↔ORM, repositorios concretos
  y adapters externos (FTGM, almacenamiento).
- **presentation/** — routers FastAPI, schemas de request, providers de inyección.

Lo transversal vive en `app/shared/` (base de datos, seguridad, errores, deps, puertos).

---

## Entidades importantes

### Identidad y multi-tenant (módulo `companies`)
- **Company** — la MYPE (tenant). Campos: `name`, `tax_id` (RUC, único), `business_type`,
  `email`, `plan`, `status`. Métodos: `suspend()`, `activate()`.
- **User** — usuario de una empresa. Campos: `company_id`, `email` (único global),
  `hashed_password`, `role` (owner/admin/analyst/viewer), `status`. Métodos: `can(permiso)`,
  `disable()`, `record_login()`. Vive en `companies` y lo consume `auth`.

### Catálogo (módulo `products`)
- **Product** — SKU del catálogo. Campos: `sku`, `name`, `unit_cost`/`unit_price` (Money),
  y los **parámetros de inventario** que alimentan al DSS: `lead_time_days`, `safety_stock`,
  `reorder_point`. Método clave: `needs_reorder(on_hand)`.
- **Category** — categoría de productos (árbol opcional vía `parent_id`).

### Ventas (módulo `sales`)
- **Sale** — venta observada. Invariante: `total_amount == unit_price * quantity`. Es la
  materia prima histórica del pronóstico.
- **SalesBatch** — lote de ventas cargadas.

### Inventario (módulo `inventory`)
- **InventoryMovement** — entrada/salida/ajuste. El **stock actual se deriva** de estos
  movimientos (no se almacena directo).
- **StockSnapshot** — foto de stock en un instante.
- **Replenishment** — orden de reposición (sugerida/ordenada/recibida/cancelada).
- **StockoutEvent** — periodo sin stock; `close(at)` y `duration_days()`.

### Pipeline de datos (módulos `ingestion` y `data_preparation`)
- **IngestionBatch** — archivo subido + `column_mapping` + estado del pipeline.
- **PreparedDataset** — agregado raíz con series limpias listas para el motor.
- **PreparedTimeSeries** — serie por producto (hija del dataset); lista de `SeriesPoint`.
- Value objects: `SeriesPoint` (fecha, demanda, is_stockout), `RawDemandRow` (fila cruda con
  SKU), `DemandRecord` (con producto resuelto).

### Predicción (módulo `forecasting`)
- **ForecastRun** — ejecución con **máquina de estados**
  (pending→running→success/failed/cancelled); `start/complete/fail/cancel`.
- **ForecastResult** — pronóstico por producto: lista de `ForecastPoint`
  (fecha, demanda predicha, bandas inferior/superior).
- **ForecastMetrics** — precisión por producto: MAPE, MAE, RMSE.

### Inteligencia DSS (módulos `kpis` y `recommendations`)
- **Kpi** — un indicador calculado por producto: `kpi_type` (coverage_days/stockout_risk/
  turnover/overstock_risk), `value`, `run_id`, `computed_at`.
- **Recommendation** — sugerencia accionable: `recommended_quantity`, `priority`, `reason`,
  `status` (pending/accepted/dismissed); `accept()`, `dismiss()`.

### Soporte (módulos diferidos)
- **Notification**, **StoredFile**, **Report**, **AuditEvent**, **Subscription** (billing),
  **DashboardWidget**, **ValidationRule**, **SystemSetting** (admin).

### Value objects compartidos (`app/shared/domain/value_objects.py`)
- **Money** (Decimal + moneda, valida no negativo), **Quantity** (no negativa),
  **Sku** (normalizado), **Email** (validación de formato), **DateRange** (start ≤ end),
  **Percentage** (0–100).

---

## Funcionalidades importantes (qué hace cada módulo)

- **auth** — registro (crea empresa + owner atómicamente), login (JWT access+refresh),
  refresh de token, `/me`, cambio de contraseña. Hash con bcrypt.
- **companies** — CRUD de empresa, gestión de usuarios (invitar, rol, deshabilitar),
  protegido por rol y por acceso al tenant.
- **products** — CRUD de productos y categorías; SKU único por empresa.
- **sales** — alta individual y por lote, listados por producto y rango de fechas, batches.
- **inventory** — movimientos, **stock derivado**, snapshots, reposiciones, stockouts y
  **detección automática de stockouts**.
- **ingestion** — subida de archivos (vía StoragePort), mapeo de columnas, estados.
- **data_preparation** — **pipeline de limpieza**: lee el archivo, resuelve SKUs, limpia,
  trata outliers, marca stockout flags y construye las series listas para el motor.
- **forecasting** — ciclo de vida del run + **ejecución en background** que llama al
  **motor FTGM** (adapter HTTP) y persiste resultados/métricas; consulta de estado/resultados.
- **kpis** — **cálculo de KPIs** del DSS a partir de pronóstico + stock + parámetros.
- **recommendations** — **generación de recomendaciones** de reposición; aceptar/descartar.
- **reports / notifications / files / audit / dashboard / billing / admin / validation** —
  soporte operativo (CRUD + almacenamiento + auditoría + suscripciones).

---

## Los servicios de dominio (el cerebro, puro y testeable)

Estas son las piezas con valor analítico, todas sin dependencias de framework:

- **`inventory/domain/services.py` → `compute_stock_on_hand(movements)`**: deriva el stock
  sumando entradas/ajustes y restando salidas.
- **`data_preparation/domain/services.py` → `prepare_demand_series(records)`**: agrega por
  fecha, rellena huecos del calendario, winsoriza outliers (regla IQR, cola superior) y
  marca stockout flags.
- **`kpis/domain/services.py`**: `coverage_days`, `stockout_risk`, `turnover`,
  `overstock_risk` (consumen stock + demanda pronosticada + lead time + safety stock).
- **`recommendations/domain/services.py` → `suggest_reorder(inputs)`**: política
  *order-up-to* (nivel objetivo = demanda en lead time + revisión + safety; cantidad =
  objetivo − stock) con prioridad por urgencia.
- **`forecasting/domain/entities.py` → `ForecastRun`**: máquina de estados con transiciones
  válidas.

---

## El flujo DSS de extremo a extremo

```
Ingesta de archivo (ingestion)
      → Preparación: limpieza + outliers + stockout flags (data_preparation)
      → Serie temporal limpia (PreparedTimeSeries)
      → Forecasting: run en background → Motor FTGM → ForecastResult + métricas
      → KPIs: cobertura, riesgo de quiebre, rotación, sobrestock (kpis)
      → Recomendaciones: cantidad sugerida + prioridad + justificación (recommendations)
      → Dashboard / Reportes / Notificaciones (salida)
```

Tres insumos se combinan en la capa de inteligencia (KPIs y recomendaciones):
1. el **pronóstico** (del motor FTGM, almacenado como ForecastResult),
2. el **stock actual** (derivado de los movimientos de inventario),
3. los **parámetros del producto** (lead time, safety stock, reorder point).

---

## Estado de implementación (a la fecha de esta guía)

- Implementado y testeado: las 4 capas de los 18 módulos, el pipeline de preparación y la
  inteligencia DSS (KPIs, recomendaciones, detección de stockouts).
- Pendiente: el **motor FTGM** (repo aparte) — hasta que exista, un `forecast-run/execute`
  termina en `failed` por motor inalcanzable, pero toda la cadena posterior (KPIs/recos)
  funciona sobre cualquier ForecastResult almacenado.
- Desviaciones conocidas en módulos de soporte (dashboard con métricas stub, validation como
  configuración de reglas, admin como ajustes del sistema): ver `decisiones.md`.
