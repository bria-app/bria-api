from fastapi import APIRouter

from app.shared.presentation.system_router import router as system_router
from app.modules.auth.presentation.router import router as auth_router
from app.modules.companies.presentation.router import router as companies_router, users_router as companies_users_router
from app.modules.products.presentation.router import router as products_router, categories_router
from app.modules.sales.presentation.router import router as sales_router, batches_router as sales_batches_router
from app.modules.sales.presentation.router import orders_router as sales_orders_router, lost_sales_router
from app.modules.inventory.presentation.router import router as inventory_router
from app.modules.ingestion.presentation.router import router as ingestion_router
from app.modules.data_preparation.presentation.router import router as data_preparation_router
from app.modules.forecasting.presentation.router import runs_router as forecast_runs_router, forecasts_router
from app.modules.kpis.presentation.router import router as kpis_router
from app.modules.recommendations.presentation.router import router as recommendations_router
from app.modules.dashboard.presentation.router import router as dashboard_router
from app.modules.reports.presentation.router import router as reports_router
from app.modules.notifications.presentation.router import router as notifications_router
from app.modules.files.presentation.router import router as files_router
from app.modules.audit.presentation.router import router as audit_router, activity_router
from app.modules.validation.presentation.router import router as validation_router
from app.modules.admin.presentation.router import router as admin_router
from app.modules.billing.presentation.router import router as billing_router, companies_router as companies_billing_router
from app.modules.suppliers.presentation.router import router as suppliers_router
from app.modules.purchases.presentation.router import router as purchases_router
from app.modules.invoicing.presentation.router import router as invoicing_router
from app.modules.custom_fields.presentation.router import router as custom_fields_router, preferences_router

api_router = APIRouter()

# System
api_router.include_router(system_router)

# Auth
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])

# Admin
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])

# Billing (global)
api_router.include_router(billing_router, prefix="/billing", tags=["Billing"])

# Companies
api_router.include_router(companies_router, prefix="/companies", tags=["Companies"])
api_router.include_router(companies_users_router, prefix="/companies", tags=["Company Users"])

# Products
api_router.include_router(products_router, prefix="/companies/{company_id}/products", tags=["Products"])
api_router.include_router(categories_router, prefix="/companies/{company_id}/product-categories", tags=["Product Categories"])

# Sales
api_router.include_router(sales_router, prefix="/companies/{company_id}/sales", tags=["Sales"])
api_router.include_router(sales_batches_router, prefix="/companies/{company_id}/sales/batches", tags=["Sales Batches"])
api_router.include_router(sales_orders_router, prefix="/companies/{company_id}/sales-orders", tags=["POS"])
api_router.include_router(lost_sales_router, prefix="/companies/{company_id}/lost-sales", tags=["POS"])

# Inventory
api_router.include_router(inventory_router, prefix="/companies/{company_id}/inventory", tags=["Inventory", "Inventory Movements", "Inventory Snapshots", "Replenishments", "Stockouts"])

# Ingestion
api_router.include_router(ingestion_router, prefix="/companies/{company_id}/ingestion", tags=["Ingestion"])

# Data Preparation
api_router.include_router(data_preparation_router, prefix="/companies/{company_id}/data-preparation", tags=["Data Preparation"])

# Forecasting
api_router.include_router(forecast_runs_router, prefix="/companies/{company_id}/forecast-runs", tags=["Forecasting"])
api_router.include_router(forecasts_router, prefix="/companies/{company_id}/forecasts", tags=["Forecast Results"])

# KPIs
api_router.include_router(kpis_router, prefix="/companies/{company_id}/kpis", tags=["KPIs"])

# Recommendations
api_router.include_router(recommendations_router, prefix="/companies/{company_id}/recommendations", tags=["Recommendations"])

# Dashboard
api_router.include_router(dashboard_router, prefix="/companies/{company_id}/dashboard", tags=["Dashboard"])

# Reports
api_router.include_router(reports_router, prefix="/companies/{company_id}/reports", tags=["Reports"])

# Notifications
api_router.include_router(notifications_router, prefix="/companies/{company_id}/notifications", tags=["Notifications"])

# Files
api_router.include_router(files_router, prefix="/companies/{company_id}/files", tags=["Files"])

# Audit & Activity
api_router.include_router(audit_router, prefix="/companies/{company_id}/audit", tags=["Audit"])
api_router.include_router(activity_router, prefix="/companies/{company_id}/activity", tags=["Audit"])

# Validation
api_router.include_router(validation_router, prefix="/companies/{company_id}/validation", tags=["Validation"])

# Billing (companies)
api_router.include_router(companies_billing_router, prefix="/companies", tags=["Billing"])

# Suppliers
api_router.include_router(suppliers_router, prefix="/companies/{company_id}/suppliers", tags=["Suppliers"])

# Purchases
api_router.include_router(purchases_router, prefix="/companies/{company_id}/purchases", tags=["Purchases"])

# Invoicing (Boleta / Factura)
api_router.include_router(invoicing_router, prefix="/companies/{company_id}/invoices", tags=["Invoicing"])

# Custom fields (user-defined columns) + saved UI preferences
api_router.include_router(custom_fields_router, prefix="/companies/{company_id}/custom-fields", tags=["Custom Fields"])
api_router.include_router(preferences_router, prefix="/companies/{company_id}/preferences", tags=["Custom Fields"])
