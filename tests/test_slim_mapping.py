"""Tests for the locked slim/MVT property-map derivation.

The whole point of the engine is that no city needs custom slim/raster code:
the slim output schema is derived from the canonical [fields] map. These tests
pin that contract.
"""

from types import SimpleNamespace

from addresslayerist.slim import _property_map


def _cfg(fields, mvt_extra=None):
    return SimpleNamespace(fields=fields, mvt_extra=mvt_extra or {})


def test_canonical_fields_map_to_short_keys():
    cfg = _cfg({
        "number": "STREET_NUM",
        "street": "SNAME",
        "unit": "UNIT",
        "full": "ADDRESS",
    })
    assert _property_map(cfg) == {
        "STREET_NUM": "housenumber",
        "SNAME": "street",
        "UNIT": "unit",
        "ADDRESS": "addr",
    }


def test_partial_fields_only_map_what_is_present():
    cfg = _cfg({"street": "STREET_NM", "full": "CIVIC_ADDR"})
    assert _property_map(cfg) == {"STREET_NM": "street", "CIVIC_ADDR": "addr"}


def test_mvt_extra_is_merged_through():
    cfg = _cfg({"number": "N"}, mvt_extra={"ADDRESS_CLASS": "class"})
    assert _property_map(cfg) == {"N": "housenumber", "ADDRESS_CLASS": "class"}


def test_unknown_canonical_keys_are_ignored():
    cfg = _cfg({"number": "N", "postcode": "PC"})  # postcode is not in the schema
    assert _property_map(cfg) == {"N": "housenumber"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All slim-mapping tests passed.")
