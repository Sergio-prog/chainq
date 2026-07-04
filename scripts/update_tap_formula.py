import json
import sys
import urllib.request
from pathlib import Path

TEMPLATE = Path(__file__).with_name("chainq.rb.tmpl")


def main() -> None:
    version, out_path = sys.argv[1], Path(sys.argv[2])
    with urllib.request.urlopen(f"https://pypi.org/pypi/chainq/{version}/json") as resp:
        payload = json.load(resp)
    sdist = next(f for f in payload["urls"] if f["packagetype"] == "sdist")
    formula = TEMPLATE.read_text().replace("{{URL}}", sdist["url"]).replace("{{SHA256}}", sdist["digests"]["sha256"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(formula)
    print(f"wrote {out_path} for chainq {version}")


if __name__ == "__main__":
    main()
