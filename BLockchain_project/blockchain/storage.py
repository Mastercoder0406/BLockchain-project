import json

# def save_chain(chain, filename="chain.json"):
#     data = [block.__dict__ for block in chain]
#     with open(filename, "w") as f:
#         json.dump(data, f, indent=4)

# def load_chain(filename="chain.json"):
#     try:
#         with open(filename, "r") as f:
#             return json.load(f)
#     except:
#         return []


from db import chain_col

def save_block(block_dict):
    chain_col.insert_one(block_dict)

def load_blocks():
    return list(chain_col.find({}, {"_id": 0}).sort("index", 1))

def chain_count():
    return chain_col.count_documents({})

def clear_chain():
    chain_col.delete_many({})