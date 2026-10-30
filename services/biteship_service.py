import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)


class BiteshipService:
    def __init__(self):
        self.api_key = current_app.config["BITESHIP_API_KEY"]
        self.base_url = current_app.config["BITESHIP_BASE_URL"]
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        logger.info("[Biteship] POST %s", url)
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=15)
        except requests.exceptions.Timeout:
            raise RuntimeError("Biteship API timeout.")
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f"Biteship connection error: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("Respons Biteship tidak valid: bukan JSON")

        if not response.ok:
            message = data.get("error") or data.get("message") or str(data) or "Unknown error"
            raise RuntimeError(f"Biteship API error [{response.status_code}]: {message}")

        return data

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        logger.info("[Biteship] GET %s", url)
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
        except requests.exceptions.Timeout:
            raise RuntimeError("Biteship API timeout.")
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f"Biteship connection error: {exc}") from exc

        logger.info("[Biteship] Response %s", response.status_code)

        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("Respons Biteship tidak valid: bukan JSON")

        if not response.ok:
            message = data.get("error") or data.get("message") or "Unknown error"
            raise RuntimeError(f"Biteship API error [{response.status_code}]: {message}")

        return data

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def get_rates(self, origin_postal: str, destination_postal: str, items: list) -> list:
        """
        Get shipping rates.

        Args:
            origin_postal:      origin postal code string (e.g. "44151")
            destination_postal: destination postal code string
            items:              list of dicts with keys 'product' (Product instance)
                                and 'quantity' (int)

        Returns:
            list of dicts with keys: courier_code, courier_name, service,
                                     service_name, price, etd
        """
        couriers_str = current_app.config["BITESHIP_COURIERS"].lower().replace(" ", "")

        items_payload = []
        for entry in items:
            product = entry["product"]
            quantity = entry["quantity"]
            # Prefer pre-resolved variant weight; fall back to product.weight
            unit_w = entry.get("unit_weight")
            if unit_w is None:
                unit_w = product.weight or 1000
            weight_g = int(unit_w * quantity)
            items_payload.append({
                "id": str(product.id),
                "name": product.name,
                "description": product.name,
                "value": int(product.price),
                "weight": max(weight_g, 1),
                "quantity": quantity,
                "height": 1,
                "length": 1,
                "width": 1,
            })

        payload = {
            "origin_postal_code": int(origin_postal),
            "destination_postal_code": int(destination_postal),
            "couriers": couriers_str,
            "items": items_payload,
        }

        data = self._post("/rates/couriers", payload)

        results = []
        for pricing in data.get("pricing", []):
            results.append({
                "courier_code": pricing.get("courier_code", ""),
                "courier_name": pricing.get("courier_name", ""),
                "service": pricing.get("courier_service_code", ""),
                "service_name": pricing.get("courier_service_name", ""),
                "price": pricing.get("price", 0),
                "etd": pricing.get("duration", ""),
            })

        return results

    def create_shipment(self, order) -> dict:
        """
        Create a shipment order on Biteship and return resi + shipment_id.

        Args:
            order: Order model instance (must have .user, .items, .courier,
                   .service, .shipping_address, .shipping_cost)

        Returns:
            dict with keys: resi_number, shipment_id
        """
        user = order.user
        if not user:
            raise ValueError("Order tidak memiliki user.")

        items_payload = []
        for item in order.items:
            product = item.product
            variant = item.variant  # None for legacy / no-variant orders
            unit_w = variant.effective_weight if variant else (product.weight or 1000)
            weight = int(unit_w * item.quantity)
            items_payload.append({
                "id": str(product.id),
                "name": product.name,
                "description": product.name,
                "value": item.price,
                "weight": max(weight, 1),
                "quantity": item.quantity,
            })

        store_name = current_app.config["STORE_NAME"]
        whatsapp = current_app.config["WHATSAPP_NUMBER"]
        mail_user = current_app.config["MAIL_USER"]
        origin_address = current_app.config["BITESHIP_ORIGIN_ADDRESS"]
        origin_postal = current_app.config["BITESHIP_ORIGIN_POSTAL"]

        payload = {
            "shipper_contact_name": store_name,
            "shipper_contact_phone": whatsapp,
            "shipper_contact_email": mail_user,
            "shipper_organization": store_name,
            "origin_contact_name": store_name,
            "origin_contact_phone": whatsapp,
            "origin_address": origin_address,
            "origin_postal_code": int(origin_postal),
            "destination_contact_name": user.name,
            "destination_contact_phone": user.phone or whatsapp,
            "destination_contact_email": user.email,
            "destination_address": order.shipping_address,
            "destination_postal_code": int(order.destination_postal or origin_postal),
            "courier_company": order.courier,
            "courier_type": order.service,
            "delivery_type": "now",
            "order_note": f"Order #{order.id} - {store_name}",
            "metadata": {"order_id": order.id},
            "items": items_payload,
        }

        logger.info("[Biteship] Creating shipment for order %s", order.id)
        data = self._post("/orders", payload)

        resi = data.get("courier", {}).get("waybill_id") or data.get("waybill_id") or ""
        shipment_id = data.get("id", "")

        if not shipment_id:
            raise RuntimeError("Biteship tidak mengembalikan shipment ID")

        logger.info("[Biteship] Shipment created for order %s: resi=%s id=%s", order.id, resi, shipment_id)
        return {
            "resi_number": resi,
            "shipment_id": shipment_id,
        }

    def track_shipment(self, waybill_id: str, courier_code: str) -> dict:
        """
        Track a shipment by waybill/resi number.

        Args:
            waybill_id:   resi / waybill number
            courier_code: e.g. "jne", "jnt", "sicepat"

        Returns:
            dict with keys: status, history (list), courier_name
        """
        path = f"/trackings/{waybill_id}/couriers/{courier_code}"
        data = self._get(path)

        history = []
        for event in data.get("history", []):
            history.append({
                "timestamp": event.get("updated_at", ""),
                "note": event.get("note", ""),
                "status": event.get("status", ""),
            })

        return {
            "status": data.get("status", ""),
            "courier_name": data.get("courier_name", courier_code),
            "waybill_id": data.get("waybill_id", waybill_id),
            "history": history,
        }
