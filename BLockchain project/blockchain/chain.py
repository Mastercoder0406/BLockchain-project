import hashlib
import json
import time

from blockchain.storage import save_block, load_blocks, chain_count

class Block:
    def __init__(self, index, data, previous_hash, timestamp=None):
        self.index = index
        self.timestamp = time.time() if timestamp is None else timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.nonce = 0
        self.hash = self.compute_hash()

    def compute_hash(self):
        block_data = {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce
        }
        content = json.dumps(block_data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def mine(self, difficulty=2):
        while not self.hash.startswith("0" * difficulty):
            self.nonce += 1
            self.hash = self.compute_hash()

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash
        }

    @classmethod
    def from_dict(cls, data):
        block = cls(
            data["index"],
            data["data"],
            data["previous_hash"],
            timestamp=data["timestamp"]
        )
        block.nonce = data["nonce"]
        block.hash = data["hash"]
        return block


class Blockchain:
    def __init__(self, difficulty=2):
        self.difficulty = difficulty

        if chain_count() == 0:
            genesis = Block(0, {"type": "genesis"}, "0", timestamp=0)
            save_block(genesis.to_dict())

        self.chain = [Block.from_dict(item) for item in load_blocks()]

    def _genesis(self):
        return Block(0, {"type": "genesis"}, "0", timestamp=0)

    def latest(self):
        return self.chain[-1]

    def add(self, data):
        block = Block(len(self.chain), data, self.latest().hash)
        block.mine(self.difficulty)
        save_block(block.to_dict())
        self.chain.append(block)
        return block

    def is_valid(self):
        for i in range(1, len(self.chain)):
            curr, prev = self.chain[i], self.chain[i - 1]
            if curr.hash != curr.compute_hash():
                return False
            if curr.previous_hash != prev.hash:
                return False
        return True

    def find(self, did):
        for block in reversed(self.chain):
            if block.data.get("did") == did:
                return block
        return None