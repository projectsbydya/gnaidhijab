"""
Cart persistence service.

Session cart format: { "pid:vid": quantity, ... }  (vid=0 for no-variant)
DB cart:   Cart row (one per user)  →  CartItem rows (product_id, variant_id nullable)

The session is always the primary working copy.  DB is synced:
  - load_db_cart_into_session()  → called once at login (after guest-merge)
  - save_session_cart_to_db()    → called after every successful cart mutation
  - clear_db_cart()              → called after checkout order is committed

Guest (unauthenticated) users only ever use the session cart — no DB touch.
"""

from flask import session
from models import db
from models.cart import Cart, CartItem


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_or_create_cart(user_id: int) -> Cart:
    """Return existing Cart for user_id, creating one if it doesn't exist."""
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        cart = Cart(user_id=user_id)
        db.session.add(cart)
        db.session.flush()
    return cart


def _vid_to_db(vid: int):
    """Convert cart key variant id (0 = no variant) to DB nullable int."""
    return None if vid == 0 else vid


def _vid_from_db(variant_id) -> int:
    """Convert DB nullable variant_id back to cart key int (None → 0)."""
    return 0 if variant_id is None else variant_id


# ── Public API ────────────────────────────────────────────────────────────────

def load_db_cart_into_session(user_id: int) -> None:
    """
    Overwrite session["cart"] with the contents of the user's DB cart.
    Called after login (after merging guest cart first).
    """
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        session["cart"] = session.get("cart", {})
        return

    db_cart: dict[str, int] = {}
    for item in cart.items:
        from routes.cart import _make_cart_key
        key = _make_cart_key(item.product_id, _vid_from_db(item.variant_id))
        db_cart[key] = item.quantity

    session["cart"] = db_cart


def save_session_cart_to_db(user_id: int) -> None:
    """
    Persist the current session["cart"] to the DB.
    Existing DB cart items are replaced to stay in sync.
    No-op for unauthenticated users (user_id=None).
    """
    if not user_id:
        return

    cart_data: dict = session.get("cart", {})
    cart = _get_or_create_cart(user_id)

    # Build a lookup of existing items keyed by (product_id, variant_id)
    existing: dict[tuple, CartItem] = {
        (item.product_id, item.variant_id): item
        for item in cart.items
    }

    from routes.cart import _parse_cart_key
    seen: set[tuple] = set()

    for cart_key, qty in cart_data.items():
        parsed = _parse_cart_key(cart_key)
        if not parsed:
            continue
        pid, vid = parsed
        db_vid = _vid_to_db(vid)
        key = (pid, db_vid)
        seen.add(key)

        if key in existing:
            existing[key].quantity = qty
        else:
            db.session.add(CartItem(
                cart_id=cart.id,
                product_id=pid,
                variant_id=db_vid,
                quantity=qty,
            ))

    # Remove DB items no longer in session
    for key, item in existing.items():
        if key not in seen:
            db.session.delete(item)

    db.session.commit()


def merge_guest_cart_into_db(user_id: int) -> None:
    """
    Merge the current session (guest) cart into the user's DB cart.
    Rules:
      - If the item already exists in DB, ADD quantities (capped at _MAX_CART_QTY).
      - If adding a new item would exceed _MAX_CART_TOTAL_ITEMS, skip silently.
    Called at login BEFORE load_db_cart_into_session().
    """
    from routes.cart import _parse_cart_key, _MAX_CART_QTY, _MAX_CART_TOTAL_ITEMS

    guest_cart: dict = session.get("cart", {})
    if not guest_cart:
        return

    cart = _get_or_create_cart(user_id)

    existing: dict[tuple, CartItem] = {
        (item.product_id, item.variant_id): item
        for item in cart.items
    }

    for cart_key, qty in guest_cart.items():
        parsed = _parse_cart_key(cart_key)
        if not parsed:
            continue
        pid, vid = parsed
        db_vid = _vid_to_db(vid)
        key = (pid, db_vid)

        try:
            qty = int(qty)
        except (ValueError, TypeError):
            continue
        if qty < 1:
            continue

        if key in existing:
            # Additive merge, capped
            existing[key].quantity = min(
                existing[key].quantity + qty,
                _MAX_CART_QTY,
            )
        else:
            if len(existing) >= _MAX_CART_TOTAL_ITEMS:
                continue
            new_item = CartItem(
                cart_id=cart.id,
                product_id=pid,
                variant_id=db_vid,
                quantity=min(qty, _MAX_CART_QTY),
            )
            db.session.add(new_item)
            existing[key] = new_item

    db.session.commit()


def clear_db_cart(user_id: int) -> None:
    """
    Delete all CartItems for the user (e.g. after successful checkout).
    No-op if user has no cart row.
    """
    if not user_id:
        return
    cart = Cart.query.filter_by(user_id=user_id).first()
    if cart:
        CartItem.query.filter_by(cart_id=cart.id).delete()
        db.session.commit()
