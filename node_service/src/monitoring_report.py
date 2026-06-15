import time
import json
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional, Dict
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

def current_epoch():
    """Get current epoch ID (60-second window)"""
    return int(time.time() // 60)

@dataclass
class MonitoringReport:
    url: str
    epoch_id: int
    response_ms: float
    status_code: int
    ssl_valid: bool
    content_hash: str
    is_reachable: bool
    node_address: str
    timestamp: float = None
    signature: str = None
    report_hash: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.report_hash is None:
            self.report_hash = self.calculate_hash()

    def calculate_hash(self):
        data = f"{self.url}{self.epoch_id}{self.node_address}{self.content_hash}"
        return hashlib.sha256(data.encode()).hexdigest()

class NodeSigner:
    def __init__(self, private_key_hex: Optional[str] = None):
        if private_key_hex:
            try:
                self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
            except Exception:
                # Fallback if hex is invalid or wrong length
                self.private_key = ed25519.Ed25519PrivateKey.generate()
        else:
            self.private_key = ed25519.Ed25519PrivateKey.generate()
        
        self.public_key = self.private_key.public_key()
        self.public_key_hex = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        ).hex()

    def sign(self, message: str) -> str:
        signature = self.private_key.sign(message.encode())
        return signature.hex()

    def sign_report(self, report: MonitoringReport) -> MonitoringReport:
        # Create canonical string
        report_dict = asdict(report)
        report_dict.pop('signature', None)
        canonical = json.dumps(report_dict, sort_keys=True)
        report.signature = self.sign(canonical)
        return report

class ReportVerifier:
    @staticmethod
    def from_dict(data: Dict) -> MonitoringReport:
        # Filter out keys that aren't in the dataclass
        valid_keys = MonitoringReport.__dataclass_fields__.keys()
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return MonitoringReport(**filtered_data)

    @staticmethod
    def verify(report: MonitoringReport, public_key_hex: str) -> bool:
        report_dict = asdict(report)
        signature_hex = report_dict.pop('signature', None)
        if not signature_hex:
            return False
        
        canonical = json.dumps(report_dict, sort_keys=True)
        return ReportVerifier.verify_signature(signature_hex, canonical, public_key_hex)

    @staticmethod
    def verify_signature(signature_hex: str, message: str, public_key_hex: str) -> bool:
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
            public_key.verify(bytes.fromhex(signature_hex), message.encode())
            return True
        except Exception:
            return False
