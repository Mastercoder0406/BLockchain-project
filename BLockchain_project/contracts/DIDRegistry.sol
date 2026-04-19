// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title DIDRegistry
 * @notice Decentralized Identity + KYC Credential Registry on Ethereum
 * @dev Stores DID documents, KYC credential hashes, and revocations on-chain
 */
contract DIDRegistry {

    // ─────────────────────────────────────────────
    // STRUCTS
    // ─────────────────────────────────────────────

    struct DIDDocument {
        string did;
        string role;           // "issuer" | "subject" | "generic"
        string publicKey;      // base64-encoded Ed25519 public key
        string documentJson;   // full DID document as JSON string
        address owner;
        uint256 createdAt;
        bool exists;
    }

    struct Credential {
        string credentialId;
        string issuerDid;
        string subjectDid;
        bytes32 credentialHash;  // keccak256 of VC JSON (without proof)
        uint256 issuedAt;
        bool revoked;
        string revokeReason;
        bool exists;
    }

    // ─────────────────────────────────────────────
    // STATE
    // ─────────────────────────────────────────────

    address public owner;

    mapping(string => DIDDocument)  private _dids;           // did → DIDDocument
    mapping(string => Credential)   private _credentials;    // credentialId → Credential
    mapping(address => string)      private _addressToDid;   // wallet → did

    string[] private _allDids;
    string[] private _allCredentials;

    // ─────────────────────────────────────────────
    // EVENTS
    // ─────────────────────────────────────────────

    event DIDRegistered(
        string indexed did,
        string role,
        address indexed owner,
        uint256 timestamp
    );

    event CredentialIssued(
        string indexed credentialId,
        string indexed issuerDid,
        string indexed subjectDid,
        bytes32 credentialHash,
        uint256 timestamp
    );

    event CredentialRevoked(
        string indexed credentialId,
        string reason,
        uint256 timestamp
    );

    // ─────────────────────────────────────────────
    // MODIFIERS
    // ─────────────────────────────────────────────

    modifier onlyOwner() {
        require(msg.sender == owner, "DIDRegistry: not contract owner");
        _;
    }

    modifier didExists(string memory did) {
        require(_dids[did].exists, "DIDRegistry: DID not found");
        _;
    }

    // ─────────────────────────────────────────────
    // CONSTRUCTOR
    // ─────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
    }

    // ─────────────────────────────────────────────
    // DID FUNCTIONS
    // ─────────────────────────────────────────────

    /**
     * @notice Register a new DID on-chain
     * @param did       The DID string (e.g. did:lab:abc123)
     * @param role      Role: "issuer", "subject", or "generic"
     * @param publicKey Base64-encoded Ed25519 public key
     * @param docJson   Full DID document JSON string
     */
    function registerDID(
        string memory did,
        string memory role,
        string memory publicKey,
        string memory docJson
    ) external {
        require(!_dids[did].exists, "DIDRegistry: DID already registered");

        _dids[did] = DIDDocument({
            did:          did,
            role:         role,
            publicKey:    publicKey,
            documentJson: docJson,
            owner:        msg.sender,
            createdAt:    block.timestamp,
            exists:       true
        });

        _addressToDid[msg.sender] = did;
        _allDids.push(did);

        emit DIDRegistered(did, role, msg.sender, block.timestamp);
    }

    /**
     * @notice Resolve a DID document
     */
    function resolveDID(string memory did)
        external
        view
        didExists(did)
        returns (
            string memory role,
            string memory publicKey,
            string memory documentJson,
            address didOwner,
            uint256 createdAt
        )
    {
        DIDDocument storage doc = _dids[did];
        return (doc.role, doc.publicKey, doc.documentJson, doc.owner, doc.createdAt);
    }

    /**
     * @notice Check if a DID is registered
     */
    function isDIDRegistered(string memory did) external view returns (bool) {
        return _dids[did].exists;
    }

    /**
     * @notice Get total number of registered DIDs
     */
    function getTotalDIDs() external view returns (uint256) {
        return _allDids.length;
    }

    // ─────────────────────────────────────────────
    // CREDENTIAL FUNCTIONS
    // ─────────────────────────────────────────────

    /**
     * @notice Anchor a KYC credential hash on-chain
     * @param credentialId  SHA-256 ID of the credential
     * @param issuerDid     DID of the issuing authority
     * @param subjectDid    DID of the credential subject
     * @param credentialHash keccak256 hash of the VC payload
     */
    function issueCredential(
        string memory credentialId,
        string memory issuerDid,
        string memory subjectDid,
        bytes32 credentialHash
    ) external didExists(issuerDid) didExists(subjectDid) {
        require(!_credentials[credentialId].exists, "DIDRegistry: credential already anchored");

        _credentials[credentialId] = Credential({
            credentialId:   credentialId,
            issuerDid:      issuerDid,
            subjectDid:     subjectDid,
            credentialHash: credentialHash,
            issuedAt:       block.timestamp,
            revoked:        false,
            revokeReason:   "",
            exists:         true
        });

        _allCredentials.push(credentialId);

        emit CredentialIssued(credentialId, issuerDid, subjectDid, credentialHash, block.timestamp);
    }

    /**
     * @notice Revoke a credential on-chain (immutable audit trail)
     * @param credentialId  ID of the credential to revoke
     * @param reason        Human-readable revocation reason
     */
    function revokeCredential(string memory credentialId, string memory reason)
        external
    {
        require(_credentials[credentialId].exists, "DIDRegistry: credential not found");
        require(!_credentials[credentialId].revoked, "DIDRegistry: already revoked");

        _credentials[credentialId].revoked = true;
        _credentials[credentialId].revokeReason = reason;

        emit CredentialRevoked(credentialId, reason, block.timestamp);
    }

    /**
     * @notice Check on-chain revocation status
     */
    function isRevoked(string memory credentialId) external view returns (bool) {
        if (!_credentials[credentialId].exists) return false;
        return _credentials[credentialId].revoked;
    }

    /**
     * @notice Get anchored credential hash for verification
     */
    function getCredential(string memory credentialId)
        external
        view
        returns (
            string memory issuerDid,
            string memory subjectDid,
            bytes32 credentialHash,
            uint256 issuedAt,
            bool revoked,
            string memory revokeReason
        )
    {
        require(_credentials[credentialId].exists, "DIDRegistry: credential not found");
        Credential storage c = _credentials[credentialId];
        return (c.issuerDid, c.subjectDid, c.credentialHash, c.issuedAt, c.revoked, c.revokeReason);
    }

    /**
     * @notice Get total number of anchored credentials
     */
    function getTotalCredentials() external view returns (uint256) {
        return _allCredentials.length;
    }

    /**
     * @notice Get contract stats
     */
    function getStats()
        external
        view
        returns (uint256 totalDIDs, uint256 totalCredentials)
    {
        return (_allDids.length, _allCredentials.length);
    }
}
