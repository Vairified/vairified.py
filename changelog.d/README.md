# Changelog fragments

Every pull request that changes user-visible behavior must include a news
fragment in this directory. Fragments are combined into `CHANGELOG.md` by
[`towncrier`](https://towncrier.readthedocs.io/) at release time.

## Naming

Fragments are files named `<issue-or-slug>.<type>.md`, where `<type>` is one of:

| Type         | Purpose                                      |
|--------------|----------------------------------------------|
| `breaking`   | Backwards-incompatible changes               |
| `added`      | New features                                 |
| `changed`    | Changes to existing behavior                 |
| `deprecated` | Features still working but due for removal   |
| `removed`    | Features removed this release                |
| `fixed`      | Bug fixes                                    |
| `security`   | Security-relevant fixes                      |

Prefix with `+` (e.g. `+short-slug.added.md`) when there's no associated
issue number — towncrier will skip the issue-link formatter for these.

## Writing

One fragment per logical change, in complete sentences, past tense:

```
client.members.search() now yields results lazily via an async iterator.
```

## Building the changelog

```bash
uv run towncrier build --yes --version <next-version>
```

This drops a new section at the top of `CHANGELOG.md` and deletes the
fragments.
