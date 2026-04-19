import hashlib, json, time, base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def create_did(public_key_b64):
    key_hash = hashlib.sha256(public_key_b64.encode()).hexdigest()[:24]
    did = f"did:lab:{key_hash}"
    document = {
        "id": did,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verificationMethod": [{
            "id": f"{did}#key-1",
            "type": "Ed25519VerificationKey2020",
            "controller": did,
            "publicKeyBase64": public_key_b64
        }]
    }
    return did, document