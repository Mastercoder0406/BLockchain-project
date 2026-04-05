import json
import time
import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def issue_credential(issuer_did, subject_did, claims, private_key_b64):
    vc = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "type": ["VerifiableCredential", "KYC"],
        "issuer": issuer_did,
        "issuanceDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "credentialSubject": {
            "id": subject_did,
            "kyc": claims
        }
    }

    payload = json.dumps(vc, sort_keys=True).encode()
    vc["credentialId"] = hashlib.sha256(payload).hexdigest()

    payload = json.dumps(vc, sort_keys=True).encode()

    priv_bytes = base64.b64decode(private_key_b64)
    private_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    signature = private_key.sign(payload)

    vc["proof"] = {
        "type": "Ed25519Signature2020",
        "verificationMethod": f"{issuer_did}#key-1",
        "signature": base64.b64encode(signature).decode()
    }

    return vc


def verify_credential(vc, public_key_b64):
    if "proof" not in vc:
        return False

    proof = vc["proof"]
    vc_copy = vc.copy()
    vc_copy.pop("proof")

    payload = json.dumps(vc_copy, sort_keys=True).encode()

    pub_bytes = base64.b64decode(public_key_b64)
    pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)

    try:
        pub_key.verify(
            base64.b64decode(proof["signature"]),
            payload
        )
        return True
    except Exception:
        return False