# Items the Opus judges flagged for the author (2026-10-17)

## Held back (full text on file belongs to a different paper; re-retrieve before judging)
- doi:10.1109/iros.2011.6048246 — text is Fine & Shell, "Flocking: don't need no stinkin' robot recognition"
- doi:10.1109/iros.2011.6048389 — text is Hauert et al., "Reynolds flocking in reality with fixed-wing robots"
- doi:10.1007/978-3-319-63537-8_10 — text is a different Cazenille et al. zebrafish/robot paper

## Undecided by the judge (abstract only; hardware vs simulation unclear)
- doi:10.1155/2016/4370635
- doi:10.1299/jsmermd.2024.1p2-m07

## Likely duplicate records (both included)
- ads:2022APS..MARM14002F and openalex:W3013978559 (two GoPiGo3 robots, non-reciprocal alignment)
- doi:10.1038/s41467-021-26699 (truncated DOI) and doi:10.1038/s41467-021-26699-6
- doi:10.1109/iros.2011.6048876: stored abstract belongs to another paper; full text matches title

## Judgement rules applied (spot-check)
- I3 not met by plain trajectory plots or photo snapshots of hardware runs; formation/consensus
  hardware results limited to convergence or tracking error -> E3.
- APS/conference abstracts included only when they state a hardware collective result; otherwise E5.
- Colloids count as programmably controlled when the field/light input is patterned in space or
  time, or under feedback/learning; a global field strength alone -> E6.
- Passive mechanical metamaterial doi:10.1073/pnas.1913228117 coded E6 as closest fit.
- Extraction: simulation-only counts not used for agent numbers; open-loop operator-set external
  field -> central_controller; constant driving field -> no_control_passive_rules.

## Resolved 2026-10-17 (link check, data/linkcheck/)
- doi:10.1038/s41467-021-26699 (truncated DOI) merged into doi:10.1038/s41467-021-26699-6 as a duplicate.
- ACM placeholder DOIs replaced by the registered IFAAMAS DOIs: 10.5555/1402383.1402394 -> 10.65109/tjgp2764,
  10.5555/3091125.3091319 -> 10.65109/kqhs7667.

## Resolved 2026-10-17 (IROS 2011 DOI scramble)
Crossref's IROS 2011 metadata pairs titles with the wrong DOIs. Resolving at doi.org/IEEE Xplore:
10.1109/iros.2011.6048246 = Fine & Shell (flocking), 10.1109/iros.2011.6048389 = Hauert et al. (fixed-wing
flocking), 10.1109/iros.2011.6048876 = "Force control for planar spring-mass running", 10.1109/iros.2011.6048729 =
"RGB-D object discovery". The Fine & Shell and Hauert records now carry the correct DOIs; the two
"ornithopter" / "force-velocity" records were duplicates of them and are merged. The stored PDFs were right.
