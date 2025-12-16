import datetime
import hashlib
from antigravity.config import settings
from antigravity.logging import get_logger

logger = get_logger("audit_logger")

class AuditLogger:
    def __init__(self, log_file="audit.log"):
        self.enabled = settings.AUDIT_ENABLED
        self.log_file = log_file

    def log_event(self, component: str, message: str, level: str = "INFO"):
        """
        Writes an immutable audit record.
        Format: TIMESTAMP | LEVEL | COMPONENT | MESSAGE | HASH
        """
        if not self.enabled:
            return

        timestamp = datetime.datetime.utcnow().isoformat()
        # Generate hash of content to detect tampering
        content = f"{timestamp}|{level}|{component}|{message}"
        record_hash = hashlib.sha256(content.encode()).hexdigest()
        
        entry = f"{content}|{record_hash}\n"
        
        try:
            with open(self.log_file, "a") as f:
                f.write(entry)
        except Exception as e:
            # Fallback to standard logger if audit write fails
            logger.error("audit_write_failure", error=str(e))

# Global Audit Instance
audit = AuditLogger()
