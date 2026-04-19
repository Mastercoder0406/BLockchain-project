# Ethereum Upgrade Guide — DID + KYC Blockchain Project
## From Local Python Chain → Ganache + Remix IDE + Ethereum

---

## What This Upgrade Does

| Before | After |
|---|---|
| Python-only local chain (MongoDB) | Ethereum smart contract (Solidity) |
| No on-chain anchoring | Every DID & credential hash written to Ganache |
| Revocation only in Mongo | Revocation is **immutable** on-chain |
| No wallet/gas concept | web3.py signs transactions automatically |

The local MongoDB chain is kept as an **audit log**. Ethereum becomes the **source of truth** for DID registration, credential anchoring, and revocations.

---

## Files Added / Changed

```
your-project/
├── contracts/
│   └── DIDRegistry.sol          ← NEW: Solidity smart contract
├── ethereum/
│   ├── __init__.py              ← NEW (empty)
│   ├── eth_client.py            ← NEW: Python ↔ Ethereum bridge
│   └── DIDRegistry_abi.json     ← NEW: paste ABI from Remix here
├── api/
│   └── app.py                   ← UPDATED: all routes now anchor to Ethereum
├── .env.example                 ← NEW: env var template
└── requirements.txt             ← UPDATED: added web3>=7.0.0
```

---

## STEP 1 — Install Python Dependencies

Open a terminal inside your project folder (activate your venv first):

```bash
pip install web3>=7.0.0 python-dotenv --break-system-packages
# or inside venv:
pip install web3 python-dotenv
```

Verify:
```bash
python -c "from web3 import Web3; print(Web3.api_version)"
# should print something like: 7.x.x
```

---

## STEP 2 — Start Ganache

1. Open **Ganache** desktop app
2. Click **"New Workspace"** → **Quickstart Ethereum**
3. Note these values (you will need them in Step 5):
   - **RPC URL**: usually `http://127.0.0.1:7545`
   - **Network ID**: usually `1337` or `5777`
   - **Account[0] address** — the first address in the list
   - **Account[0] private key** — click the 🔑 key icon next to Account[0]

Leave Ganache running throughout.

---

## STEP 3 — Deploy Contract in Remix IDE

### 3a. Open Remix
Go to **https://remix.ethereum.org** in your browser.

### 3b. Create the contract file
1. In the left sidebar, click the **Files** icon
2. Click **"New File"** → name it `DIDRegistry.sol`
3. **Paste the entire contents** of `contracts/DIDRegistry.sol` into the editor

### 3c. Compile
1. Click the **Solidity Compiler** icon (second icon in sidebar)
2. Set compiler version to **`0.8.19`** (or "Auto compile" — it will auto-select)
3. Click **"Compile DIDRegistry.sol"**
4. ✅ You should see a green tick — no errors

### 3d. Connect Remix to Ganache
1. Click the **Deploy & Run Transactions** icon (third icon in sidebar)
2. In the **"ENVIRONMENT"** dropdown, select:
   **`Dev - Ganache Provider`**
3. A dialog will appear asking for the RPC endpoint — enter:
   `http://127.0.0.1:7545`
4. Click **OK** — Remix connects to your local Ganache
5. You will see Ganache accounts appear in the "ACCOUNT" dropdown

### 3e. Deploy
1. Make sure **"DIDRegistry"** is selected in the CONTRACT dropdown
2. Click the orange **"Deploy"** button
3. In Ganache, you will see a new **TRANSACTIONS** entry appear
4. Back in Remix, in the bottom panel under **"Deployed Contracts"**,
   copy the **contract address** (looks like `0xAbc123...`)
   → **Save this — you need it in Step 5**

---

## STEP 4 — Export the ABI from Remix

1. In Remix, go to **Solidity Compiler** tab
2. Click the **copy icon** next to "ABI" (below the compile button)
3. Open a text editor, paste the copied ABI
4. Save it as `ethereum/DIDRegistry_abi.json` inside your project

The file should look like a large JSON array starting with `[{"inputs": ...`.

---

## STEP 5 — Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and fill in the real values:

```env
MONGO_URI=mongodb+srv://admin:admin123@cluster0.jh355lx.mongodb.net/...

GANACHE_URL=http://127.0.0.1:7545

# From Remix "Deployed Contracts" section:
CONTRACT_ADDRESS=0xPasteYourContractAddressHere

# Account[0] from Ganache dashboard:
DEPLOYER_ADDRESS=0xPasteGanacheAccount0Here

# Private key (click the key icon next to Account[0] in Ganache):
DEPLOYER_PRIVATE_KEY=0xPastePrivateKeyHere
```

---

## STEP 6 — Load .env in Your Project

Add this at the **top of `db.py`** (before the MongoDB connection):

```python
from dotenv import load_dotenv
import os
load_dotenv()                          # reads .env from project root
MONGO_URI = os.getenv("MONGO_URI")
```

Add this at the **top of `ethereum/eth_client.py`**:
```python
from dotenv import load_dotenv
load_dotenv()
```
*(Already handled in the provided eth_client.py)*

---

## STEP 7 — Add the `ethereum/__init__.py`

Create an empty file at `ethereum/__init__.py`:

```bash
touch ethereum/__init__.py
```

Or on Windows:
```cmd
type nul > ethereum\__init__.py
```

---

## STEP 8 — Replace `api/app.py`

Replace your existing `api/app.py` with the new `api/app.py` provided.

It is a **drop-in replacement** — all original routes are preserved.
The only additions are:
- Ethereum anchor calls after each MongoDB write
- Three new read-only routes: `/eth/status`, `/eth/did/<did>`, `/eth/credential/<id>`

---

## STEP 9 — Run the App

```bash
cd "BLockchain project"
python api/app.py
```

Expected startup output:
```
✅  Ethereum client connected to Ganache
Starting Flask server on http://localhost:5000 ...
```

If you see `⚠️ Ethereum client unavailable` — double-check your `.env` values.

---

## STEP 10 — Test the Full Flow

Open `http://localhost:5000` in your browser and run through the flow:

### A. Create an Issuer
1. Go to `/issuer` → click "Create Issuer"
2. Copy the `did` and `private_key` from the response
3. In Ganache, check the **TRANSACTIONS** tab — you will see a new tx

### B. Create a Subject
1. Go to `/subject` → click "Create Subject"
2. Copy the `did`

### C. Issue KYC Credential
1. Go to `/issue_kyc`
2. Fill in the issuer DID, subject DID, private key, and claim fields
3. Submit — the response will include an `"ethereum": {"tx_hash": "0x..."}` field
4. Verify in Ganache → TRANSACTIONS

### D. Verify KYC
1. Go to `/verify_kyc`
2. Paste the full VC JSON and the issuer's public key
3. Result will show: `✅ Valid (signature verified + not revoked on-chain)`

### E. Revoke and Re-verify
1. Call `POST /credential/revoke` with `{"credentialId": "...", "reason": "test"}`
2. Re-verify the same VC → result: `❌ Revoked on Ethereum blockchain`
3. This revocation is **permanent** — even clearing MongoDB won't un-revoke it

---

## STEP 11 — Verify On-Chain Data in Remix

You can query the contract directly in Remix:

1. Go to **Deploy & Run** tab in Remix
2. Under "Deployed Contracts", expand your `DIDRegistry` contract
3. Use the read functions:
   - `isDIDRegistered` → paste a DID string → click → returns `true`
   - `getStats` → returns total DIDs and credentials
   - `isRevoked` → paste a credential ID → returns `true`/`false`
   - `getCredential` → returns the anchored hash + revocation status

---

## API Reference (New + Updated)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Dashboard (now shows ETH stats) |
| POST | `/did/create` | Create DID → anchored on Ethereum |
| GET | `/did/resolve/<did>` | Resolve DID (from chain or Mongo) |
| POST | `/credential/issue` | Issue VC → hash anchored on Ethereum |
| POST | `/credential/verify` | Verify VC + check on-chain revocation |
| POST | `/credential/revoke` | Revoke → written permanently to chain |
| GET | `/chain/validate` | Validate local MongoDB chain |
| GET | `/eth/status` | Ganache connection + contract stats |
| GET | `/eth/did/<did>` | Resolve DID directly from Ethereum |
| GET | `/eth/credential/<id>` | Get credential data from Ethereum |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ConnectionError: Cannot reach Ganache` | Make sure Ganache is open and `GANACHE_URL` matches |
| `Transaction reverted` | Check that both DIDs exist on-chain before issuing a credential |
| `Contract not loaded` | Verify `CONTRACT_ADDRESS` in `.env` and that `DIDRegistry_abi.json` exists |
| `⚠️ Ethereum anchor failed` | The app still works — Mongo/local chain still record; fix Eth config and retry |
| `Invalid private key` | Private key must start with `0x` in `.env` |
| Web3 import error | Run `pip install "web3>=7.0.0"` |

---

## Architecture Summary

```
Browser / API Client
        │
        ▼
   Flask (app.py)
    │         │
    ▼         ▼
MongoDB    eth_client.py
(fast      (web3.py)
 reads)         │
                ▼
           Ganache (local Ethereum)
                │
                ▼
         DIDRegistry.sol
         (on-chain: DIDs, hashes, revocations)
```
