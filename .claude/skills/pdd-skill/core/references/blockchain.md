# PDD Reference: Blockchain / Smart Contracts

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for blockchain and smart contract projects (Solidity, Rust/Anchor, Move, Vyper — targeting EVM chains, Solana, Aptos/Sui, and similar on-chain platforms).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Which blockchain(s)? (Ethereum, Solana, Polygon, Arbitrum, etc.)
- Smart contract language (Solidity, Rust/Anchor, Move, Vyper)?
- Framework (Hardhat, Foundry, Anchor, Truffle)?
- Contract type (DeFi, NFT, DAO governance, token, custom)?
- Upgradeability needed? If so, which pattern (UUPS, Transparent Proxy, Diamond)?
- What tokens/standards are involved (ERC-20, ERC-721, ERC-1155, SPL)?
- Mainnet, testnet, or L2 target?
- Audit requirements (internal, external firm, formal verification)?
- Frontend interaction (ethers.js, wagmi, web3.js)?

### Extended `pdd/context/project.md` sections for blockchain / smart contracts

```markdown
## Target Chain and VM
- Chain(s): (Ethereum, Polygon, Arbitrum, Solana, etc.)
- VM: (EVM, SVM, MoveVM)
- Network targets: (mainnet, testnet names, L2s)
- Chain-specific constraints: (block gas limit, transaction size limit, compute units)

## Contract Architecture
- Contract structure: (single contract, multi-contract system, proxy pattern)
- Upgrade strategy: (immutable, UUPS, Transparent Proxy, Diamond/EIP-2535, none)
- Access control model: (Ownable, AccessControl, multisig, DAO-governed)
- Inter-contract communication: (direct calls, delegatecall, cross-program invocation)

## Token Standards and Interfaces
- Standards implemented: (ERC-20, ERC-721, ERC-1155, SPL Token, custom)
- Extensions: (permit, votes, enumerable, pausable, burnable)
- Third-party integrations: (DEX routers, lending protocols, oracles)

## Gas and Cost Budgets
- Gas budget per key operation: (mint, transfer, swap, governance vote)
- Storage optimization strategy: (packed structs, mappings vs arrays, SSTORE2)
- L2 calldata optimization: (if targeting rollups)

## Security Model
- Access control: (role-based, timelocked admin, multisig, governance)
- Oracle dependencies: (Chainlink, Pyth, UMA — trust assumptions)
- External call trust model: (which contracts are trusted, which are untrusted)
- Reentrancy protection approach: (checks-effects-interactions, ReentrancyGuard, Solana CPI guards)
- Value limits and circuit breakers: (max transfer, pause mechanism, rate limiting)

## Deployment and Migration
- Deployment tooling: (Hardhat Ignition, Foundry scripts, Anchor deploy)
- Migration strategy: (fresh deploy, proxy upgrade, data migration)
- Verification: (Etherscan, Sourcify, block explorer verification)
- Deployment environment flow: (local → testnet → staging → mainnet)

## Audit and Formal Verification
- Audit timeline and firm:
- Formal verification scope: (critical financial logic, invariants)
- Bug bounty program:
- Known risk acceptance:
```

---

## Conventions Starter (Workflow 2)

```markdown
# Blockchain / Smart Contract Conventions

## Security First
- Follow checks-effects-interactions pattern for all external calls
- Never use `tx.origin` for authorization — always use `msg.sender`
- Use OpenZeppelin or Solmate for standard implementations — don't roll your own ERC-20/721/1155
- Mark all external/public functions with explicit access control
- Use reentrancy guards on all functions that make external calls or transfer value
- Emit events for every state change — indexers and frontends depend on them

## Gas Optimization
- Pack struct fields to minimize storage slots (uint128 + uint128 = 1 slot)
- Use `calldata` instead of `memory` for read-only function parameters
- Prefer mappings over arrays for large collections — iteration is a gas smell
- Cache storage reads in local variables when accessed multiple times
- Use unchecked blocks for arithmetic that provably cannot overflow
- Avoid dynamic arrays in storage when fixed-size alternatives exist

## Arithmetic and Data
- Use fixed-point math libraries for financial calculations — no floating point on-chain
- Define decimal precision explicitly (e.g., 18 decimals for tokens, 8 for prices)
- Guard against division by zero and overflow in all arithmetic
- Use SafeMath only if targeting Solidity <0.8.0 — 0.8+ has built-in overflow checks

## Upgrade Safety
- Never change storage layout order in upgradeable contracts — append only
- Use storage gaps (`uint256[50] private __gap`) in base contracts for future fields
- Test upgrade paths explicitly — deploy v1, upgrade to v2, verify state preserved
- Initializers instead of constructors for proxy contracts — use `initializer` modifier

## Testing
- 100% test coverage on all state-changing functions — no exceptions
- Fuzz test invariants (total supply, balance conservation, access control)
- Fork mainnet state for integration tests against live protocols
- Test with Slither, Mythril, or Aderyn as part of CI — not just before audit
- Simulate front-running and sandwich attacks on value-transferring functions
- Test gas usage per function and fail CI if budget exceeded

## Code Organization
- One contract per file — file name matches contract name
- Group functions by visibility: external, public, internal, private
- NatSpec comments on all public/external functions and state variables
- Keep contracts under 300 lines — extract libraries for shared logic
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New smart contract

```markdown
# Prompt: <ContractName> contract

## Task
Create a <ContractName> contract that <does what>.

## Standards and Interfaces
- Implements: <ERC-20 / ERC-721 / ERC-1155 / custom interface>
- Extends: <OpenZeppelin base contracts, if any>
- Interacts with: <other contracts, oracles, DEX routers>

## State and Storage
- <state variable — type — purpose, for each>
- Storage optimization notes: <packing, mappings vs arrays>

## Functions
- <function signature — access control — what it does, for each>
- <which functions transfer value or make external calls>

## Access Control
- Roles: <owner, admin, minter, pauser — who can do what>
- Modifiers: <onlyOwner, onlyRole, whenNotPaused>
- Timelocks or multisig requirements:

## Security Considerations
- Reentrancy: <which functions need guards>
- Front-running: <which functions are vulnerable, mitigation>
- Value validation: <input bounds, slippage checks>
- Emergency: <pause mechanism, circuit breakers>

## Events
- <EventName(indexed param, param) — when emitted>

## Constraints
- Gas budget: <target gas per key function>
- Must follow checks-effects-interactions pattern
- No `tx.origin` for authorization
- All arithmetic must handle edge cases (zero, max uint)

## Output format
- Contract implementation (Solidity / Rust / Move)
- Interface definition (if applicable)
- Unit tests covering all state-changing functions
- Gas usage report for key operations
- Deployment script
```

### DeFi protocol integration

```markdown
# Prompt: <Protocol> integration

## Task
Integrate with <protocol> (e.g., Uniswap, Aave, Chainlink) to <purpose — swap tokens, provide liquidity, fetch price feeds, etc.>.

## Protocol Details
- Protocol and version: <e.g., Uniswap V3, Aave V3, Chainlink Data Feeds>
- Chain: <target chain>
- Contract addresses: <router, factory, pool, oracle — from official docs>
- Interface: <ISwapRouter, IPool, AggregatorV3Interface, etc.>

## Integration Points
- <which protocol function to call — parameters — expected return>
- <callback handling, if any (e.g., Uniswap callback)>
- <approval flow for token spending>

## Security
- Slippage protection: <deadline, minimum output, price bounds>
- Oracle manipulation: <TWAP vs spot price, staleness check, fallback oracle>
- Flash loan attack vectors: <how this integration could be exploited>
- Token whitelist: <which tokens are allowed, how to validate>

## Constraints
- Price feeds must include staleness check (revert if stale)
- All swaps must have slippage protection and deadline
- External calls follow checks-effects-interactions
- Handle protocol-specific edge cases (e.g., fee-on-transfer tokens, rebasing tokens)

## Output format
- Integration contract with protocol interaction logic
- Interface definitions for external protocol contracts
- Unit tests with mainnet fork (test against real protocol state)
- Gas report for integration operations
```

### Upgradeable contract system

```markdown
# Prompt: Upgradeable <ContractName>

## Task
Implement <ContractName> as an upgradeable contract using <UUPS / Transparent Proxy / Diamond> pattern.

## Upgrade Architecture
- Pattern: <UUPS / TransparentUpgradeableProxy / Diamond (EIP-2535)>
- Proxy admin: <ProxyAdmin contract / multisig / governance>
- Storage layout: <list storage variables in slot order>

## V1 Implementation
- <functionality for initial deployment>
- Initializer function (replaces constructor)
- Storage gaps for future upgrades

## Upgrade Path
- What V2 will add: <planned additions, if known>
- Storage compatibility: <new variables appended, gaps consumed>
- Migration logic: <reinitializer for V2 state setup>

## Security
- Who can trigger upgrades: <admin role, timelock, governance vote>
- Upgrade timelock: <delay between proposal and execution>
- Storage collision check: <tooling — OpenZeppelin Upgrades plugin, slither>
- Rollback plan: <how to revert a bad upgrade>

## Constraints
- Never reorder or remove existing storage variables
- Initializers must use `initializer` / `reinitializer` modifiers
- No `selfdestruct` or `delegatecall` in implementation (UUPS)
- Test full upgrade path: deploy V1, interact, upgrade to V2, verify state

## Output format
- V1 implementation with initializer and storage gaps
- Proxy deployment script
- V2 stub showing safe upgrade pattern
- Upgrade test (deploy V1, upgrade to V2, assert state preserved)
- Storage layout documentation
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Security**
- [ ] Checks-effects-interactions pattern followed for all external calls?
- [ ] No use of `tx.origin` for authorization?
- [ ] Reentrancy guards on functions that transfer value or make external calls?
- [ ] Access control on all state-changing functions (not just `public`)?
- [ ] No unprotected `selfdestruct` or `delegatecall`?
- [ ] Integer arithmetic safe (overflow/underflow handled, division by zero guarded)?
- [ ] Front-running mitigations where applicable (commit-reveal, deadlines, slippage)?
- [ ] Flash loan attack vectors considered for value-dependent logic?

**Gas and efficiency**
- [ ] Gas usage benchmarked per function and within budget?
- [ ] Storage variables packed efficiently (no wasted slots)?
- [ ] `calldata` used instead of `memory` where possible?
- [ ] Storage reads cached in local variables when accessed multiple times?
- [ ] No unnecessary iteration over unbounded arrays in storage?
- [ ] Events emitted for all state changes (required for indexing)?

**Standards compliance**
- [ ] ERC/token standard fully implemented (all required functions and events)?
- [ ] Interface IDs correctly registered (ERC-165 `supportsInterface`)?
- [ ] NatSpec documentation on all public/external functions?
- [ ] Follows OpenZeppelin or Solmate patterns where applicable?

**Testing**
- [ ] 100% test coverage on all state-changing functions?
- [ ] Fuzz testing passes with no invariant violations?
- [ ] Static analysis clean (Slither, Mythril, or Aderyn)?
- [ ] Edge cases tested (zero values, max values, empty arrays, reentrancy attempts)?
- [ ] Mainnet fork tests for external protocol integrations?
- [ ] Gas snapshot tests to catch regressions?

**Upgradeability** (if applicable)
- [ ] Storage layout unchanged from previous version (append only)?
- [ ] Storage gaps present in base contracts?
- [ ] Initializer used instead of constructor?
- [ ] Upgrade path tested (V1 deploy → interact → upgrade to V2 → verify state)?
- [ ] No `selfdestruct` in implementation contract?
- [ ] Upgrade access properly restricted (timelock, multisig, governance)?

**Deployment**
- [ ] Contract verified on block explorer (Etherscan, Sourcify)?
- [ ] Deployment script tested on testnet before mainnet?
- [ ] Constructor/initializer arguments validated?
- [ ] Deployed bytecode matches verified source?
- [ ] Post-deployment health checks pass (ownership, roles, initial state)?
