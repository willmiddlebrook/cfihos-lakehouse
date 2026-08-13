> Origin: This evaluation procedure is original to this kit and licensed under MIT.

# Choose how you will use the kit

If the registry, mapping, or stewardship terms are new, start with
[how the system works in plain language](HOW-IT-WORKS.md).

The notebooks support two deliberately different Git modes. Choose one before you
upload source data or edit a mapping.

## Evaluation mode

Clone this repository as a Databricks Git folder and treat its remote as read-only
from your side. A Git folder does not push by itself: nothing leaves the workspace
unless you explicitly push, and in evaluation mode you will not push.

1. Choose a throwaway catalog—a disposable top-level container for governed data—such
   as `cfihos_tutorial_<name>`.
2. Run `notebooks/00_get_started.py` through `notebooks/04_steward.py` in order.
3. Make disposable notebook-side YAML edits when a tutorial asks for them.
4. Review the health, exception, validation, and stewardship surfaces.
5. Drop the throwaway catalog when the evaluation is complete.

Uncommitted edits are expected in this mode. They are workspace experiments, not an
approved production mapping.

## Implementation mode

Fork the repository into a writable remote owned by your organization, then clone
that fork as a Databricks Git folder. A clone keeps the original repository as its
remote; a fork gives your organization a place to review and merge its own source
profiles, mappings, and proposals.

Source YAMLs, profiles, and mapping proposals move through pull requests. Under the
[mapping-proposal workflow](mapping-proposals.md), the pull request is the approval
event and Git history is the audit trail, so the implementation loop requires a
writable remote.

Protect the default branch and require `make test` to pass before merge. Keep raw
profiles out of Git when their sample values are sensitive; the mapping workflow
documents how to pin a local profile instead.
