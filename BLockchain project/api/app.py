from flask import Flask, jsonify, request, render_template
import os
import json

from blockchain.chain import Blockchain
from identity.keygen import generate_keypair
from identity.did import create_did
from identity.credential import issue_credential, verify_credential

from db import (
    issuer_col,
    subject_col,
    identity_col,
    credentials_col,
    revocations_col,
    utc_now
)

# -----------------------------
# FLASK INIT (FIXED)
# -----------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))

bc = Blockchain()


# -----------------------------
# HELPERS
# -----------------------------
def collection_for_role(role):
    if role == "issuer":
        return issuer_col
    if role == "subject":
        return subject_col
    return identity_col


def get_issuers():
    return list(issuer_col.find({}, {"_id": 0}))


def get_subjects():
    return list(subject_col.find({}, {"_id": 0}))


def find_identity(did):
    return (
        issuer_col.find_one({"did": did}, {"_id": 0})
        or subject_col.find_one({"did": did}, {"_id": 0})
        or identity_col.find_one({"did": did}, {"_id": 0})
    )


def register_identity(role):
    priv, pub = generate_keypair()
    did, doc = create_did(pub)

    record = {
        "role": role,
        "did": did,
        "public_key": pub,
        "document": doc,
        "created_at": utc_now()
    }

    collection_for_role(role).insert_one(record)

    bc.add({
        "type": "DID_REGISTER",
        "role": role,
        "did": did,
        "document": doc
    })

    clean_record = {
    "role": role,
    "did": did,
    "public_key": pub,
    "private_key": priv,
    "document": doc
}

    return clean_record


# -----------------------------
# HOME
# -----------------------------
@app.route("/")
def home():
    return render_template(
        "index.html",
        issuer_count=issuer_col.count_documents({}),
        subject_count=subject_col.count_documents({}),
        credential_count=credentials_col.count_documents({}),
        revoked_count=revocations_col.count_documents({})
    )


# -----------------------------
# API ROUTES
# -----------------------------
@app.route("/did/create", methods=["POST"])
def create_did_api():
    role = request.json.get("role", "generic")
    record = register_identity(role)
    return jsonify(record)


@app.route("/credential/issue", methods=["POST"])
def issue_credential_api():
    body = request.json

    issuer = find_identity(body["issuer_did"])
    subject = find_identity(body["subject_did"])

    if not issuer:
        return jsonify({"error": "Issuer not found"}), 404
    if not subject:
        return jsonify({"error": "Subject not found"}), 404

    vc = issue_credential(
        body["issuer_did"],
        body["subject_did"],
        body["claims"],
        body["private_key"]
    )

    credentials_col.insert_one({
        "credentialId": vc["credentialId"],
        "issuer": body["issuer_did"],
        "subject": body["subject_did"],
        "credential": vc,
        "status": "active",
        "created_at": utc_now()
    })

    bc.add({
        "type": "KYC_ISSUED",
        "issuer": body["issuer_did"],
        "subject": body["subject_did"],
        "credential_id": vc["credentialId"]
    })

    return jsonify(vc)


@app.route("/credential/verify", methods=["POST"])
def verify_credential_api():
    body = request.json

    valid = verify_credential(body["vc"], body["public_key"])

    cred_id = body["vc"].get("credentialId")
    cred = credentials_col.find_one({"credentialId": cred_id})

    if cred and cred.get("status") == "revoked":
        return jsonify({"valid": False, "reason": "Revoked"})

    return jsonify({"valid": valid})


@app.route("/credential/revoke", methods=["POST"])
def revoke_credential():
    body = request.json
    cred_id = body["credentialId"]

    credentials_col.update_one(
        {"credentialId": cred_id},
        {"$set": {"status": "revoked"}}
    )

    revocations_col.insert_one({
        "credentialId": cred_id,
        "reason": body.get("reason", ""),
        "revoked_at": utc_now()
    })

    bc.add({
        "type": "CREDENTIAL_REVOKED",
        "credential_id": cred_id
    })

    return jsonify({"message": "Credential revoked"})


@app.route("/chain/validate")
def validate_chain():
    return jsonify({
        "valid": bc.is_valid(),
        "length": len(bc.chain)
    })


# -----------------------------
# UI ROUTES
# -----------------------------
@app.route("/issuer", methods=["GET", "POST"])
def issuer_page():
    created = None

    if request.method == "POST":
        created = register_identity("issuer")

    return render_template(
        "issuer.html",
        created=created,
        issuers=get_issuers()
    )


@app.route("/subject", methods=["GET", "POST"])
def subject_page():
    created = None

    if request.method == "POST":
        created = register_identity("subject")

    return render_template(
        "subject.html",
        created=created,
        subjects=get_subjects()
    )


@app.route("/issue_kyc", methods=["GET", "POST"])
def issue_kyc_ui():
    result = None
    error = None

    if request.method == "POST":
        issuer_did = request.form["issuer_did"]
        subject_did = request.form["subject_did"]
        private_key = request.form["private_key"]

        claims = {
            "name": request.form["name"],
            "dob": request.form["dob"],
            "aadhaar": request.form["aadhaar"],
            "pan": request.form["pan"]
        }

        try:
            vc = issue_credential(
                issuer_did,
                subject_did,
                claims,
                private_key
            )

            credentials_col.insert_one({
                "credentialId": vc["credentialId"],
                "issuer": issuer_did,
                "subject": subject_did,
                "credential": vc,
                "status": "active",
                "created_at": utc_now()
            })

            bc.add({
                "type": "KYC_ISSUED",
                "issuer": issuer_did,
                "subject": subject_did,
                "credential_id": vc["credentialId"]
            })

            result = json.dumps(vc, indent=2)

        except Exception as e:
            error = str(e)

    return render_template(
        "issue_kyc.html",
        issuers=get_issuers(),
        subjects=get_subjects(),
        result=result,
        error=error
    )


@app.route("/verify_kyc", methods=["GET", "POST"])
def verify_kyc_ui():
    result = None

    if request.method == "POST":
        vc = json.loads(request.form["vc"])
        public_key = request.form["public_key"]

        valid = verify_credential(vc, public_key)

        result = "✅ Valid" if valid else "❌ Invalid"

    return render_template("verify_kyc.html", result=result)


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask server...")
    app.run(debug=True, port=5000)