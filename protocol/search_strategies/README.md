# Search strategies

- `concepts.yml` holds the concept blocks; it is the only file edited by hand.
- Each `amlr search` run writes `<source>-<YYYY-MM-DD>.txt` containing the rendered
  query, the run timestamp (UTC), the record count, the SHA-256 of the raw payload, and the
  `amlr` version. These files are committed and never edited.
- Changing `concepts.yml` after the protocol is frozen is an amendment: log it in
  `../PROTOCOL.md` and bump the protocol tag.
