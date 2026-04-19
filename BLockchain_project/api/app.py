
from flask import Flask, jsonify, request, render_template
import os
import json

from blockchain.chain import Blockchain           # keeps local chain as audit log
from identity.keygen import generate_keypair
from identity.did import create_did
from identity.credential import issue_credential, verify_credential

from db import (
    issuer_col, subject_col, identity_col,
    credentials_col, revocations_col, utc_now
)

# ── Ethereum bridge ────────────────────────────────────────────────────────────
from ethereum.eth_client import EthClient

eth: EthClient | None = None

def get_eth() -> EthClient | None:
    """Lazy-init the Ethereum client; returns None if not configured."""
    global eth
    if eth is None:
        try:
            eth = EthClient()
            print("✅  Ethereum client connected to Ganache")
        except Exception as exc:
            print(f"⚠️   Ethereum client unavailable: {exc}")
            eth = None
    return eth

# ── Flask init ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))

bc = Blockchain()   # local MongoDB-backed chain kept for backward compat

# ── Helpers ────────────────────────────────────────────────────────────────────

def collection_for_role(role):
    if role == "issuer":   return issuer_col
    if role == "subject":  return subject_col
    return identity_col

def get_issuers():   return list(issuer_col.find({},  {"_id": 0}))
def get_subjects():  return list(subject_col.find({}, {"_id": 0}))

def find_identity(did):
    return (
        issuer_col.find_one(  {"did": did}, {"_id": 0}) or
        subject_col.find_one( {"did": did}, {"_id": 0}) or
        identity_col.find_one({"did": did}, {"_id": 0})
    )

def register_identity(role):
    priv, pub = generate_keypair()
    did, doc  = create_did(pub)

    record = {
        "role":       role,
        "did":        did,
        "public_key": pub,
        "document":   doc,
        "created_at": utc_now(),
        "eth_tx":     None,
        "eth_block":  None,
    }

    # ── 1. Write to MongoDB ────────────────────────────────────────────────────
    collection_for_role(role).insert_one(record)

    # ── 2. Write to local chain ────────────────────────────────────────────────
    bc.add({"type": "DID_REGISTER", "role": role, "did": did, "document": doc})

    # ── 3. Anchor on Ethereum ─────────────────────────────────────────────────
    eth_info = {}
    client = get_eth()
    if client and client.contract:
        try:
            doc_json = json.dumps(doc, sort_keys=True)
            eth_info = client.register_did(did, role, pub, doc_json)
            # back-fill tx hash into Mongo record
            collection_for_role(role).update_one(
                {"did": did},
                {"$set": {"eth_tx": eth_info["tx_hash"], "eth_block": eth_info["block"]}}
            )
        except Exception as exc:
            print(f"⚠️   Ethereum anchor failed for {did}: {exc}")
            eth_info = {"error": str(exc)}

    return {
        "role":        role,
        "did":         did,
        "public_key":  pub,
        "private_key": priv,
        "document":    doc,
        "ethereum":    eth_info,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    client   = get_eth()
    eth_stats = {}
    if client and client.contract:
        try:
            eth_stats = client.get_stats()
        except Exception:
            pass

    return render_template(
        "index.html",
        issuer_count=issuer_col.count_documents({}),
        subject_count=subject_col.count_documents({}),
        credential_count=credentials_col.count_documents({}),
        revoked_count=revocations_col.count_documents({}),
        eth_stats=eth_stats,
        eth_connected=(client is not None and client.contract is not None),
    )


# ══════════════════════════════════════════════════════════════════════════════
# DID API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/did/create", methods=["POST"])
def create_did_api():
    role   = request.json.get("role", "generic")
    record = register_identity(role)
    return jsonify(record)


@app.route("/did/resolve/<path:did>", methods=["GET"])
def resolve_did_api(did):
    client = get_eth()
    if client and client.contract:
        try:
            return jsonify(client.resolve_did(did))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 404
    # Fallback to Mongo
    identity = find_identity(did)
    if not identity:
        return jsonify({"error": "DID not found"}), 404
    return jsonify(identity)


# ══════════════════════════════════════════════════════════════════════════════
# CREDENTIAL API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/credential/issue", methods=["POST"])
def issue_credential_api():
    body    = request.json
    issuer  = find_identity(body["issuer_did"])
    subject = find_identity(body["subject_did"])

    if not issuer:  return jsonify({"error": "Issuer not found"}),  404
    if not subject: return jsonify({"error": "Subject not found"}), 404

    vc = issue_credential(
        body["issuer_did"], body["subject_did"],
        body["claims"], body["private_key"]
    )

    # ── 1. Mongo ───────────────────────────────────────────────────────────────
    credentials_col.insert_one({
        "credentialId": vc["credentialId"],
        "issuer":       body["issuer_did"],
        "subject":      body["subject_did"],
        "credential":   vc,
        "status":       "active",
        "created_at":   utc_now(),
        "eth_tx":       None,
    })

    # ── 2. Local chain ─────────────────────────────────────────────────────────
    bc.add({
        "type":          "KYC_ISSUED",
        "issuer":        body["issuer_did"],
        "subject":       body["subject_did"],
        "credential_id": vc["credentialId"],
    })

    # ── 3. Ethereum anchor ────────────────────────────────────────────────────
    eth_info = {}
    client   = get_eth()
    if client and client.contract:
        try:
            eth_info = client.anchor_credential(vc)
            credentials_col.update_one(
                {"credentialId": vc["credentialId"]},
                {"$set": {"eth_tx": eth_info["tx_hash"]}}
            )
        except Exception as exc:
            eth_info = {"error": str(exc)}

    vc["ethereum"] = eth_info
    return jsonify(vc)


@app.route("/credential/verify", methods=["POST"])
def verify_credential_api():
    body    = request.json
    vc      = body["vc"]
    cred_id = vc.get("credentialId")

    # ── Signature check ────────────────────────────────────────────────────────
    valid = verify_credential(vc, body["public_key"])

    # ── On-chain revocation check (authoritative) ─────────────────────────────
    revoked_on_chain = False
    client = get_eth()
    if client and client.contract and cred_id:
        try:
            revoked_on_chain = client.is_revoked_on_chain(cred_id)
        except Exception:
            pass

    # ── Mongo fallback for revocation ─────────────────────────────────────────
    cred = credentials_col.find_one({"credentialId": cred_id})
    revoked_mongo = cred and cred.get("status") == "revoked"

    revoked = revoked_on_chain or revoked_mongo

    return jsonify({
        "valid":             valid and not revoked,
        "signature_valid":   valid,
        "revoked":           revoked,
        "revoked_on_chain":  revoked_on_chain,
    })


@app.route("/credential/revoke", methods=["POST"])
def revoke_credential():
    body    = request.json
    cred_id = body["credentialId"]
    reason  = body.get("reason", "")

    # ── 1. Mongo ───────────────────────────────────────────────────────────────
    credentials_col.update_one(
        {"credentialId": cred_id},
        {"$set": {"status": "revoked"}}
    )
    revocations_col.insert_one({
        "credentialId": cred_id,
        "reason":       reason,
        "revoked_at":   utc_now(),
        "eth_tx":       None,
    })

    # ── 2. Local chain ─────────────────────────────────────────────────────────
    bc.add({"type": "CREDENTIAL_REVOKED", "credential_id": cred_id})

    # ── 3. Ethereum (permanent, immutable) ────────────────────────────────────
    eth_info = {}
    client   = get_eth()
    if client and client.contract:
        try:
            eth_info = client.revoke_on_chain(cred_id, reason)
            revocations_col.update_one(
                {"credentialId": cred_id},
                {"$set": {"eth_tx": eth_info["tx_hash"]}}
            )
        except Exception as exc:
            eth_info = {"error": str(exc)}

    return jsonify({"message": "Credential revoked", "ethereum": eth_info})


# ══════════════════════════════════════════════════════════════════════════════
# CHAIN / ETH STATUS ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/chain/validate")
def validate_chain():
    return jsonify({"valid": bc.is_valid(), "length": len(bc.chain)})


@app.route("/eth/status")
def eth_status():
    client = get_eth()
    if not client:
        return jsonify({"connected": False, "error": "Ethereum client not initialized"})
    try:
        stats = client.get_stats()
        accounts = client.get_accounts()
        return jsonify({
            "connected":    True,
            "network_id":   stats["network"],
            "block_number": stats["block"],
            "total_dids":   stats["total_dids"],
            "total_credentials": stats["total_credentials"],
            "accounts":     accounts[:5],   # first 5 Ganache wallets
        })
    except Exception as exc:
        return jsonify({"connected": False, "error": str(exc)}), 500


@app.route("/eth/did/<path:did>")
def eth_resolve_did(did):
    client = get_eth()
    if not client or not client.contract:
        return jsonify({"error": "Ethereum not connected"}), 503
    try:
        return jsonify(client.resolve_did(did))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/eth/credential/<credential_id>")
def eth_get_credential(credential_id):
    client = get_eth()
    if not client or not client.contract:
        return jsonify({"error": "Ethereum not connected"}), 503
    try:
        return jsonify(client.get_credential_on_chain(credential_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 404


# ══════════════════════════════════════════════════════════════════════════════
# UI ROUTES  (identical to original, extended with eth_connected flag)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/issuer", methods=["GET", "POST"])
def issuer_page():
    created = None
    if request.method == "POST":
        created = register_identity("issuer")
    return render_template("issuer.html", created=created, issuers=get_issuers())


@app.route("/subject", methods=["GET", "POST"])
def subject_page():
    created = None
    if request.method == "POST":
        created = register_identity("subject")
    return render_template("subject.html", created=created, subjects=get_subjects())


@app.route("/issue_kyc", methods=["GET", "POST"])
def issue_kyc_ui():
    result = error = None
    if request.method == "POST":
        issuer_did  = request.form["issuer_did"]
        subject_did = request.form["subject_did"]
        private_key = request.form["issuer_private_key"]
        claims = {
            "name":    request.form["name"],
            "dob":     request.form["dob"],
            "aadhaar": request.form["aadhaar"],
            "pan":     request.form["pan"],
        }
        try:
            vc = issue_credential(issuer_did, subject_did, claims, private_key)

            credentials_col.insert_one({
                "credentialId": vc["credentialId"],
                "issuer":       issuer_did,
                "subject":      subject_did,
                "credential":   vc,
                "status":       "active",
                "created_at":   utc_now(),
            })
            bc.add({
                "type":          "KYC_ISSUED",
                "issuer":        issuer_did,
                "subject":       subject_did,
                "credential_id": vc["credentialId"],
            })

            # Ethereum anchor
            client = get_eth()
            eth_info = {}
            if client and client.contract:
                try:
                    eth_info = client.anchor_credential(vc)
                except Exception as exc:
                    eth_info = {"error": str(exc)}
            vc["ethereum"] = eth_info

            result = json.dumps(vc, indent=2)
        except Exception as exc:
            error = str(exc)

    return render_template(
        "issue_kyc.html",
        issuers=get_issuers(), subjects=get_subjects(),
        result=result, error=error
    )


@app.route("/verify_kyc", methods=["GET", "POST"])
def verify_kyc_ui():
    result = None
    if request.method == "POST":
        vc         = json.loads(request.form["vc"])
        public_key = request.form["public_key"]
        valid      = verify_credential(vc, public_key)

        cred_id = vc.get("credentialId")
        client  = get_eth()
        revoked_on_chain = False
        if client and client.contract and cred_id:
            try:
                revoked_on_chain = client.is_revoked_on_chain(cred_id)
            except Exception:
                pass

        if revoked_on_chain:
            result = "❌  Revoked on Ethereum blockchain"
        elif valid:
            result = "✅  Valid  (signature verified + not revoked on-chain)"
        else:
            result = "❌  Invalid signature"

    return render_template("verify_kyc.html", result=result)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    get_eth()   # eagerly connect so errors surface on startup
    print("Starting Flask server on http://localhost:5000 ...")
    app.run(debug=True, port=5000)
