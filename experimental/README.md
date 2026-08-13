# Experimental identity layer

Multi-system identity layer — matching, survivorship, stewardship — not part of the core product

## KNOWN OPEN ISSUES

(1) engine.py re-runs re-insert already-mapped rows into id_map (new_maps includes direct); (2) who_wins compares values null-unsafely in the additions join and conflicts filter.
