from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, PrivateFormat, NoEncryption
)
import base64

# def generate_keypair():
#     private_key = Ed25519PrivateKey.generate()
#     pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
#     priv_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
#     return base64.b64encode(priv_bytes).decode(), base64.b64encode(pub_bytes).decode()

def generate_keypair():
    private_key = Ed25519PrivateKey.generate()

    pub_bytes = private_key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )

    priv_bytes = private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )

    return (
        base64.b64encode(priv_bytes).decode(),
        base64.b64encode(pub_bytes).decode()
    )