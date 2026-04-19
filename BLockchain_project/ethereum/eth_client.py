"""
ethereum/eth_client.py
──────────────────────
Ethereum bridge layer — connects the Flask app to the DIDRegistry
smart contract running on Ganache (or any EVM-compatible network).

Usage
-----
from ethereum.eth_client import EthClient
eth = EthClient()
eth.register_did(did, role, pub_key, doc_json, sender_address)
"""

import json
import os
import hashlib
from pathlib import Path
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware   # for Ganache PoA

# ─────────────────────────────────────────────────────
# CONFIG  — edit these or override via environment vars
# ─────────────────────────────────────────────────────

GANACHE_URL      = os.getenv("GANACHE_URL",       "http://127.0.0.1:7545")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS",  "0xB2A6aaa637b01bC7b5497Fab6b1A78eB9FB13D40")   # filled after deploy
DEPLOYER_ADDRESS = os.getenv("DEPLOYER_ADDRESS",  "0x5d2e454cc6E329f1B8D5eE9c1D74aAB8bF3df31E")   # Ganache account[0]
PRIVATE_KEY      = os.getenv("DEPLOYER_PRIVATE_KEY", "0xfd7a093d82ad45dc1467ed01dcd48e79f5fce16c8d8a7930fe6f2819f6628c79") # Ganache account[0] private key

# Path to the ABI file produced by Remix
ABI_PATH = Path(__file__).parent / "DIDRegistry_abi.json"


class EthClient:
    """
    Thin wrapper around web3.py for the DIDRegistry contract.
    All write methods sign & send transactions automatically.
    """

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
        # Ganache uses proof-of-authority — inject middleware
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not self.w3.is_connected():
            raise ConnectionError(
                f"❌  Cannot reach Ganache at {GANACHE_URL}\n"
                "    Make sure Ganache is running and the URL is correct."
            )

        self.contract_address = Web3.to_checksum_address(CONTRACT_ADDRESS) if CONTRACT_ADDRESS else None
        self.deployer          = Web3.to_checksum_address(DEPLOYER_ADDRESS) if DEPLOYER_ADDRESS else None
        self.private_key       = PRIVATE_KEY

        if self.contract_address and ABI_PATH.exists():
            abi = json.loads(ABI_PATH.read_text())
            self.contract = self.w3.eth.contract(
                address=self.contract_address, abi=abi
            )
        else:
            self.contract = None
            print("⚠️  EthClient: contract not loaded. Run deploy first.")

    # ─────────────────────────────────────────────
    # INTERNAL HELPERS
    # ─────────────────────────────────────────────

    def _send(self, fn, sender: str = None):
        """
        Build, sign and broadcast a contract transaction.
        Returns the transaction receipt.
        """
        sender = Web3.to_checksum_address(sender or self.deployer)

        tx = fn.build_transaction({
            "from":     sender,
            "nonce":    self.w3.eth.get_transaction_count(sender),
            "gas":      3_000_000,
            "gasPrice": self.w3.eth.gas_price,
        })

        signed = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        if receipt["status"] != 1:
            raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")

        return receipt

    @staticmethod
    def _credential_hash(vc_dict: dict) -> bytes:
        """
        Compute the keccak256 hash of the VC payload (proof stripped).
        Returns raw 32-byte value suitable for bytes32 Solidity param.
        """
        vc_copy = {k: v for k, v in vc_dict.items() if k != "proof"}
        payload = json.dumps(vc_copy, sort_keys=True).encode()
        return Web3.keccak(text=json.dumps(vc_copy, sort_keys=True))

    # ─────────────────────────────────────────────
    # DID OPERATIONS
    # ─────────────────────────────────────────────

    def register_did(self, did: str, role: str, public_key: str,
                     doc_json: str, sender: str = None) -> dict:
        """Anchor a new DID on-chain."""
        receipt = self._send(
            self.contract.functions.registerDID(did, role, public_key, doc_json),
            sender
        )
        return {
            "tx_hash":    receipt["transactionHash"].hex(),
            "block":      receipt["blockNumber"],
            "gas_used":   receipt["gasUsed"],
        }

    def resolve_did(self, did: str) -> dict:
        """Read a DID document from chain (no gas)."""
        role, pub_key, doc_json, owner, created_at = \
            self.contract.functions.resolveDID(did).call()
        return {
            "did":          did,
            "role":         role,
            "publicKey":    pub_key,
            "documentJson": doc_json,
            "owner":        owner,
            "createdAt":    created_at,
        }

    def is_did_registered(self, did: str) -> bool:
        return self.contract.functions.isDIDRegistered(did).call()

    # ─────────────────────────────────────────────
    # CREDENTIAL OPERATIONS
    # ─────────────────────────────────────────────

    def anchor_credential(self, vc: dict, sender: str = None) -> dict:
        """Hash the VC and write the anchor to the blockchain."""
        cred_id   = vc["credentialId"]
        issuer    = vc["issuer"]
        subject   = vc["credentialSubject"]["id"]
        cred_hash = self._credential_hash(vc)

        receipt = self._send(
            self.contract.functions.issueCredential(
                cred_id, issuer, subject, cred_hash
            ),
            sender
        )
        return {
            "tx_hash":        receipt["transactionHash"].hex(),
            "block":          receipt["blockNumber"],
            "credential_hash": cred_hash.hex(),
        }

    def revoke_on_chain(self, credential_id: str, reason: str = "",
                        sender: str = None) -> dict:
        """Write a revocation permanently to the blockchain."""
        receipt = self._send(
            self.contract.functions.revokeCredential(credential_id, reason),
            sender
        )
        return {
            "tx_hash":  receipt["transactionHash"].hex(),
            "block":    receipt["blockNumber"],
        }

    def is_revoked_on_chain(self, credential_id: str) -> bool:
        return self.contract.functions.isRevoked(credential_id).call()

    def get_credential_on_chain(self, credential_id: str) -> dict:
        issuer, subject, cred_hash, issued_at, revoked, reason = \
            self.contract.functions.getCredential(credential_id).call()
        return {
            "issuerDid":       issuer,
            "subjectDid":      subject,
            "credentialHash":  cred_hash.hex(),
            "issuedAt":        issued_at,
            "revoked":         revoked,
            "revokeReason":    reason,
        }

    # ─────────────────────────────────────────────
    # STATS / UTILITY
    # ─────────────────────────────────────────────

    def get_stats(self) -> dict:
        total_dids, total_creds = self.contract.functions.getStats().call()
        return {
            "total_dids":        total_dids,
            "total_credentials": total_creds,
            "network":           self.w3.eth.chain_id,
            "block":             self.w3.eth.block_number,
        }

    def get_accounts(self) -> list:
        return self.w3.eth.accounts

    def get_balance(self, address: str) -> float:
        checksum = Web3.to_checksum_address(address)
        wei = self.w3.eth.get_balance(checksum)
        return float(self.w3.from_wei(wei, "ether"))
