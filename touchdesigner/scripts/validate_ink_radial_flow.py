"""Native control, glitter and outward/inward phase tests for Ink Radial Flow."""
from pathlib import Path

SCRIPT = Path(__file__).with_name("validate_ink_dream_flow.py")
_scope = dict(globals(), __file__=str(SCRIPT), __name__="_ink_radial_shared_validator")
exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), _scope)


def validate(write_report=True):
    return _scope["validate"](write_report=write_report, radial=True)


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2))
