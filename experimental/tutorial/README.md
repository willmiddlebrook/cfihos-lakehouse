> Origin: This synthetic tutorial data and procedure are original to this kit and
> licensed under MIT.

# Tutorial source files

These neutral CSVs contain invented records only. They correspond exactly to the two
feeds in `src/onramp/sources/example_cmms.yml` and to the evidence recorded in
`src/onramp/profiles/example_cmms.yml`:

- `example_locations.csv` becomes `<catalog>.bronze.example_locations`.
- `example_assets.csv` becomes `<catalog>.bronze.example_assets`.

After notebook 00 creates the upload Volume (the governed file folder), upload both
files through Catalog Explorer. Run notebook 01 first with its defaults for locations,
then rerun it with `feed_table_name=example_assets` and
`file_name=example_assets.csv`. Keep `source_name=example_cmms` for both because that
widget names the one logical source, while `feed_table_name` names each physical input
table.

The `UNKNOWN` location status is intentional. It demonstrates a blocked, untranslated
code in notebook 02 rather than silently assigning a standard value.
