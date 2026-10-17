# Paper submissions

One YAML file per proposed paper (see `TEMPLATE.yml`, or use the form at
<https://akmaier.github.io/ActiveMatterLivingReview/contribute/>). A pull request that adds files
here is checked automatically (`scripts/validate_submissions.py`): required fields, DOI format,
Crossref title match, and whether the review already holds the record.

After a maintainer merges it, the next update (`amlr fetch submissions`) turns each file into a
record "identified via other methods" (PRISMA 2020), which is deduplicated and screened by the same
LLM panel and criteria as the database records.
