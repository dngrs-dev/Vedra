"""Usage: git diff --cached --name-only | python scripts/check_ownership.py A|B"""
import fnmatch
import sys

OWN = {
    "A": ["backend/app/geo/*", "backend/config/geo_sources.yaml", "backend/config/soil_categories.yaml",
          "backend/requirements/a-geo.txt", "backend/scripts/a/*", "backend/tests/a/*",
          "backend/tests/fixtures/geo/*", "backend/tests/fixtures/parcels.json",
          "backend/tests/contract/test_geo_provider_contract.py", "backend/data/a/*",
          "backend/docs/PART_A_DATA_GEO.md", "backend/docs/DATA_SOURCES.md"],
    "B": ["backend/app/main.py", "backend/app/config.py", "backend/app/api/*", "backend/app/analytics/*",
          "backend/app/recommendations/*", "backend/app/reports/*", "backend/app/jobs/*",
          "backend/app/storage/*", "backend/app/fakes/*", "backend/app/contracts/report.py",
          "backend/config/*", "backend/requirements/b-app.txt", "backend/Dockerfile", "backend/scripts/b/*",
          "backend/tests/b/*", "backend/tests/contract/test_pipeline_on_fixtures.py",
          "backend/tests/fixtures/sample_report.json", "backend/data/b/*", "backend/README.md",
          "backend/docs/*"],
}
EXCLUDE_FROM_B = OWN["A"]  # A's files under config/ and docs/ stay A's

who = sys.argv[1]
bad = []
for path in (line.strip() for line in sys.stdin if line.strip()):
    if not path.startswith("backend/"):
        continue  # frontend / repo root are outside this check
    mine = any(fnmatch.fnmatch(path, p) for p in OWN[who])
    if who == "B" and any(fnmatch.fnmatch(path, p) for p in EXCLUDE_FROM_B):
        mine = False
    if not mine:
        bad.append(path)
if bad:
    print("Not your files:\n  " + "\n  ".join(bad))
    sys.exit(1)
