"""Generate VAPID keys for Web Push. Run once; keep the private key secret."""
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


private = ec.generate_private_key(ec.SECP256R1())
private_number = private.private_numbers().private_value.to_bytes(32, "big")
public = private.public_key().public_bytes(
    serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint,
)
print("VAPID_PUBLIC_KEY=" + b64url(public))
print("VAPID_PRIVATE_KEY=" + b64url(private_number))
print("VAPID_SUBJECT=mailto:YOUR_EMAIL_ADDRESS")
