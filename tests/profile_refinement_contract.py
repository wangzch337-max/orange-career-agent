"""Exact C.4 compatibility for TWO shared authority files; no folder exemption."""

import hashlib

# Each approved complete source hash is paired with the unchanged pre-C.4 source.
# Other data/store files still use the original byte-freeze contracts.
SHARED_HASHES = {
    "data/models.py": ("da0788dcbeecf846c90bebc40e7906e6e6ff81cd631cc66a701b013812d43f67",
                       "86b3b14ff75f8c5787fa3beeff8d8570174250d66128214cbb7414613ffd9d8b"),
    "memory/sqlite_store.py": ("c1295d195bc3639898ee11eba00a28b6646404b1822dcbdab932597d1bbf9d5f",
                             "20e88a38fb5883747204be98f7becce04954e6a8b94c767a713abd45895cacc4"),
}


def assert_c4_shared_delta(name, current, historical):
    assert name in SHARED_HASHES, name
    approved, original = SHARED_HASHES[name]
    assert hashlib.sha256(current).hexdigest() == approved, name
    assert hashlib.sha256(historical).hexdigest() == original, name
