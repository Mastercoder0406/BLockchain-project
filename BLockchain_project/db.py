import os
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING
# MONGO_URI = os.getenv("MONGO_URI")

MONGO_URI = "mongodb+srv://admin:admin123@cluster0.jh355lx.mongodb.net/?appName=Cluster0"

client = MongoClient(MONGO_URI)
db = client["did_lab"]

issuer_col = db["issuer_identities"]
subject_col = db["subject_identities"]
identity_col = db["identities"]
credentials_col = db["credentials"]
chain_col = db["chain_blocks"]
revocations_col = db["revocations"]

print("Mongo URI:", MONGO_URI)
print("Connected to DB:", db)

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def ensure_indexes():
    issuer_col.create_index([("did", ASCENDING)], unique=True)
    subject_col.create_index([("did", ASCENDING)], unique=True)
    identity_col.create_index([("did", ASCENDING)], unique=True)
    credentials_col.create_index([("credentialId", ASCENDING)], unique=True)
    chain_col.create_index([("index", ASCENDING)], unique=True)
    revocations_col.create_index([("credentialId", ASCENDING)], unique=True)

ensure_indexes()