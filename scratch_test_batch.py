from gbp_sentinel import db, remediation_engine

locs = db.get_locations("Rankingpartner B.V. & Doorway Network (websitelatenmakenindenhaag.nl)")
engine = remediation_engine.RemediationEngine()
res = engine.process_batch(locs)

print("=" * 60)
print(f"Totaal geanalyseerd: {res['total']}")
print(f"Hernoemen (RENAME): {len(res['renames'])}")
print(f"Verwijderen (REMOVE): {len(res['removals'])}")
print(f"Behouden (KEEP): {len(res['kept'])}")
print("=" * 60)

for r in res["renames"]:
    print(f"[RENAME] {r['original_title']}")
    print(f"   --> {r['clean_name']} (Betrouwbaarheid: {r['confidence']}%)")

for r in res["removals"]:
    print(f"[REMOVE] {r['original_title']}")
    print(f"   --> {r['reasons'][0]}")

for r in res["kept"]:
    print(f"[KEEP]   {r['original_title']}")
