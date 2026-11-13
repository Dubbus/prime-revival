# PPL semantics notes (pplvm)

**All `tests/cases/*.expected` files are PROVISIONAL**: written from knowledge of PPL, not yet recorded from
HP Prime.app. Per CLAUDE.md the real spec is the virtual calculator. Verify each, then delete it from the list.

Unverified guesses to check first:
- Number/list formatting in PRINT (`{3,9,4}`, `3.5`, integer-valued floats shown as ints).
- Whether PRINT takes multiple args and concatenates them (tests assume yes).
- `2^3^2` right-associativity (=512), `7/2` -> 3.5, `L(2):=9` list assignment, 1-based indexing.
- Division by zero (pplvm raises; real PPL likely returns an undefined/inf value).
- `+` on two lists (pplvm concatenates; unverified).
- Out-of-range index error text and behavior (pplvm's message is invented).
- Not implemented: `FOR x IN list`, matrices, strings ops, `▶` store, CAS, INPUT/CHOOSE, graphics.
