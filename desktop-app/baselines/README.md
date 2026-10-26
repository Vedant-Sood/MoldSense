# Optional local reference captures

Experimental captures are not included in the public source repository. The app and its test suite work without them; tests generate temporary, explicitly synthetic signals.

For the legacy comparison panel, you may place your own local `cap_1.bmerawdata`, `cap_2.bmerawdata` and `cap_1_tailored_to_cap_2.bmerawdata` files here. They are ignored by Git. With no matching comparison pair, the panel displays "Not available" and produces no reference finding.

Keep original and derived captures separate and preserve provenance. These files do not establish mold/no-mold ground truth. Do not publish experimental captures or device backups in a source contribution.
