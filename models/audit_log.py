"""Audit log model for tracking admin actions."""
from datetime import datetime
from models import db


class AuditLog(db.Model):
    """Log for admin actions including create, update, delete operations."""
    
    __tablename__ = "audit_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user_email = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # CREATE, UPDATE, DELETE, LOGIN, etc.
    entity_type = db.Column(db.String(50), nullable=False)  # product, order, user, etc.
    entity_id = db.Column(db.Integer, nullable=True)  # ID of the affected entity
    entity_name = db.Column(db.String(255), nullable=True)  # Human-readable name
    details = db.Column(db.Text, nullable=True)  # JSON or text details of changes
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    user_agent = db.Column(db.String(500), nullable=True)  # Browser/user agent
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship to user (optional, for easy querying)
    user = db.relationship("User", backref="audit_logs", lazy=True)
    
    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity_type} by {self.user_email}>"


def log_admin_action(
    user_id: int,
    user_email: str,
    action: str,
    entity_type: str,
    entity_id: int = None,
    entity_name: str = None,
    details: str = None,
    request=None,
) -> AuditLog:
    """Create and save an audit log entry.
    
    Args:
        user_id: ID of the admin/staff performing the action
        user_email: Email of the user
        action: Action type (CREATE, UPDATE, DELETE, LOGIN, LOGOUT, etc.)
        entity_type: Type of entity affected (product, order, user, video, etc.)
        entity_id: ID of the affected entity
        entity_name: Human-readable name/title of the entity
        details: Additional details (JSON string or text)
        request: Flask request object to extract IP and user agent
    
    Returns:
        The created AuditLog instance (already added to session, not committed)
    """
    log = AuditLog(
        user_id=user_id,
        user_email=user_email,
        action=action.upper(),
        entity_type=entity_type.lower(),
        entity_id=entity_id,
        entity_name=entity_name,
        details=details,
    )
    
    if request:
        # Get IP address (handle proxies)
        if request.headers.getlist("X-Forwarded-For"):
            log.ip_address = request.headers.getlist("X-Forwarded-For")[0]
        else:
            log.ip_address = request.remote_addr
        
        # Get user agent (truncate if too long)
        ua = request.headers.get("User-Agent", "")
        log.user_agent = ua[:500] if ua else None
    
    db.session.add(log)
    return log
