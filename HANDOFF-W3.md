# W3 lightweight SDK handoff

Implementation and bounded verification are complete. The complete W3 API,
lightweight SDK and deployed full SDK handoff is in
`../chain-api/HANDOFF-W3.md`; the final commit manifest, including each
handoff commit, is in `../HANDOFF-W3.md`.

- Repository/worktree: `/Users/ruitaochen/Desktop/Yototec/implementation-worktrees/credits-cutover/w3/chain-sdk`
- Branch: `work/yt-credits-w3`
- Base: `83d1fdaac74b42e1b2a10c11db5a2461614b2491`
- Implementation: `021b6e4fe5d6381927bc8afcb28d00aa36230b0b`
- API implementation: `9495de8828aa14f07d777989c05568069dac0594`
- Full SDK implementation: `4266c68cfa0f6babde059d409485ff8ffedf350f`
- Full SDK handoff: `a665d4dfb59c85edede5d6ffbc4508f0ce82d6f7`

Bearer permanent credentials replace URL keys. Paid reads preserve one purchase
UUID across transport retries and accept explicit `idempotency_key` recovery.
Public transactions are ordered full matrices and optional matrix proofs only;
unexpected fields or malformed matrices are rejected. Canonical writer/signing
and key helpers are unchanged. Retired account, mapper-content and cross-product
reasoning methods were removed. README documents the new read/verification limits.

Focused checks: `.venv/bin/ruff check sentichain tests` passed;
`.venv/bin/pytest -q -m 'not live'` passed **210 tests**, with one live metadata
check deselected. Local HTTP balance evidence: free metadata leaves **2**;
a deliberately lost committed response and its automatic retry debit once to
**1**; explicit same-operation retry remains **1**; a fresh intentional purchase
reaches **0**; subsequent HTTP402 and missing-data404 remain **0**. Exact **3×2**
and **2×2** matrices preserve row order and values. Changed values, truncated
matrices and a wrong trusted key fail the independent matrix proof check.

Offline wheel/sdist build and Twine checks passed. Local unpublished artifacts:

- `dist/sentichain-0.4.0-py3-none-any.whl`, SHA256
  `d44702ad7c2563b6fee35f824e5bed3372cb684b356ba493bfe6b6a957e111bd`
- `dist/sentichain-0.4.0.tar.gz`, SHA256
  `49deeb51f98c6974b155e6bccc81082f57f74c53944189ec2b19a3decdad4f1f`

Integrate the API and website changes together. Configure the caller's permanent
key privately, change transaction iteration to ordered lists, use free metadata
before paid refreshes, remove retired calls, and pin a trusted vectorizer public
key for independent matrix verification. Package publication/activation and the
coordinator's real assembled end-to-end check remain unapplied.

No live call, production enrollment/write, deployment, merge, push, package
publication, future-block wait or historical scratch-clone change occurred.

W3 DONE
