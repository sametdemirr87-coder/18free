# Bot regression checks — 2026-09-22

Run from the repository root:

    node tests/bot-regressions.cjs
    python tests/test_zuncia_security.py

Zuncia loader 1.0.1 removes the window-geometry detector. Zoom, browser chrome,
sidebars and minimizing are not reliable evidence of developer tools. Only a
trusted, non-repeating keyboard shortcut emits the versioned keyboard source.
The source label is diagnostic metadata, not cryptographic authentication.
The server ignores legacy Zuncia signals because old loaders overwrite the
original source with `bot_keydown`. It no longer guesses a Zuncia license from
the most recently online user when a report cannot identify a license.

Existing affected users must replace their installed loader with the corrected
per-user script. Updating the downloaded bot bundle cannot replace the loader
that is already installed in Tampermonkey. Ignoring an old report server-side
prevents a persistent license ban but does not repair an old loader's local gate.
Old ambiguous license blocks require an explicit admin decision; no bulk unlock
or automatic migration is performed in application code.

AztlaCoin 4.2.2 selects eligible mission games with 60% group probability and
other eligible games with 40%. Least-recent selection within a group prevents
starvation. Alternatives suppress immediate repeats; consequently the actual
ratio may differ when only one mission game is eligible or cooldowns limit the
pool. Completed, claimed, expired and locally reached mission targets do not
receive priority. Failed games receive a 60-second retry delay. Empty-pool waits
are finite and refresh cooldowns, not missions.

Tests use synthetic data, not real game sessions. They cover 10,000 selections,
all eight game IDs, distribution, repeats, completed/expired tasks, cooldowns,
retry delays, large window gaps, synthetic/repeated F12 and explicit F12.
Server tests run with fake configuration and no production persistence.
