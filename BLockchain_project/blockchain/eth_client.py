from web3 import Web3
import json

class EthereumKYCClient:
    def __init__(self, rpc_url, contract_address, abi_path):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        with open(abi_path, "r", encoding="utf-8") as f:
            abi = json.load(f)
        self.contract = self.w3.eth.contract(address=contract_address, abi=abi)
        self.account = self.w3.eth.accounts[0]

    def store_record(self, user_id: str, data_hash_hex: str):
        tx_hash = self.contract.functions.submitRecord(
            user_id,
            bytes.fromhex(data_hash_hex.replace("0x", ""))
        ).transact({"from": self.account})
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    def get_record(self, user_id: str):
        return self.contract.functions.getRecord(user_id).call()