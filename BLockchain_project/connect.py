from web3 import Web3
import json

# Connect to Ganache
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:7545"))

# Load config
with open("config.json") as f:
    config = json.load(f)

contract = w3.eth.contract(
    address=config["contract_address"],
    abi=config["abi"]
)

account = w3.eth.accounts[0]

# Issue certificate
def issue_certificate(cert_id, name, degree, issuer):
    tx = contract.functions.issueCertificate(
        cert_id, name, degree, issuer
    ).transact({'from': account})

    w3.eth.wait_for_transaction_receipt(tx)
    print("Certificate stored on blockchain")

# Verify certificate
def verify_certificate(cert_id):
    cert = contract.functions.getCertificate(cert_id).call()
    return cert