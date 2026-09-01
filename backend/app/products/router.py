from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.products.models import Product
from app.products.schemas import ProductCreate, ProductOut, ProductUpdate
from app.users.models import User

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Page[ProductOut], dependencies=[Depends(require_perm("products:read"))])
def list_products(
    category: str | None = None,
    active_only: bool = False,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Product)
    if category:
        stmt = stmt.where(Product.category == category)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Product.name.ilike(q), Product.sku.ilike(q), Product.category.ilike(q)))
    stmt = apply_sort(stmt, Product, params.sort)
    return paginate(db, stmt, params)


@router.get("/{product_id}", response_model=ProductOut, dependencies=[Depends(require_perm("products:read"))])
def get_product(product_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Product, product_id, "Product")


@router.post("", response_model=ProductOut)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("products:write"))):
    if payload.sku and db.scalar(select(Product).where(Product.sku == payload.sku)):
        raise AppError("A product with this SKU already exists", 409)
    product = Product(**payload.model_dump())
    db.add(product)
    db.flush()
    audit(db, user.id, "create", "product", product.id, {"name": product.name})
    db.commit()
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: str, payload: ProductUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("products:write"))):
    product = get_or_404(db, Product, product_id, "Product")
    changes = apply_updates(product, payload.model_dump(exclude_unset=True))
    if changes:
        audit(db, user.id, "update", "product", product.id, changes)
    db.commit()
    return product


@router.delete("/{product_id}", response_model=Message)
def delete_product(product_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("products:delete"))):
    product = get_or_404(db, Product, product_id, "Product")
    name = product.name
    db.delete(product)
    audit(db, user.id, "delete", "product", product_id, {"name": name})
    db.commit()
    return {"detail": "Product deleted"}
