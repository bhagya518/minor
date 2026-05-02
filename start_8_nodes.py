PS C:\Users\bhagy\Downloads\minor-project-main> .\start_nodes.bat
Starting node_a on port 8005...
Starting node_b on port 8006...
Starting node_c on port 8007...
Starting node_d (malicious) on port 8008...
Starting node_e on port 8009...
Starting node_f on port 8010...
Starting node_g on port 8011...
Starting node_h on port 8012...

All nodes started! Wait 10 seconds for initialization...
Running setup_network.py to register peers...

=== STEP 1: Fetching public keys ===
  node_a: e4809a40e7f9d2a8744084db...
  node_b: 28a65bfe18b2d64caecde3f1...
  node_c: 2ad2c9a8cc3998bd4ebe33a9...
  node_d: 132e198ad723d39526c98b23...
  node_e: 1409dac677406e517a81b750...
  node_f: a40387e838db2c7056c73682...
  node_g: bb5a15aa35e4bd4e8fedc58e...
  node_h: cfde08ef0a77e086ff1b573f...

=== STEP 2: Full mesh peer registration ===
  node_a -> node_b: registered
  node_a -> node_c: registered
  node_a -> node_d: registered
  node_a -> node_e: registered
  node_a -> node_f: registered
  node_a -> node_g: registered
  node_a -> node_h: registered
  node_b -> node_a: registered
  node_b -> node_c: registered
  node_b -> node_d: registered
  node_b -> node_e: registered
  node_b -> node_f: registered
  node_b -> node_g: registered
  node_b -> node_h: registered
  node_c -> node_a: registered
  node_c -> node_b: registered
  node_c -> node_d: registered
  node_c -> node_e: registered
  node_c -> node_f: registered
  node_c -> node_g: registered
  node_c -> node_h: registered
  node_d -> node_a: registered
  node_d -> node_b: registered
  node_d -> node_c: registered
  node_d -> node_e: registered
  node_d -> node_f: registered
  node_d -> node_g: registered
  node_d -> node_h: registered
  node_e -> node_a: registered
  node_e -> node_b: registered
  node_e -> node_c: registered
  node_e -> node_d: registered
  node_e -> node_f: registered
  node_e -> node_g: registered
  node_e -> node_h: registered
  node_f -> node_a: registered
  node_f -> node_b: registered
  node_f -> node_c: registered
  node_f -> node_d: registered
  node_f -> node_e: registered
  node_f -> node_g: registered
  node_f -> node_h: registered
  node_g -> node_a: registered
  node_g -> node_b: registered
  node_g -> node_c: registered
  node_g -> node_d: registered
  node_g -> node_e: registered
  node_g -> node_f: registered
  node_g -> node_h: registered
  node_h -> node_a: registered
  node_h -> node_b: registered
  node_h -> node_c: registered
  node_h -> node_d: registered
  node_h -> node_e: registered
  node_h -> node_f: registered
  node_h -> node_g: registered

[OK] Full mesh registered. Waiting 5s for nodes to sync...

=== STEP 3: Verifying peer registration ===
  node_a: 7 peers OK
  node_b: 7 peers OK
  node_c: 7 peers OK
  node_d: 7 peers OK
  node_e: 7 peers OK
  node_f: 7 peers OK
  node_g: 7 peers OK
  node_h: 7 peers OK

=== STEP 4: Injecting malicious reports from node_d ===
node_d will report the site as DOWN (lie) to all honest nodes.
Honest nodes (a, b, c) report UP -> majority=UP -> node_d gets SLASHED

--- Round 1 (epoch 29627578) ---
  -> port 8005: accepted
  -> port 8006: accepted
  -> port 8007: accepted
  Waiting 5s before next round...
--- Round 2 (epoch 29627578) ---
  -> port 8005: accepted
  -> port 8006: accepted
  -> port 8007: accepted
  Waiting 5s before next round...
--- Round 3 (epoch 29627579) ---
  -> port 8005: accepted
  -> port 8006: accepted
  -> port 8007: accepted

OK Malicious reports injected. Waiting 15s for consensus to process...

=== STEP 5: Live consensus results ===

--- node_a (http://localhost:8005) ---
  Latest epoch:    29627578
  Majority verdict:up
  Honest nodes:    []
  Slashed nodes:   []
  Reputations:
    node_a: 0.8500  ✅ ALLOW
  Total reports stored: 3

--- node_b (http://localhost:8006) ---
  Latest epoch:    29627578
  Majority verdict:up
  Honest nodes:    ['node_c', 'node_b']
  Slashed nodes:   []
  Reputations:
    node_b: 0.9500  ✅ ALLOW
  Total reports stored: 3

--- node_c (http://localhost:8007) ---
  Latest epoch:    29627578
  Majority verdict:up
  Honest nodes:    ['node_c']
  Slashed nodes:   []
  Reputations:
    node_c: 0.9500  ✅ ALLOW
  Total reports stored: 3

--- node_d (http://localhost:8008) ---
  Latest epoch:    29627578
  Majority verdict:up
  Honest nodes:    ['node_d']
  Slashed nodes:   []
  Reputations:
    node_d: 0.9500  ✅ ALLOW
  Total reports stored: 3

--- node_e (http://localhost:8009) ---
  Latest epoch:    29627578
  Majority verdict:up
  Honest nodes:    []
  Slashed nodes:   []
  Reputations:
    node_e: 0.6500  ⚠️  WARN
  Total reports stored: 3

--- node_f (http://localhost:8010) ---
  Latest epoch:    29627578
  Majority verdict:up
  Honest nodes:    []
  Slashed nodes:   []
  Reputations:
    node_f: 0.6500  ⚠️  WARN
  Total reports stored: 3

--- node_g (http://localhost:8011) ---
  Latest epoch:    29627579
  Majority verdict:up
  Honest nodes:    ['node_g']
  Slashed nodes:   []
  Reputations:
    node_g: 0.6500  ⚠️  WARN
  Total reports stored: 4

--- node_h (http://localhost:8012) ---
  Latest epoch:    29627579
  Majority verdict:up
  Honest nodes:    ['node_c', 'node_d', 'node_h']
  Slashed nodes:   []
  Reputations:
    node_h: 0.6500  ⚠️  WARN
  Total reports stored: 4

=== DONE ===
Dashboard -> Multi-Node tab should now show:
  - node_d with low reputation and SLASH action
  - Honest nodes with reputation ~0.97-0.99
  - Majority verdict: 'up'
  - Slashed: ['node_d']

Blockchain tx hashes will appear in the Hardhat terminal.
Run this script again any time to re-inject malicious reports.

Nodes are now running and registered.
Press any key to stop all nodes (close the terminal windows)...
Press any key to continue . . .