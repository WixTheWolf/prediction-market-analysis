# Kalshi scanner schema compatibility

The public Kalshi market API migrated from legacy cent-denominated fields to dollar/fixed-point fields in 2026. The scanner now prefers `*_dollars` price fields and `*_fp` volume/open-interest fields, while retaining legacy fallbacks for old fixtures.

The scheduled scanner also uses broader discovery thresholds so the dashboard displays active markets even when none qualify as evidence-backed opportunities. Recommendations still fail closed unless independent signals are registered.
