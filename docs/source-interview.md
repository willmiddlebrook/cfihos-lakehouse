# Five-question source interview

Record the answers with the source owner. They map directly to one file under
`src/onramp/sources/`; do not add source-specific code.

1. Which tables or extracts hold the asset data, and how does the kit receive them?
2. Which column is the source identifier for each record?
3. Does each record describe a place or required function in the design (tag), a
   physical item (equipment), or both in separate tables?
4. Which fields can recognize the same record across systems: functional-location
   code, serial number, or a manufacturer-and-model combination?
5. For which canonical attributes is this source authoritative, and what precedence
   rank should each claim receive?

Also capture every source-code-to-RDL-code mapping. A missing translation is a
blocked value, not permission to invent a default.
