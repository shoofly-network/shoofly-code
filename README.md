## Shoofly Code

1. `NetworkTopology.py`: Class with definitions for network edges, nodes, demands, tunnels and shortcuts.
2. `cpwan_parser.py`: Parser to build the CPWAN network topology
3. `other_networks_parser.py`: Parser to build the network topologies of other networks.
4. `helper.py`: Helper file with APIs used across Shoofly Code
5. `teavar.py`: Python implementation of the TeaVAR algorithm from SIGCOMM 2019.
6. `shooflyv2.py`: Main driver program. Run this program to build k-wise failure resilient and TeaVAR failure resilient Shoofly topologies.
7. `shoofly.py`: Main driver program for all other network topologies (made available by previous work, TeaVAR and SMORE).
8. `max_flow_analysis.py`: Post processing analysis on Shoofly proposed topologies.
9. `evaluate_failure_resistent_topology.py`: Post processing analysis on Shoofly proposed topologies.
10. `feasible_failure_scenarios.py`: Enumerating the feasible failure scenarios.

