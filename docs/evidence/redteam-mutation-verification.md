# Cross-tenant red team: mutation verification

A test that passes with the protection deleted is not a test. Every guard this
suite covers was removed in turn, the suite was run against the mutated tree,
and the tests that noticed were recorded. The source was restored afterwards
and the restoration verified byte-for-byte.

Harness: one mutation at a time, full suite each run, `git status` clean after.

## Results

| Mutation | What was removed | Suite result | Tests that caught it |
|---|---|---|---:|
| M1 | The owner filter on an administrator's **general** search (`case_scope.py`) | 4 failed, 32 passed | 4 |
| M2 | `_assert_case_scoped`, the refusal of an unscoped private-corpus query | 3 failed, 33 passed | 3 |
| M3 | The owner filter on a **named matter** (`case_scope.py`) | 8 failed, 28 passed | 8 |
| M4 | The `case_id` condition in `RetrievalFilters.to_qdrant` | 10 failed, 26 passed | 10 |

Every guard is detected by at least three independent tests.

## M4 found a hole in the matrix, which is the point of doing this

On the first run M4 was caught by **one** test, and not by its advocate
counterpart. The reason was structural rather than incidental: the police case
and the advocate case live in *different Qdrant collections*, so the collection
boundary was silently doing the work the `case_id` filter is supposed to do.
Deleting the tenant filter entirely changed almost no test result.

The matrix was missing its highest-risk cell: **two matters of the same role,
in the same collection**, where nothing separates the evidence but `case_id`.
The fixture now provisions a second police officer and a second advocate, each
with their own matter and marker, and their statements are deliberately near
identical — the same red hatchback leaving the same park minutes apart — so the
vectors sit close together and relevance cannot substitute for the filter.

After that change M4 is caught by ten tests instead of one.

This is worth stating plainly: the suite as first written would have passed
with the tenant filter removed from Qdrant. Running the mutations is what
found that, not reading the tests.

## Coverage

Roles `{citizen, police, police_two, advocate, advocate_two, admin}` against
modes `{general, named matter}` and targets `{own matter, a sibling matter in
the same collection, a matter of another role, no matter}`.

Assertions are made at two levels, because they fail differently:

- **what came back** — a foreign marker in the results is a leak that reached
  the caller.
- **what was asked** — a private collection appearing in the query targets at
  all is a leak that has not reached the caller yet. The administrator
  disclosure was visible at this level first, and only at this level for a
  caller who owned no matching case.

## Guards against a vacuous pass

The fixture asserts, before any test body runs, that every one of the four
matters holds indexed evidence. Isolation between empty indexes is free, and a
suite that quietly stopped indexing would otherwise report perfect security.

The permissive direction is asserted too: each owner must retrieve their own
evidence. Without that, a system that returned nothing to anybody would score
full marks on every isolation test here.
