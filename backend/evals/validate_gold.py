import json
from pathlib import Path

from app.schemas.extraction import ContractExtraction

GOLD = Path(__file__).parent / "gold"


def main() -> None:
    files = sorted(GOLD.glob("*.json"))
    assert len(files) == 8, f"expected 8 gold files, found {len(files)}"
    for f in files:
        ContractExtraction.model_validate(json.loads(f.read_text()))
        print("ok", f.name)


if __name__ == "__main__":
    main()
