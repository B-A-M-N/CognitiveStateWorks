# Trusted StateWork extensions

Bundles placed under this directory are discovered only by
`compile-registry.py`. Compilation validates their data contracts and pins all
bundle bytes in `compiled-registry.json`. Executable workflow engines and
freshness validators still require explicit host registration in code.

Create a starter bundle with `python3 scripts/new_statework.py <id> --domain
<domain> --purpose "<purpose>"`. Choose `--engine milestone` for checklist
workflows that should not invent state names. Edit the generated contracts, then
run `python3 scripts/compile-registry.py` to validate and pin the finished
bundle.
