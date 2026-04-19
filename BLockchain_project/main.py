from blockchain.chain import Blockchain
from identity.keygen import generate_keypair
from identity.did import create_did
from identity.credential import issue_credential, verify_credential



from connect import issue_certificate, verify_certificate

# Issue certificate
issue_certificate("123", "Atharva", "BTech", "XYZ College")

# Verify certificate
cert = verify_certificate("123")

print("\n--- Certificate ---")
print("Name:", cert[0])
print("Degree:", cert[1])
print("Issuer:", cert[2])

# bc = Blockchain()

# 1. Create issuer identity (e.g. your lab)
priv_issuer, pub_issuer = generate_keypair()
issuer_did, issuer_doc = create_did(pub_issuer)
# bc.add({"type": "DID_REGISTER", "did": issuer_did, "document": issuer_doc})

# 2. Create subject identity (e.g. a researcher)
priv_subject, pub_subject = generate_keypair()
subject_did, subject_doc = create_did(pub_subject)
# bc.add({"type": "DID_REGISTER", "did": subject_did, "document": subject_doc})

# 3. Issue a credential
vc = issue_credential(issuer_did, subject_did,
    {"name": "Dr. Alice", "role": "Researcher", "lab": "BioLab A"},
    priv_issuer)

# 4. Verify it
valid = verify_credential(vc, pub_issuer)
print(f"Credential valid: {valid}")
print(f"Chain valid: {bc.is_valid()}, Blocks: {len(bc.chain)}")
print("Issuer DID:", issuer_did)
print("Subject DID:", subject_did)
print("Credential Valid:", valid)
print("Blockchain Valid:", bc.is_valid())
print("Total Blocks:", len(bc.chain))