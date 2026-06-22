"""ClientCRM API — client-facing features ka surface (admin).

- End-customer mini-CRM + birthday/anniversary wishes (app/marketing/customer_crm.py)
- Mini-site product catalog CRUD (app/marketing/product_catalog.py)

(Razorpay payment links removed 2026-06-18 — no online gateway; manual UPI.)
Sab additive + free-stack + ban-safe (wishes = DRAFT/1-click, KOI auto-send
nahi). Writes admin-only. Mount: /api + prefix /clientcrm.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/clientcrm", tags=["ClientCRM"])


# ----------------------- F1: end-customer mini-CRM ----------------------- #
class CustomerIn(BaseModel):
    name: str
    phone: str
    birthday: str | None = ""  # "MM-DD" ya "YYYY-MM-DD"
    anniversary: str | None = ""
    tags: list[str] | None = None


@router.post("/customers/{client_id}")
async def add_customer(client_id: str, body: CustomerIn, _user=Depends(require_admin)):
    """Client ke END-CUSTOMER ko CRM me add karo (phone dedupe)."""
    from app.marketing import customer_crm

    return customer_crm.add_customer(
        client_id,
        body.name,
        body.phone,
        birthday=body.birthday or "",
        anniversary=body.anniversary or "",
        tags=body.tags or [],
    )


class ImportIn(BaseModel):
    rows: list[dict] | None = None
    csv_text: str | None = ""


@router.post("/customers/{client_id}/import")
async def import_customers(client_id: str, body: ImportIn, _user=Depends(require_admin)):
    """Bulk import — Excel/CSV paste ya dict rows (Name/Mobile/DOB alias-mapped)."""
    from app.marketing import customer_crm

    return customer_crm.import_rows(client_id, rows=body.rows, csv_text=body.csv_text or "")


@router.get("/customers/{client_id}")
async def get_customers(client_id: str, tag: str | None = None, _user=Depends(require_admin)):
    """Client ke saved customers (optional ?tag= filter)."""
    from app.marketing import customer_crm

    rows = customer_crm.list_customers(client_id, tag=tag)
    return {"client_id": client_id, "count": len(rows), "customers": rows}


@router.get("/occasions/today")
async def occasions_today(_user=Depends(require_admin)):
    """Aaj (IST) ke birthday/anniversary — saare clients ek saath."""
    from app.marketing import customer_crm

    groups = customer_crm.all_clients_todays_occasions()
    return {
        "clients": len(groups),
        "total_occasions": sum(len(g.get("occasions", [])) for g in groups),
        "groups": groups,
    }


@router.post("/wishes/run")
async def wishes_run(_user=Depends(require_admin)):
    """Aaj ke wish DRAFTS banao (caption + AI image + wa.me 1-click). Auto-send NAHI."""
    from app.marketing import customer_crm

    return await customer_crm.run_wishes(execute=False)


@router.get("/wishes/drafts")
async def wishes_drafts(limit: int = 100, date: str | None = None, _user=Depends(require_admin)):
    """Saved wish drafts (?date=MM-DD filter optional)."""
    from app.marketing import customer_crm

    rows = customer_crm.list_wish_drafts(limit=limit, date=date)
    return {"count": len(rows), "drafts": rows}


# ----------------------- F2: mini-site product catalog ------------------- #
class ProductIn(BaseModel):
    name: str
    price_inr: float | str | None = 0
    photo_url: str | None = ""
    desc: str | None = ""
    in_stock: bool = True


@router.post("/catalog/{slug}")
async def catalog_add(slug: str, body: ProductIn, _user=Depends(require_admin)):
    """Mini-site (/b/{slug}) catalog me product add karo."""
    from app.marketing import product_catalog

    return product_catalog.add_product(
        slug,
        body.name,
        price_inr=body.price_inr or 0,
        photo_url=body.photo_url or "",
        desc=body.desc or "",
        in_stock=body.in_stock,
    )


@router.get("/catalog/{slug}")
async def catalog_list(slug: str, _user=Depends(require_admin)):
    """Slug ke saare products (in/out of stock dono)."""
    from app.marketing import product_catalog

    items = product_catalog.list_products(slug)
    return {"slug": slug, "count": len(items), "products": items}


class ProductUpdateIn(BaseModel):
    name: str | None = None
    price_inr: float | str | None = None
    photo_url: str | None = None
    desc: str | None = None
    in_stock: bool | None = None


@router.post("/catalog/{slug}/{product_id}")
async def catalog_update(
    slug: str, product_id: str, body: ProductUpdateIn, _user=Depends(require_admin)
):
    """Product partial update (price/stock/photo/desc)."""
    from app.marketing import product_catalog

    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    return product_catalog.update_product(slug, product_id, **fields)


@router.delete("/catalog/{slug}/{product_id}")
async def catalog_delete(slug: str, product_id: str, _user=Depends(require_admin)):
    """Product delete."""
    from app.marketing import product_catalog

    return product_catalog.delete_product(slug, product_id)


# Razorpay payment-link routes (/payment-link, /payment-links) removed 2026-06-18 —
# no online gateway; clients collect from their customers via manual UPI.
